from __future__ import annotations

import os
import unittest

from app.core.config import GatewaySettings
from app.runtime.llm.gateway_service import build_gateway_service
from app.runtime.llm.schemas import LLMInvokeRequest


def _load_dotenv_if_present() -> None:
    env_path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(env_path):
        return

    with open(env_path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


class GatewayServiceAlibabaIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _load_dotenv_if_present()

    def test_invoke_chat_with_alibaba_dashscope(self) -> None:
        required_keys = (
            "PRIVATE_LLM_BASE_URL",
            "PRIVATE_LLM_API_KEY",
            "PRIVATE_LLM_MODEL",
            "PRIVATE_LLM_LOGICAL_MODEL",
        )
        missing_keys = [key for key in required_keys if not os.getenv(key)]
        if missing_keys:
            self.skipTest(
                "Missing required environment variables: "
                + ", ".join(missing_keys)
            )

        settings = GatewaySettings.from_env()
        service = build_gateway_service(settings=settings)
        request = LLMInvokeRequest(
            tenant_id="integration-tenant",
            app_id="integration-app",
            scene="chat",
            task_type="chat",
            logical_model=settings.private_llm_logical_model,
            messages=[
                {
                    "role": "user",
                    "content": "请只回复 OK，不要输出其他内容。",
                }
            ],
            temperature=0.1,
            timeout_ms=30000,
        )

        result = service.invoke_chat(request)

        self.assertEqual(result.final_channel, "direct")
        self.assertEqual(result.final_provider, "private_llm")
        self.assertEqual(result.final_model, settings.private_llm_model)
        self.assertIsNotNone(result.content)
        self.assertTrue(result.content.strip())

class GatewayServiceAlibabaIntegrationTestCase2(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _load_dotenv_if_present()

    def test_invoke_chat_with_alibaba_dashscope(self) -> None:
        required_keys = (
            "PRIVATE_LLM_BASE_URL",
            "PRIVATE_LLM_API_KEY",
            "PRIVATE_LLM_MODEL",
            "PRIVATE_LLM_LOGICAL_MODEL",
        )
        missing_keys = [key for key in required_keys if not os.getenv(key)]
        if missing_keys:
            self.skipTest(
                "Missing required environment variables: "
                + ", ".join(missing_keys)
            )

        settings = GatewaySettings.from_env()
        service = build_gateway_service(settings=settings)
        request = LLMInvokeRequest(
            tenant_id="integration-tenant",
            app_id="integration-app",
            scene="chat",
            task_type="chat",
            logical_model=settings.private_llm_logical_model,
            messages=[
                {
                    "role": "user",
                    "content": "请只回复 OK，不要输出其他内容。",
                }
            ],
            temperature=0.1,
            timeout_ms=30000,
        )

        result = service.invoke_chat(request)

        self.assertEqual(result.final_channel, "direct")
        self.assertEqual(result.final_provider, "private_llm")
        self.assertEqual(result.final_model, settings.private_llm_model)
        self.assertIsNotNone(result.content)
        self.assertTrue(result.content.strip())


if __name__ == "__main__":
    unittest.main()


# python -m unittest tests.unit.runtime.llm.test_gateway_service_alibaba_integration.GatewayServiceAlibabaIntegrationTestCase.test_invoke_chat_with_alibaba_dashscope
# 测试阿里模型接口是否可以调用。
