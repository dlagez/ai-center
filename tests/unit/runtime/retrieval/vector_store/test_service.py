from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.config import VectorStoreSettings
from app.core.exceptions import (
    VectorStoreDimensionMismatchError,
    VectorStoreValidationError,
)
from app.runtime.retrieval.vector_store import (
    VectorDeleteRequest,
    VectorQueryRequest,
    VectorRecord,
    VectorStoreService,
    VectorUpsertRequest,
)


class VectorStoreServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.settings = VectorStoreSettings(
            vector_store_provider="local_file",
            vector_store_timeout_ms=60000,
            vector_store_default_metric="cosine",
            vector_store_collection_prefix="kb_",
            vector_store_local_dir=self._tmp_dir.name,
        )
        self.service = VectorStoreService(settings=self.settings)

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

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

        self.assertEqual(upsert_result.total_count, 2)
        self.assertEqual(upsert_result.success_count, 2)
        self.assertEqual(upsert_result.failed_count, 0)

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

    def test_upsert_rejects_mixed_vector_dimensions(self) -> None:
        with self.assertRaises(VectorStoreDimensionMismatchError):
            self.service.upsert_records(
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
                            text="first",
                            vector=[1.0, 0.0],
                        ),
                        VectorRecord(
                            chunk_id="chunk-2",
                            document_id="doc-2",
                            text="second",
                            vector=[1.0, 0.0, 0.5],
                        ),
                    ],
                )
            )

    def test_delete_requires_target_ids(self) -> None:
        with self.assertRaises(VectorStoreValidationError):
            self.service.delete_records(
                VectorDeleteRequest(
                    tenant_id="tenant-a",
                    app_id="app-a",
                    knowledge_base_id="kb-a",
                    index_name="main",
                    index_version="v1",
                )
            )

    def test_collection_is_persisted_to_local_store(self) -> None:
        self.service.upsert_records(
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
                    )
                ],
            )
        )

        collection_name = self.service.build_collection_name(
            tenant_id="tenant-a",
            app_id="app-a",
            knowledge_base_id="kb-a",
            index_name="main",
            index_version="v1",
        )
        collection_path = Path(self._tmp_dir.name) / f"{collection_name}.json"

        self.assertTrue(collection_path.exists())
        self.assertEqual(self.service.recorder.records[-1].operation, "upsert_records")

    def test_build_collection_name_preserves_configured_prefix(self) -> None:
        collection_name = self.service.build_collection_name(
            tenant_id="tenant-a",
            app_id="app-a",
            knowledge_base_id="kb-a",
            index_name="main",
            index_version="v1",
        )

        self.assertTrue(collection_name.startswith("kb_"))
        self.assertEqual(
            collection_name,
            "kb_tenant-a__app-a__kb-a__main__v1",
        )


if __name__ == "__main__":
    unittest.main()
