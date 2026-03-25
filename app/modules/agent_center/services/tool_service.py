from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.core.config import OCRSettings
from app.runtime.tools import ToolExecutor, build_default_tool_executor


class AgentToolService:
    def __init__(self, executor: ToolExecutor) -> None:
        self._executor = executor

    def execute_tool(
        self,
        tool_name: str,
        request: BaseModel | dict[str, Any],
    ) -> BaseModel:
        return self._executor.execute(tool_name, request)

    def list_tool_specs(self) -> list[dict[str, object]]:
        return self._executor.list_tool_specs()


def build_agent_tool_service(
    settings: OCRSettings | None = None,
    *,
    executor: ToolExecutor | None = None,
) -> AgentToolService:
    executor = executor or build_default_tool_executor(settings)
    return AgentToolService(executor)
