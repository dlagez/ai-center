from __future__ import annotations

import importlib.util
import json
import os
import unittest

from app.core.config import EmbeddingSettings, GatewaySettings
from app.runtime.embedding.gateway_service import build_embedding_gateway_service
from app.runtime.embedding.schemas import EmbeddingBatchRequest, EmbeddingInputItem


class AliyunTextEmbeddingV4IntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.embedding_settings = EmbeddingSettings.from_env()
        cls.gateway_settings = GatewaySettings.from_env()

    def setUp(self) -> None:
        if importlib.util.find_spec("openai") is None:
            self.skipTest("The 'openai' package is not installed.")

        self.logical_model, self.expected_model = self._resolve_test_target()
        self.service = build_embedding_gateway_service(
            embedding_settings=self.embedding_settings,
            gateway_settings=self.gateway_settings,
        )

    def test_embed_with_env_config_and_print_result(self) -> None:
        request = EmbeddingBatchRequest(
            tenant_id="integration-tenant",
            app_id="integration-app",
            scene="knowledge_index",
            logical_model=self.logical_model,
            items=[
                EmbeddingInputItem(
                    chunk_id="chunk-1",
                    text="清明节机房安全巡检工作部署",
                    metadata={"source": "integration_test"},
                ),
                EmbeddingInputItem(
                    chunk_id="chunk-2",
                    text="文档解析模块需要支持缓存判重",
                    metadata={"source": "integration_test"},
                ),
            ],
        )

        result = self.service.embed(request)

        printable = result.model_dump(mode="json")
        for item in printable.get("items", []):
            item["vector"] = item["vector"][:8]
            item["vector_preview"] = True
        printable["raw_response"] = {
            "has_raw_response": result.raw_response is not None,
            "batch_count": len(result.raw_response.get("batches", []))
            if isinstance(result.raw_response, dict)
            else 0,
        }
        print("\n=== Embedding Result ===")
        print(json.dumps(printable, ensure_ascii=False, indent=2))
        print("=== End Embedding Result ===")

        self.assertEqual(result.final_model, self.expected_model)
        self.assertEqual(len(result.items), 2)
        self.assertGreater(result.dimension, 0)
        self.assertEqual(len(result.items[0].vector), result.dimension)
        self.assertTrue(all(item.vector for item in result.items))

    def _resolve_test_target(self) -> tuple[str | None, str]:
        public_proxy_enabled = self.embedding_settings.embedding_enable_public_proxy
        gateway_api_key = os.getenv("MODEL_GATEWAY_API_KEY", "").strip()
        if public_proxy_enabled and gateway_api_key and gateway_api_key != "change-me":
            return None, self.embedding_settings.embedding_default_public_model

        private_base_url = os.getenv("PRIVATE_EMBEDDING_BASE_URL", "").strip()
        private_api_key = os.getenv("PRIVATE_EMBEDDING_API_KEY", "").strip()
        private_model = os.getenv("PRIVATE_EMBEDDING_MODEL", "").strip()
        if private_base_url and private_api_key and private_api_key != "change-me" and private_model:
            return self.embedding_settings.private_embedding_logical_model, private_model

        self.skipTest(
            "Embedding integration is not configured. "
            "Set MODEL_GATEWAY_API_KEY for LiteLLM mode, or set "
            "PRIVATE_EMBEDDING_BASE_URL / PRIVATE_EMBEDDING_API_KEY / PRIVATE_EMBEDDING_MODEL "
            "for direct mode."
        )


if __name__ == "__main__":
    unittest.main()

# .\.venv\Scripts\python.exe -m unittest tests.integration.runtime.embedding.test_aliyun_text_embedding_v4_integration
