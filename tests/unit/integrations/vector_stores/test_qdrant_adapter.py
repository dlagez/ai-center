from __future__ import annotations

import os
import tempfile
import unittest

from app.core.config import VectorStoreSettings
from app.integrations.vector_stores.qdrant_adapter import QdrantVectorStoreAdapter
from app.runtime.retrieval.vector_store import (
    VectorDeleteRequest,
    VectorQueryRequest,
    VectorRecord,
    VectorStoreService,
    VectorUpsertRequest,
)

try:
    from qdrant_client import QdrantClient
except ImportError:  # pragma: no cover - optional dependency in test env
    QdrantClient = None


@unittest.skipIf(QdrantClient is None, "qdrant-client is not installed.")
class QdrantVectorStoreAdapterTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.settings = VectorStoreSettings(
            vector_store_provider="qdrant",
            vector_store_timeout_ms=60000,
            vector_store_default_metric="cosine",
            vector_store_collection_prefix="kb_",
            vector_store_local_dir=self._tmp_dir.name,
            qdrant_url="http://localhost:6333",
            qdrant_api_key=None,
            qdrant_grpc_port=6334,
            qdrant_prefer_grpc=False,
            qdrant_https=False,
        )
        self.client = QdrantClient(location=":memory:")
        self.service = VectorStoreService(
            settings=self.settings,
            adapters={
                "qdrant": QdrantVectorStoreAdapter(
                    self.settings,
                    client=self.client,
                )
            },
        )

    def tearDown(self) -> None:
        self.client.close()
        self._tmp_dir.cleanup()

    def test_build_client_supports_local_mode_with_path(self) -> None:
        local_path = os.path.join(self._tmp_dir.name, "qdrant_local")
        settings = VectorStoreSettings(
            vector_store_provider="qdrant",
            vector_store_timeout_ms=60000,
            vector_store_default_metric="cosine",
            vector_store_collection_prefix="kb_",
            vector_store_local_dir=self._tmp_dir.name,
            qdrant_local_mode=True,
            qdrant_local_path=local_path,
        )

        client = QdrantVectorStoreAdapter._build_client(settings)
        self.assertTrue(os.path.isdir(local_path))
        self.assertTrue(
            getattr(type(getattr(client, "_client", None)), "__module__", "").startswith(
                "qdrant_client.local."
            )
        )
        client.close()

    def test_upsert_query_and_delete_records_round_trip(self) -> None:
        upsert_result = self.service.upsert_records(
            VectorUpsertRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                knowledge_base_id="kb-a",
                index_name="main",
                index_version="v1",
                records=[
                    VectorRecord(
                        chunk_id="chunk-1",
                        document_id="doc-1",
                        text="alpha beta",
                        vector=[1.0, 0.0],
                        metadata={"tags": ["finance"]},
                    ),
                    VectorRecord(
                        chunk_id="chunk-2",
                        document_id="doc-2",
                        text="gamma delta",
                        vector=[0.0, 1.0],
                        metadata={"tags": ["legal"]},
                    ),
                ],
            )
        )

        self.assertEqual(upsert_result.provider, "qdrant")
        self.assertEqual(upsert_result.success_count, 2)

        query_result = self.service.query_vectors(
            VectorQueryRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                knowledge_base_id="kb-a",
                index_name="main",
                index_version="v1",
                query_vector=[0.99, 0.01],
                top_k=2,
                filters={"tenant_id": "tenant-a"},
            )
        )

        self.assertEqual(query_result.total_hits, 2)
        self.assertEqual(query_result.hits[0].chunk_id, "chunk-1")
        self.assertEqual(query_result.hits[0].document_id, "doc-1")
        self.assertEqual(query_result.hits[0].text, "alpha beta")
        self.assertEqual(query_result.hits[0].metadata["knowledge_base_id"], "kb-a")

        delete_result = self.service.delete_records(
            VectorDeleteRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                knowledge_base_id="kb-a",
                index_name="main",
                index_version="v1",
                document_ids=["doc-1"],
            )
        )

        self.assertEqual(delete_result.provider, "qdrant")
        self.assertEqual(delete_result.deleted_count, 1)

        remaining = self.service.query_vectors(
            VectorQueryRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                knowledge_base_id="kb-a",
                index_name="main",
                index_version="v1",
                query_vector=[0.99, 0.01],
                top_k=5,
            )
        )

        self.assertEqual(remaining.total_hits, 1)
        self.assertEqual(remaining.hits[0].chunk_id, "chunk-2")

    def test_upsert_overwrites_existing_chunk_id(self) -> None:
        request = VectorUpsertRequest(
            tenant_id="tenant-a",
            app_id="app-a",
            knowledge_base_id="kb-a",
            index_name="main",
            index_version="v1",
            records=[
                VectorRecord(
                    chunk_id="chunk-1",
                    document_id="doc-1",
                    text="first",
                    vector=[1.0, 0.0],
                )
            ],
        )
        self.service.upsert_records(request)
        self.service.upsert_records(
            request.model_copy(
                update={
                    "records": [
                        VectorRecord(
                            chunk_id="chunk-1",
                            document_id="doc-1",
                            text="updated",
                            vector=[0.8, 0.2],
                        )
                    ]
                }
            )
        )

        query_result = self.service.query_vectors(
            VectorQueryRequest(
                tenant_id="tenant-a",
                app_id="app-a",
                knowledge_base_id="kb-a",
                index_name="main",
                index_version="v1",
                query_vector=[0.8, 0.2],
                top_k=1,
            )
        )

        self.assertEqual(query_result.total_hits, 1)
        self.assertEqual(query_result.hits[0].text, "updated")


if __name__ == "__main__":
    unittest.main()
