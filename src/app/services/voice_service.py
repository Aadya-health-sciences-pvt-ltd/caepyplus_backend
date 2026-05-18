"""
Voice Onboarding Service.

Production-grade stateful conversation service for voice-based doctor registration.
Implements a state machine pattern for managing multi-turn conversations.

Architecture:
    - VoiceSession: Immutable session state container
    - SessionStore: Pluggable storage backend (In-Memory)
    - VoiceOnboardingService: Business logic orchestrator
    - Integration with GeminiService for AI responses

Design Patterns:
    - State Machine: Session lifecycle management
    - Repository: Session storage abstraction
    - Strategy: Pluggable AI providers
    - Builder: Session state construction
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Protocol

from ..core.exceptions import (
    AIServiceError,
    ExtractionError,
    SessionExpiredError,
    SessionNotFoundError,
)
from ..core.prompts import PromptManager, get_prompt_manager
from .gemini_service import GeminiService, get_gemini_service

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class SessionStatus(str, Enum):
    """Voice session lifecycle states."""
    INITIATED = "initiated"      # Session created, greeting sent
    COLLECTING = "collecting"    # Actively collecting fields
    CONFIRMING = "confirming"    # All fields collected, awaiting confirmation
    COMPLETED = "completed"      # User confirmed, ready for handover
    CANCELLED = "cancelled"      # User cancelled
    EXPIRED = "expired"          # Session timed out
    ERROR = "error"              # Unrecoverable error


class RequiredField(str, Enum):
    """Fields required for voice onboarding completion."""
    FULL_NAME = "full_name"
    PRIMARY_SPECIALIZATION = "primary_specialization"
    YEARS_OF_EXPERIENCE = "years_of_experience"
    MEDICAL_REGISTRATION_NUMBER = "medical_registration_number"
    EMAIL = "email"
    PHONE_NUMBER = "phone_number"
    LANGUAGES = "languages"


# Field collection order and metadata
FIELD_CONFIG: dict[str, dict[str, Any]] = {
    RequiredField.FULL_NAME.value: {
        "display": "Full Name",
        "order": 1,
        "required": True,
        "validator": lambda x: bool(x and len(str(x).strip()) >= 2),
    },
    RequiredField.PRIMARY_SPECIALIZATION.value: {
        "display": "Specialization",
        "order": 2,
        "required": True,
        "validator": lambda x: bool(x and len(str(x).strip()) >= 3),
    },
    RequiredField.YEARS_OF_EXPERIENCE.value: {
        "display": "Years of Experience",
        "order": 3,
        "required": True,
        "validator": lambda x: x is not None and (isinstance(x, int) or str(x).isdigit()),
    },
    RequiredField.MEDICAL_REGISTRATION_NUMBER.value: {
        "display": "Registration Number",
        "order": 4,
        "required": True,
        "validator": lambda x: bool(x and len(str(x).strip()) >= 4),
    },
    RequiredField.EMAIL.value: {
        "display": "Email Address",
        "order": 5,
        "required": True,
        "validator": lambda x: bool(x and "@" in str(x) and "." in str(x)),
    },
    RequiredField.PHONE_NUMBER.value: {
        "display": "Phone Number",
        "order": 6,
        "required": True,
        "validator": lambda x: bool(x and sum(c.isdigit() for c in str(x)) >= 10),
    },
    RequiredField.LANGUAGES.value: {
        "display": "Languages",
        "order": 7,
        "required": False,
        "validator": lambda x: True,  # Optional field
    },
}

SESSION_TIMEOUT_MINUTES = 30


# =============================================================================
# DATA CLASSES
# =============================================================================

def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(UTC)


@dataclass
class ConversationTurn:
    """Single turn in the conversation."""
    turn_number: int
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=_utc_now)
    extracted_fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class VoiceSession:
    """
    Immutable voice session state container.
    
    All mutations create a new instance (functional approach).
    """
    session_id: str
    status: SessionStatus
    language: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    turn_count: int
    collected_data: dict[str, Any]
    field_confidence: dict[str, float]
    conversation_history: list[ConversationTurn]
    current_field: str | None
    last_ai_response: str
    metadata: dict[str, Any]

    @classmethod
    def create(cls, language: str = "en") -> VoiceSession:
        """Factory method to create a new session."""
        now = datetime.now(UTC)
        session_id = f"voice_{uuid.uuid4().hex[:16]}"

        return cls(
            session_id=session_id,
            status=SessionStatus.INITIATED,
            language=language,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(minutes=SESSION_TIMEOUT_MINUTES),
            turn_count=0,
            collected_data={},
            field_confidence={},
            conversation_history=[],
            current_field=RequiredField.FULL_NAME.value,
            last_ai_response="",
            metadata={},
        )

    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        return datetime.now(UTC) > self.expires_at

    def get_active_config(self) -> dict[str, dict[str, Any]]:
        """
        Get active field configuration.
        Prioritizes context-specific fields from metadata over global defaults.
        """
        context_fields = self.metadata.get("context", {}).get("fields")
        if context_fields:
            return {
                f["key"]: {
                    "display": f["label"],
                    "order": i + 1,
                    "required": f.get("required", False),
                    "validator": lambda x: True,  # Trust AI extraction for dynamic fields
                }
                for i, f in enumerate(context_fields)
            }
        return FIELD_CONFIG

    @property
    def collected_fields(self) -> list[str]:
        """List of successfully collected field names."""
        config = self.get_active_config()
        return [
            f for f, cfg in config.items()
            if f in self.collected_data and cfg["validator"](self.collected_data[f])
        ]

    @property
    def missing_fields(self) -> list[str]:
        """List of required fields not yet collected."""
        config = self.get_active_config()
        return [
            f for f, cfg in config.items()
            if cfg["required"] and f not in self.collected_fields
        ]

    @property
    def is_complete(self) -> bool:
        """Check if all required fields are collected."""
        return len(self.missing_fields) == 0

    @property
    def next_field(self) -> str | None:
        """Get the next field to collect based on order."""
        missing = self.missing_fields
        if not missing:
            return None

        config = self.get_active_config()
        # Sort by order and return first
        sorted_missing = sorted(
            missing,
            key=lambda f: config[f]["order"]
        )
        return sorted_missing[0] if sorted_missing else None

    def with_update(self, **kwargs: Any) -> VoiceSession:
        """Create a new session with updated fields (immutable update)."""
        data = {
            "session_id": self.session_id,
            "status": kwargs.get("status", self.status),
            "language": self.language,
            "created_at": self.created_at,
            "updated_at": datetime.now(UTC),
            "expires_at": kwargs.get("expires_at", self.expires_at),
            "turn_count": kwargs.get("turn_count", self.turn_count),
            "collected_data": kwargs.get("collected_data", self.collected_data.copy()),
            "field_confidence": kwargs.get("field_confidence", self.field_confidence.copy()),
            "conversation_history": kwargs.get("conversation_history", self.conversation_history.copy()),
            "current_field": kwargs.get("current_field", self.current_field),
            "last_ai_response": kwargs.get("last_ai_response", self.last_ai_response),
            "metadata": kwargs.get("metadata", self.metadata.copy()),
        }
        return VoiceSession(**data)

    def extend_expiry(self) -> VoiceSession:
        """Extend session expiry time."""
        return self.with_update(
            expires_at=datetime.now(UTC) + timedelta(minutes=SESSION_TIMEOUT_MINUTES)
        )


# =============================================================================
# SESSION STORAGE ABSTRACTION
# =============================================================================

class SessionStore(Protocol):
    """Protocol for session storage backends."""

    async def get(self, session_id: str) -> VoiceSession | None:
        """Retrieve a session by ID."""
        ...

    async def save(self, session: VoiceSession) -> None:
        """Save or update a session."""
        ...

    async def delete(self, session_id: str) -> None:
        """Delete a session."""
        ...

    async def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count removed."""
        ...


class InMemorySessionStore:
    """
    In-memory session storage.

    Suitable for single-worker deployments only.

    WARNING: With multiple uvicorn workers (WEB_CONCURRENCY > 1) each worker
    process has its own independent in-memory store. A session created by
    worker-A is NOT visible to worker-B, causing ``SessionNotFoundError`` in
    round-robin load-balanced environments.

    For multi-worker production, replace with a Redis-backed or
    database-backed ``SessionStore`` implementation that is shared across
    all worker processes.
    """

    def __init__(self) -> None:
        import os as _os
        _workers = int(_os.environ.get("WEB_CONCURRENCY", "1"))
        if _workers > 1:
            logger.warning(
                "InMemorySessionStore: WEB_CONCURRENCY=%d — voice sessions are "
                "NOT shared across workers. Use a Redis-backed store in production.",
                _workers,
            )
        self._sessions: dict[str, VoiceSession] = {}

    async def get(self, session_id: str) -> VoiceSession | None:
        """Retrieve a session by ID."""
        return self._sessions.get(session_id)

    async def save(self, session: VoiceSession) -> None:
        """Save or update a session."""
        self._sessions[session.session_id] = session

    async def delete(self, session_id: str) -> None:
        """Delete a session."""
        self._sessions.pop(session_id, None)

    async def cleanup_expired(self) -> int:
        """Remove expired sessions."""
        expired = [
            sid for sid, session in self._sessions.items()
            if session.is_expired
        ]
        for sid in expired:
            del self._sessions[sid]

        if expired:
            logger.info("Cleaned up %d expired voice sessions", len(expired))

        return len(expired)


# =============================================================================
# AI RESPONSE PARSER
# =============================================================================

@dataclass
class AIExtractionResult:
    """Parsed result from AI extraction."""
    extracted_fields: dict[str, Any]
    corrections: dict[str, Any]
    response_text: str
    next_field: str | None
    confidence: dict[str, float]
    needs_clarification: bool
    clarification_field: str | None
    is_complete: bool
    raw_response: dict[str, Any]


def parse_ai_response(response: dict[str, Any]) -> AIExtractionResult:
    """Parse and validate AI response."""
    return AIExtractionResult(
        extracted_fields=response.get("extracted_fields", {}),
        corrections=response.get("corrections", {}),
        response_text=response.get("response_text", ""),
        next_field=response.get("next_field"),
        confidence=response.get("confidence", {}),
        needs_clarification=response.get("needs_clarification", False),
        clarification_field=response.get("clarification_field"),
        is_complete=response.get("is_complete", False),
        raw_response=response,
    )


# =============================================================================
# VOICE ONBOARDING SERVICE
# =============================================================================

class VoiceOnboardingService:
    """
    Production-grade service for voice-based doctor onboarding.
    
    Responsibilities:
        - Session lifecycle management
        - AI-powered field extraction
        - Conversation flow orchestration
        - Data transformation for handover
    
    Usage:
        service = get_voice_service()
        
        # Start session
        session, greeting = await service.start_session("en")
        
        # Process user input
        session, response = await service.process_message(
            session.session_id, 
            "I'm Dr. John Smith"
        )
        
        # Get final data
        doctor_data = await service.finalize_session(session.session_id)
    """

    def __init__(
        self,
        gemini: GeminiService | None = None,
        prompts: PromptManager | None = None,
        store: SessionStore | None = None,
    ) -> None:
        """
        Initialize with dependencies.
        
        Args:
            gemini: AI service for extraction/response generation
            prompts: Prompt manager for loading prompts
            store: Session storage backend
        """
        self.gemini = gemini or get_gemini_service()
        self.prompts = prompts or get_prompt_manager()
        self.store = store or InMemorySessionStore()

    async def _get_session(self, session_id: str) -> VoiceSession:
        """
        Retrieve and validate a session.
        
        Raises:
            SessionNotFoundError: Session doesn't exist
            SessionExpiredError: Session has expired
        """
        session = await self.store.get(session_id)

        if session is None:
            raise SessionNotFoundError(session_id=session_id)

        if session.is_expired:
            session = session.with_update(status=SessionStatus.EXPIRED)
            await self.store.save(session)
            raise SessionExpiredError(session_id=session_id)

        return session

    async def start_session(
        self,
        language: str = "en",
        context: dict[str, Any] | None = None,
        initial_data: dict[str, Any] | None = None,
    ) -> tuple[VoiceSession, str]:
        """
        Start a new voice onboarding session.
        
        Args:
            language: Primary conversation language
            context: Optional context including dynamic field definitions
            initial_data: Optional pre-collected data (e.g., from user profile)
            
        Returns:
            Tuple of (session, greeting_text)
        """
        # Create new session via the immutable factory method
        session = VoiceSession.create(language=language)

        # Apply context and initial data immutably via with_update() — never
        # mutate the dataclass fields in-place, as that breaks the functional
        # state-machine contract documented in VoiceSession's docstring.
        if context or initial_data:
            new_meta = {**session.metadata}
            if context:
                new_meta["context"] = context

            new_data = dict(session.collected_data)
            if initial_data:
                new_data.update(initial_data)

            # Derive next_field from a temporary view of the updated state
            temp = session.with_update(collected_data=new_data, metadata=new_meta)

            session = session.with_update(
                collected_data=new_data,
                metadata=new_meta,
                current_field=temp.next_field,
            )

        # Get greeting from prompts
        greeting = self.prompts.get("voice_onboarding.greeting")

        # Add greeting to conversation history
        turn = ConversationTurn(
            turn_number=0,
            role="assistant",
            content=greeting,
        )

        session = session.with_update(
            status=SessionStatus.COLLECTING,
            conversation_history=[turn],
            last_ai_response=greeting,
            turn_count=1,
        )

        # Save session
        await self.store.save(session)

        logger.info("Started voice session: %s with context keys: %s", session.session_id, list((context or {}).keys()))

        return session, greeting

    async def process_message(
        self,
        session_id: str,
        user_message: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[VoiceSession, str]:
        """
        Process user message and generate AI response.
        
        Args:
            session_id: Session identifier
            user_message: Transcribed user speech
            context: Optional context including dynamic field definitions
            
        Returns:
            Tuple of (Updated Session, AI Response)
        """
        # This is the core conversation loop:
        # 1. Retrieve session state
        # 2. Build context prompt
        # 3. Call AI for extraction + response
        # 4. Update session state
        # 5. Return response
        # Get and validate session
        session = await self._get_session(session_id)
        session = session.extend_expiry()

        # Add user message to history
        user_turn = ConversationTurn(
            turn_number=session.turn_count,
            role="user",
            content=user_message,
        )

        history = session.conversation_history + [user_turn]

        # Build the mediator prompt
        prompt = self._build_mediator_prompt(session, user_message)

        try:
            # Call Gemini for extraction and response
            ai_result = await self._call_ai_mediator(prompt)

            # Update collected data
            new_data = session.collected_data.copy()
            new_confidence = session.field_confidence.copy()

            # Get active config for validation
            active_config = session.get_active_config()

            # Apply extractions
            for field_name, value in ai_result.extracted_fields.items():
                if field_name in active_config and value is not None:
                    # Validate before accepting
                    if active_config[field_name]["validator"](value):
                        new_data[field_name] = self._normalize_value(field_name, value)
                        new_confidence[field_name] = ai_result.confidence.get(field_name, 0.8)
                        logger.debug("Extracted %s: %s", field_name, value)

            # Apply corrections
            for field_name, value in ai_result.corrections.items():
                if field_name in active_config and value is not None:
                    new_data[field_name] = self._normalize_value(field_name, value)
                    new_confidence[field_name] = ai_result.confidence.get(field_name, 0.9)
                    logger.debug("Corrected %s: %s", field_name, value)

            # Add AI response to history
            ai_turn = ConversationTurn(
                turn_number=session.turn_count + 1,
                role="assistant",
                content=ai_result.response_text,
                extracted_fields=ai_result.extracted_fields,
            )

            history = history + [ai_turn]

            # Determine new status
            new_status = session.status
            temp_session = session.with_update(collected_data=new_data)

            if temp_session.is_complete:
                new_status = SessionStatus.CONFIRMING

            # Build updated session
            session = session.with_update(
                status=new_status,
                collected_data=new_data,
                field_confidence=new_confidence,
                conversation_history=history,
                current_field=ai_result.next_field or temp_session.next_field,
                last_ai_response=ai_result.response_text,
                turn_count=session.turn_count + 2,
            )

            # Save updated session
            await self.store.save(session)

            logger.info(
                f"Session {session_id}: turn {session.turn_count}, "
                f"collected {len(session.collected_fields)}/{len(active_config)}"
            )

            return session, ai_result.response_text

        except (AIServiceError, ExtractionError) as e:
            logger.error("AI error in session %s: %s", session_id, e)

            # Generate fallback response
            fallback = self.prompts.get(
                "voice_onboarding.errors.ai_error",
                default="I'm having trouble understanding. Could you please repeat that?"
            )

            # Add fallback to history
            ai_turn = ConversationTurn(
                turn_number=session.turn_count + 1,
                role="assistant",
                content=fallback,
            )

            session = session.with_update(
                conversation_history=history + [ai_turn],
                last_ai_response=fallback,
                turn_count=session.turn_count + 2,
            )

            await self.store.save(session)

            return session, fallback

    async def get_session_status(self, session_id: str) -> VoiceSession:
        """
        Get current session status.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Current session state
        """
        return await self._get_session(session_id)

    async def finalize_session(self, session_id: str) -> dict[str, Any]:
        """
        Finalize session and return data for handover.
        
        Transforms collected voice data into the format expected
        by the Doctor creation endpoint.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Doctor data dict ready for POST /doctors
        """
        session = await self._get_session(session_id)

        # Mark as completed
        session = session.with_update(status=SessionStatus.COMPLETED)
        await self.store.save(session)

        # Transform to doctor creation format
        doctor_data = self._transform_to_doctor_data(session)

        logger.info("Finalized voice session: %s", session_id)

        return doctor_data

    async def cancel_session(self, session_id: str) -> None:
        """Cancel and delete a session."""
        session = await self._get_session(session_id)
        session = session.with_update(status=SessionStatus.CANCELLED)
        await self.store.delete(session_id)
        logger.info("Cancelled voice session: %s", session_id)

    def _build_mediator_prompt(self, session: VoiceSession, user_message: str) -> str:
        """Build the AI mediator prompt with current context."""
        # Format current data for prompt
        current_data_str = json.dumps(session.collected_data, indent=2) if session.collected_data else "{}"

        # Get the mediator prompt template
        template = self.prompts.get("voice_onboarding.mediator_prompt")

        # Fill in the template
        prompt = template.format(
            session_id=session.session_id,
            collected_fields=", ".join(session.collected_fields) or "None",
            missing_fields=", ".join(session.missing_fields) or "None",
            turn_number=session.turn_count,
            current_data=current_data_str,
            user_message=user_message,
        )

        return prompt

    async def _call_ai_mediator(self, prompt: str) -> AIExtractionResult:
        """Call Gemini and parse the response."""
        response = await self.gemini.generate_structured(
            prompt=prompt,
            temperature=0.3,  # Lower temperature for consistent extraction
        )

        return parse_ai_response(response)

    def _normalize_value(self, field_name: str, value: Any) -> Any:
        """Normalize extracted values by field type."""
        # Handle explicitly known fields first
        if field_name == RequiredField.YEARS_OF_EXPERIENCE.value:
            # Convert to integer
            if isinstance(value, str):
                # Handle "15 years" -> 15
                digits = "".join(c for c in value if c.isdigit())
                return int(digits) if digits else None
            return int(value) if value is not None else None

        if field_name == RequiredField.LANGUAGES.value:
            # Ensure it's a list
            if isinstance(value, str):
                return [lang.strip() for lang in value.split(",")]
            return value if isinstance(value, list) else [value]

        if field_name == RequiredField.EMAIL.value:
            # Lowercase and strip
            return str(value).lower().strip() if value else None

        if field_name == RequiredField.PHONE_NUMBER.value:
            # Keep only digits and + for country code
            if value:
                cleaned = "".join(c for c in str(value) if c.isdigit() or c == "+")
                return cleaned
            return None

        # Generic handling for other fields
        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            return value

        # Default: strip strings
        return str(value).strip() if value else value

    def _transform_to_doctor_data(self, session: VoiceSession) -> dict[str, Any]:
        """Transform voice data to doctor creation schema."""
        data = session.collected_data

        # Get languages as list
        languages = data.get("languages", [])
        if isinstance(languages, str):
            languages = [lang.strip() for lang in languages.split(",")]

        return {
            "full_name": data.get("full_name", ""),
            "email": data.get("email"),
            "phone_number": data.get("phone_number"),
            "primary_specialization": data.get("primary_specialization", ""),
            "years_of_experience": data.get("years_of_experience"),
            "medical_registration_number": data.get("medical_registration_number", ""),
            "languages": languages,
            "onboarding_source": "voice",
            "qualifications": [],
            "practice_locations": [],
            "awards_recognition": [],
            "memberships": [],
            "raw_extraction_data": {
                "voice_session_id": session.session_id,
                "collected_at": session.updated_at.isoformat(),
                "confidence_scores": session.field_confidence,
            },
        }


# =============================================================================
# SINGLETON FACTORY
# =============================================================================

_voice_service: VoiceOnboardingService | None = None


def get_voice_service() -> VoiceOnboardingService:
    """Get the global voice service instance (singleton)."""
    global _voice_service
    if _voice_service is None:
        _voice_service = VoiceOnboardingService()
    return _voice_service


def reset_voice_service() -> None:
    """Reset the singleton (for testing)."""
    global _voice_service
    _voice_service = None
