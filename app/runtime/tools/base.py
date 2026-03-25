from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.exceptions import OCRToolValidationError


class BaseRuntimeTool(ABC):
    name: str
    description: str = ""
    request_model: type[BaseModel]
    result_model: type[BaseModel] | None = None

    def parse_request(self, payload: BaseModel | dict[str, Any]) -> BaseModel:
        if isinstance(payload, self.request_model):
            return payload
        try:
            return self.request_model.model_validate(payload)
        except ValidationError as exc:  # pragma: no cover - exercised through executor
            raise OCRToolValidationError(str(exc)) from exc

    def build_tool_spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.request_model.model_json_schema(),
            },
        }

    @abstractmethod
    def execute(self, request: BaseModel) -> BaseModel:
        raise NotImplementedError
