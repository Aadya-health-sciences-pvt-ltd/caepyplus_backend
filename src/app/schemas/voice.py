"""
Voice Session Schemas.

Pydantic schemas for voice onboarding session management.
"""
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(UTC)


class SessionStatus(str, Enum):
    """Voice session lifecycle status."""
    ACTIVE = "active"
    COLLECTING = "collecting"
    CONFIRMING = "confirming"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ConversationRole(str, Enum):
    """Role in conversation."""
    SYSTEM = "system"
    ASSISTANT = "assistant"
    USER = "user"


class ConversationMessage(BaseModel):
    """A single message in the conversation."""
    role: ConversationRole
    content: str
    timestamp: datetime = Field(default_factory=_utc_now)


class FieldStatus(BaseModel):
    """Status of a single field in extraction."""
    field_name: str
    display_name: str
    value: Any = None
    is_collected: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_confirmation: bool = False


# ============================================
# Request Schemas
# ============================================

class VoiceSessionCreate(BaseModel):
    """Request to start a new voice session."""
    language: str = Field(default="en", description="Primary language for conversation")


class ProcessSpeechRequest(BaseModel):
    """Request to process user speech."""
    session_id: str = Field(description="Session identifier")
    user_text: str = Field(min_length=1, description="Transcribed speech text")
    audio_duration_ms: int | None = Field(default=None, ge=0, description="Audio duration for analytics")


class CompleteSessionRequest(BaseModel):
    """Request to complete a session."""
    session_id: str
    confirm: bool = Field(default=True, description="User confirms the data is correct")


# ============================================
# Response Schemas
# ============================================

class VoiceSessionResponse(BaseModel):
    """Response with session details."""
    session_id: str
    status: SessionStatus
    greeting_message: str
    greeting_audio_text: str
    fields_collected: int
    fields_total: int
    fields_status: list[FieldStatus]
    created_at: datetime


class ProcessSpeechResponse(BaseModel):
    """Response after processing user speech."""
    session_id: str
    status: SessionStatus
    ai_response: str
    ai_response_audio_text: str
    fields_collected: int
    fields_total: int
    fields_updated: list[str]
    missing_fields: list[str]
    needs_followup: bool
    is_complete: bool
    extracted_data: dict[str, Any] | None = None


class SessionStatusResponse(BaseModel):
    """Response with current session status."""
    session_id: str
    status: SessionStatus
    fields_collected: int
    fields_total: int
    fields_status: list[FieldStatus]
    collected_data: dict[str, Any] = Field(default_factory=dict)
    is_complete: bool
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


class CompleteSessionResponse(BaseModel):
    """Response after completing a session."""
    session_id: str
    success: bool
    message: str
    extracted_data: dict[str, Any] | None = None
    thank_you_message: str


class ExtractedDataResponse(BaseModel):
    """Response with extracted data from voice session."""
    session_id: str
    success: bool
    data: dict[str, Any] | None = None
    fields_collected: int
    fields_total: int
    missing_fields: list[str]


# ============================================
# Internal Models
# ============================================

class VoiceSession(BaseModel):
    """Internal voice session model (not exposed via API)."""
    model_config = ConfigDict(use_enum_values=True)

    session_id: str
    status: SessionStatus = SessionStatus.ACTIVE
    language: str = "en"
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
    extracted_data: dict[str, Any] = Field(default_factory=dict)
    fields_status: dict[str, FieldStatus] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
