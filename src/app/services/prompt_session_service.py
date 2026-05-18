"""
Prompt Session Service.

Production-grade service for tracking prompt variant usage per doctor/session.
Implements round-robin selection to ensure variety when users refresh content.

Features:
- In-memory session tracking (can be swapped for Redis in distributed setup)
- Thread-safe operations with async locks
- Automatic cleanup of stale sessions
- Configurable variant count and TTL
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Default TTL for session data (24 hours)
DEFAULT_SESSION_TTL_SECONDS = 86400

# Number of prompt variants per section
PROMPT_VARIANT_COUNT = 3


@dataclass
class PromptUsageRecord:
    """Tracks which prompt variants have been used for a specific section."""

    used_variants: list[int] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    cycle_count: int = 0  # Track how many full cycles completed

    def get_next_variant(self, total_variants: int = PROMPT_VARIANT_COUNT) -> int:
        """
        Get the next unused variant index using round-robin.
        
        Args:
            total_variants: Total number of variants available
            
        Returns:
            Index of the next variant to use (0-indexed)
        """
        self.last_accessed = time.time()

        # Find unused variants within the current cycle window
        if len(self.used_variants) < total_variants:
            available = [i for i in range(total_variants) if i not in self.used_variants]
        else:
            last_cycle = self.used_variants[-(len(self.used_variants) % total_variants or total_variants):]
            available = [i for i in range(total_variants) if i not in last_cycle]

        if not available:
            # All variants used in this cycle — start a new one
            self.cycle_count += 1
            available = list(range(total_variants))
            logger.info("Starting cycle %s, all %s variants available", self.cycle_count + 1, total_variants)

        next_variant = available[0]
        self.used_variants.append(next_variant)
        return next_variant

    def is_expired(self, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS) -> bool:
        """Check if this record has expired."""
        return (time.time() - self.last_accessed) > ttl_seconds


@dataclass
class DoctorPromptSession:
    """
    Tracks prompt usage across all sections for a single doctor.
    
    Structure: section_name -> PromptUsageRecord
    """

    sections: dict[str, PromptUsageRecord] = field(default_factory=dict)
    doctor_identifier: str = ""
    created_at: float = field(default_factory=time.time)

    def get_section_record(self, section: str) -> PromptUsageRecord:
        """Get or create a usage record for a section."""
        if section not in self.sections:
            self.sections[section] = PromptUsageRecord()
        return self.sections[section]

    def get_next_variant_for_section(
        self,
        section: str,
        total_variants: int = PROMPT_VARIANT_COUNT,
    ) -> int:
        """Get the next variant index for a specific section."""
        record = self.get_section_record(section)
        return record.get_next_variant(total_variants)


class PromptSessionService:
    """
    Service for managing prompt variant sessions.
    
    Provides thread-safe tracking of which prompt variants have been used
    per doctor, enabling variety when users refresh generated content.
    
    For production distributed systems, this can be swapped for a
    Redis-backed implementation with the same interface.
    
    Usage:
        service = get_prompt_session_service()
        variant_idx = await service.get_next_variant("doctor_123", "professional_overview")
        # variant_idx will be 0, 1, or 2, cycling through unused variants
    """

    def __init__(self, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS) -> None:
        """
        Initialize the session service.
        
        Args:
            ttl_seconds: Time-to-live for session data
        """
        self._sessions: dict[str, DoctorPromptSession] = {}
        self._lock = asyncio.Lock()
        self._ttl_seconds = ttl_seconds
        self._last_cleanup = time.time()
        self._cleanup_interval = 3600  # Run cleanup every hour

        logger.info("PromptSessionService initialized with TTL=%ss", ttl_seconds)

    async def get_next_variant(
        self,
        doctor_identifier: str,
        section: str,
        total_variants: int = PROMPT_VARIANT_COUNT,
    ) -> int:
        """
        Get the next unused prompt variant for a doctor and section.
        
        Args:
            doctor_identifier: Unique identifier for the doctor (email, ID, etc.)
            section: Content section name (professional_overview, about_me, etc.)
            total_variants: Number of variants available
            
        Returns:
            Index of the next variant to use (0-indexed)
        """
        async with self._lock:
            # Lazy cleanup
            await self._maybe_cleanup()

            # Get or create session
            if doctor_identifier not in self._sessions:
                self._sessions[doctor_identifier] = DoctorPromptSession(
                    doctor_identifier=doctor_identifier
                )
                logger.debug("Created new prompt session for: %s", doctor_identifier)

            session = self._sessions[doctor_identifier]
            variant_idx = session.get_next_variant_for_section(section, total_variants)

            logger.info(
                "Prompt variant selected: doctor=%s, section=%s, variant=%s/%s",
                doctor_identifier, section, variant_idx + 1, total_variants
            )

            return variant_idx

    async def get_session_stats(self, doctor_identifier: str) -> dict[str, Any] | None:
        """Get usage statistics for a doctor's session."""
        async with self._lock:
            if doctor_identifier not in self._sessions:
                return None
            session = self._sessions[doctor_identifier]
            return {
                "doctor_identifier": session.doctor_identifier,
                "created_at": session.created_at,
                "sections": {
                    section: {
                        "used_variants": record.used_variants,
                        "total_calls": len(record.used_variants),
                        "cycle_count": record.cycle_count,
                    }
                    for section, record in session.sections.items()
                },
            }

    async def clear_session(self, doctor_identifier: str) -> bool:
        """
        Clear a doctor's session (reset variant tracking).
        
        Useful when doctor explicitly wants to start fresh.
        
        Returns:
            True if session existed and was cleared
        """
        async with self._lock:
            if doctor_identifier in self._sessions:
                del self._sessions[doctor_identifier]
                logger.info("Cleared prompt session for: %s", doctor_identifier)
                return True
            return False

    async def clear_section(self, doctor_identifier: str, section: str) -> bool:
        """
        Clear variant tracking for a specific section only.
        
        Returns:
            True if section existed and was cleared
        """
        async with self._lock:
            if doctor_identifier in self._sessions:
                session = self._sessions[doctor_identifier]
                if section in session.sections:
                    del session.sections[section]
                    logger.info("Cleared section %s for: %s", section, doctor_identifier)
                    return True
            return False

    async def get_all_sessions_count(self) -> int:
        """Return the number of active (non-expired) sessions.

        Useful for tests, health checks, and debugging memory usage.
        """
        async with self._lock:
            return sum(
                1 for session in self._sessions.values()
                if not all(
                    record.is_expired(self._ttl_seconds)
                    for record in session.sections.values()
                )
            )

    async def _maybe_cleanup(self) -> None:
        """Run cleanup if enough time has passed since last cleanup."""
        if (time.time() - self._last_cleanup) < self._cleanup_interval:
            return

        await self._cleanup_expired_sessions()
        self._last_cleanup = time.time()

    async def _cleanup_expired_sessions(self) -> None:
        """Remove expired sessions to prevent memory leaks."""
        expired = [
            doc_id for doc_id, session in self._sessions.items()
            if all(
                record.is_expired(self._ttl_seconds)
                for record in session.sections.values()
            )
            or not session.sections  # Empty sessions
        ]

        for doc_id in expired:
            del self._sessions[doc_id]

        if expired:
            logger.info("Cleaned up %s expired prompt sessions", len(expired))


# -----------------------------------------------------------------------------
# Singleton Pattern
# -----------------------------------------------------------------------------

_prompt_session_service: PromptSessionService | None = None


def get_prompt_session_service() -> PromptSessionService:
    """Get the global prompt session service instance."""
    global _prompt_session_service
    if _prompt_session_service is None:
        _prompt_session_service = PromptSessionService()
    return _prompt_session_service

