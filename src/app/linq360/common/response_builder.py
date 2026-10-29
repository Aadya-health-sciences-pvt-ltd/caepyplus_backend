"""Standard API envelope builder for LinQ360 (status_code / msg / data)."""
from __future__ import annotations

from typing import Any


class ResponseBuilder:
    """Map outcomes to the shared JSON envelope shape."""

    @staticmethod
    def success(msg: str, data: Any = None) -> dict[str, Any]:
        return {"status_code": 200, "msg": msg, "data": data}

    @staticmethod
    def warning(msg: str, data: Any = None) -> dict[str, Any]:
        return {"status_code": 401, "msg": msg, "data": data}

    @staticmethod
    def auth_error(msg: str, data: Any = None) -> dict[str, Any]:
        return {"status_code": 403, "msg": msg, "data": data}

    @staticmethod
    def code_error(msg: str, data: Any = None) -> dict[str, Any]:
        return {"status_code": 1000, "msg": msg, "data": data}

    def to_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        return payload
