"""
Shared logger infrastructure for Caepy AI.

Mirrors the LoggerService pattern from the reference project:
- session_context: async-safe ContextVar that injects session/step info into every log record
- A ContextFilter that prepends [Step N | Session X] without any manual passing
- Format: YYYY-MM-DD HH:MM:SS [Step N | session_id] [LEVEL] module: message

Usage:
    from app.core.logger import logger, session_context

    # At the start of a WebSocket handler:
    session_context.set(f"Step {step} | {short_id}")

    # In any module:
    logger.info("[Tool] update_form called — keys: fullName, email")
"""

import logging
import sys
import os
import contextvars


# Async-safe context variable — set once per WebSocket connection.
# Value format: "Step N | <short_session_id>"
session_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "session_context", default=None
)


class _ContextFilter(logging.Filter):
    """Injects session context into every log record, if set."""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = session_context.get()
        record.session_id = f"[{ctx}]" if ctx else ""
        return True


class LoggerService:
    _logger: logging.Logger | None = None

    @classmethod
    def setup_logger(cls, name: str = "CaepyAI") -> logging.Logger:
        if cls._logger:
            return cls._logger

        logger = logging.getLogger(name)

        env_level = os.getenv("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, env_level, logging.INFO)
        logger.setLevel(level)

        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                "%(asctime)s %(session_id)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.addFilter(_ContextFilter())
            # Prevent propagation to root logger (avoids duplicate lines)
            logger.propagate = False

        # Suppress noisy websockets library DEBUG logs
        logging.getLogger("websockets").setLevel(logging.WARNING)

        cls._logger = logger
        return logger

    @classmethod
    def get_logger(cls) -> logging.Logger:
        if not cls._logger:
            return cls.setup_logger()
        return cls._logger


# Module-level export — import this everywhere
logger = LoggerService.get_logger()


# =============================================================================
# Global Cost Tracker
# Accumulates estimated AI spend across all sessions for the process lifetime.
# Thread-safe via threading.Lock (compatible with asyncio single-thread model).
# =============================================================================

import threading


class CostTracker:
    """
    Singleton that accumulates AI cost estimates across every session.

    Live Voice (GeminiLiveService):
        Prices per token (Vertex AI gemini-2.0-flash-live-001):
          Audio input  : $0.70  / 1M tokens  (1 tok = 1 280 bytes)
          Audio output : $2.10  / 1M tokens  (1 tok = 1 920 bytes)
          Text input   : $0.075 / 1M tokens  (~4 chars / token)

    Text / Vision calls (GeminiService):
        Priced at a flat estimate per call using reported or estimated tokens.
        gemini-2.0-flash pricing:
          Input  : $0.075 / 1M tokens
          Output : $0.300 / 1M tokens

    Usage:
        from app.core.logger import cost_tracker

        # After a Live session ends:
        cost_tracker.record_live_session(
            audio_in_bytes, audio_out_bytes, text_in_chars, duration_s
        )

        # After a text / vision call:
        cost_tracker.record_text_call(
            input_tokens=prompt_tokens, output_tokens=completion_tokens
        )
    """

    # Vertex AI Live pricing (USD per token)
    _AUDIO_IN_PER_TOKEN  = 0.70  / 1_000_000
    _AUDIO_OUT_PER_TOKEN = 2.10  / 1_000_000
    _TEXT_IN_PER_TOKEN   = 0.075 / 1_000_000

    # gemini-2.0-flash text/vision pricing (USD per token)
    _TEXT_CALL_IN_PER_TOKEN  = 0.075 / 1_000_000
    _TEXT_CALL_OUT_PER_TOKEN = 0.300 / 1_000_000

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Live session totals
        self.live_sessions:       int   = 0
        self.live_audio_in_bytes: int   = 0
        self.live_audio_out_bytes:int   = 0
        self.live_text_in_chars:  int   = 0
        self.live_duration_s:     float = 0.0
        self.live_cost_usd:       float = 0.0
        # Text / Vision call totals
        self.text_calls:          int   = 0
        self.text_input_tokens:   int   = 0
        self.text_output_tokens:  int   = 0
        self.text_cost_usd:       float = 0.0

    def record_live_session(
        self,
        audio_in_bytes: int,
        audio_out_bytes: int,
        text_in_chars: int,
        duration_s: float,
    ) -> float:
        """
        Record metrics for one completed Live Voice session.
        Returns the session cost in USD.
        """
        audio_in_tok  = audio_in_bytes  / 1_280
        audio_out_tok = audio_out_bytes / 1_920
        text_in_tok   = text_in_chars   / 4

        session_cost = (
            audio_in_tok  * self._AUDIO_IN_PER_TOKEN
            + audio_out_tok * self._AUDIO_OUT_PER_TOKEN
            + text_in_tok   * self._TEXT_IN_PER_TOKEN
        )

        with self._lock:
            self.live_sessions        += 1
            self.live_audio_in_bytes  += audio_in_bytes
            self.live_audio_out_bytes += audio_out_bytes
            self.live_text_in_chars   += text_in_chars
            self.live_duration_s      += duration_s
            self.live_cost_usd        += session_cost

        return session_cost

    def record_text_call(
        self,
        input_tokens: int,
        output_tokens: int = 0,
    ) -> float:
        """
        Record one text / vision Gemini call.
        Returns the call cost in USD.
        """
        call_cost = (
            input_tokens  * self._TEXT_CALL_IN_PER_TOKEN
            + output_tokens * self._TEXT_CALL_OUT_PER_TOKEN
        )
        with self._lock:
            self.text_calls         += 1
            self.text_input_tokens  += input_tokens
            self.text_output_tokens += output_tokens
            self.text_cost_usd      += call_cost

        return call_cost

    @property
    def total_cost_usd(self) -> float:
        return self.live_cost_usd + self.text_cost_usd

    def log_totals(self) -> None:
        """
        Emit a structured summary of all accumulated AI costs to the logger.
        Call this at shutdown or on a periodic basis.
        """
        _log = LoggerService.get_logger()
        total_audio_in_kb  = self.live_audio_in_bytes  / 1024
        total_audio_out_kb = self.live_audio_out_bytes / 1024
        total_audio_in_tok  = self.live_audio_in_bytes  / 1_280
        total_audio_out_tok = self.live_audio_out_bytes / 1_920
        total_text_in_tok   = self.live_text_in_chars   / 4

        _log.info(
            "[COST SUMMARY] ═══════════════════════════════════════"
        )
        _log.info(
            f"[COST SUMMARY] Live Sessions  : {self.live_sessions} session(s) | "
            f"total_duration={self.live_duration_s:.1f}s"
        )
        _log.info(
            f"[COST SUMMARY] Live Audio In  : {total_audio_in_kb:.1f} KB "
            f"(~{total_audio_in_tok:.0f} tok) — ${self.live_audio_in_bytes / 1_280 * self._AUDIO_IN_PER_TOKEN:.6f}"
        )
        _log.info(
            f"[COST SUMMARY] Live Audio Out : {total_audio_out_kb:.1f} KB "
            f"(~{total_audio_out_tok:.0f} tok) — ${self.live_audio_out_bytes / 1_920 * self._AUDIO_OUT_PER_TOKEN:.6f}"
        )
        _log.info(
            f"[COST SUMMARY] Live Text In   : {self.live_text_in_chars} chars "
            f"(~{total_text_in_tok:.0f} tok) — ${total_text_in_tok * self._TEXT_IN_PER_TOKEN:.6f}"
        )
        _log.info(
            f"[COST SUMMARY] Live Cost      : ${self.live_cost_usd:.6f} USD"
        )
        _log.info(
            f"[COST SUMMARY] Text/Vision    : {self.text_calls} call(s) | "
            f"in={self.text_input_tokens} tok | out={self.text_output_tokens} tok | "
            f"${self.text_cost_usd:.6f} USD"
        )
        _log.info(
            f"[COST SUMMARY] GRAND TOTAL    : ${self.total_cost_usd:.6f} USD"
        )
        _log.info(
            "[COST SUMMARY] ═══════════════════════════════════════"
        )


# Process-lifetime singleton
cost_tracker = CostTracker()
