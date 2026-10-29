"""Base controller with DRY execute_method wrapper."""
from __future__ import annotations

import logging
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException

from .response_builder import ResponseBuilder

logger = logging.getLogger(__name__)


class BaseController:
    """Controller helpers: log + wrap service calls via ResponseBuilder."""

    response_builder = ResponseBuilder()

    async def execute_method(
        self,
        fun: Callable[..., Awaitable[Any]],
        payload: Any = None,
        *,
        success_msg: str,
        pass_payload: bool = True,
    ) -> dict[str, Any]:
        """Run ``fun``, return success envelope; unexpected errors → code_error.

        ``HTTPException`` is re-raised so FastAPI keeps normal HTTP status codes.
        """
        name = getattr(fun, "__name__", repr(fun))
        try:
            logger.info("linq360 execute_method start name=%s", name)
            if pass_payload and payload is not None:
                data = await fun(payload)
            elif pass_payload:
                data = await fun(None)
            else:
                data = await fun()
            logger.info("linq360 execute_method ok name=%s", name)
            return self.response_builder.success(success_msg, data)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(
                "linq360 execute_method error name=%s err=%s\n%s",
                name,
                exc,
                traceback.format_exc(),
            )
            return self.response_builder.code_error(str(exc))
