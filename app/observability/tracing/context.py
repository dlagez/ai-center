from __future__ import annotations

import os


def detect_runtime_environment() -> str:
    for key in ("APP_ENV", "ENVIRONMENT", "ENV"):
        value = os.getenv(key)
        if value and value.strip():
            return value.strip()
    return "dev"
