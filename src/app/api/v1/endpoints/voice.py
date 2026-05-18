"""Voice Onboarding API Router."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, WebSocket
from pydantic import BaseModel, Field

from ....core.exceptions import SessionExpiredError, SessionNotFoundError
from ....core.rbac import CurrentUser
from ....services.voice_service import (
    VoiceOnboardingService,
    VoiceSession,
    get_voice_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/voice", tags=["Voice Onboarding"])


# ============================================================================
# Request/Response Models with Examples
# ============================================================================

class StartSessionRequest(BaseModel):
    """Request to start a new voice onboarding session."""
    language: str = Field(
        default="en",
        description="Language code for the conversation (e.g., 'en', 'es', 'hi')",
        examples=["en", "es", "hi"],
    )
    context: dict[str, Any] | None = Field(
        default=None,
        description="Optional context including field definitions for the current step",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"language": "en"},
                {"language": "es"},
            ]
        }
    }


class StartSessionResponse(BaseModel):
    """Response after starting a voice session."""
    session_id: str = Field(description="Unique session identifier (UUID)")
    status: str = Field(description="Current session status", examples=["active"])
    greeting: str = Field(description="AI greeting message to start the conversation")
    fields_total: int = Field(description="Total number of fields to collect")
    created_at: datetime = Field(description="Session creation timestamp")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "550e8400-e29b-41d4-a716-446655440000",
                    "status": "active",
                    "greeting": "Hello! I'm here to help you complete your doctor registration. Let's start with your full name. What should I call you?",
                    "fields_total": 8,
                    "created_at": "2026-01-11T09:30:00Z"
                }
            ]
        }
    }


class ChatRequest(BaseModel):
    """Request to send a message in the voice conversation."""
    session_id: str = Field(description="Session ID from start_session")
    user_transcript: str = Field(
        min_length=1,
        max_length=2000,
        description="User's speech transcript",
        examples=["My name is Dr. Sarah Johnson"],
    )
    context: dict[str, Any] | None = Field(
        default=None,
        description="Optional context including field definitions for the current step",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "550e8400-e29b-41d4-a716-446655440000",
                    "user_transcript": "My name is Dr. Sarah Johnson and I specialize in Cardiology"
                }
            ]
        }
    }


class FieldStatusItem(BaseModel):
    """Status of a single field in the collection process."""
    field_name: str = Field(description="Internal field identifier")
    display_name: str = Field(description="Human-readable field name")
    is_collected: bool = Field(description="Whether this field has been collected")
    value: Any | None = Field(default=None, description="Collected value, if any")
    confidence: float = Field(default=0.0, description="AI confidence score (0.0-1.0)")


class ChatResponse(BaseModel):
    """Response from the chat endpoint with AI reply and progress."""
    session_id: str = Field(description="Session identifier")
    status: str = Field(description="Current session status")
    ai_response: str = Field(description="AI's response message")
    fields_collected: int = Field(description="Number of fields collected so far")
    fields_total: int = Field(description="Total fields to collect")
    fields_status: list[FieldStatusItem] = Field(description="Status of each field")
    current_data: dict[str, Any] = Field(description="All collected data so far")
    is_complete: bool = Field(description="Whether all required fields are collected")
    turn_number: int = Field(description="Conversation turn count")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "550e8400-e29b-41d4-a716-446655440000",
                    "status": "active",
                    "ai_response": "Nice to meet you, Dr. Sarah Johnson! I see you specialize in Cardiology - that's great. Now, could you tell me your medical registration number?",
                    "fields_collected": 2,
                    "fields_total": 8,
                    "fields_status": [
                        {"field_name": "name", "display_name": "Full Name", "is_collected": True, "value": "Dr. Sarah Johnson", "confidence": 0.95},
                        {"field_name": "specialization", "display_name": "Specialization", "is_collected": True, "value": "Cardiology", "confidence": 0.92}
                    ],
                    "current_data": {"name": "Dr. Sarah Johnson", "specialization": "Cardiology"},
                    "is_complete": False,
                    "turn_number": 2
                }
            ]
        }
    }


class SessionStatusResponse(BaseModel):
    """Detailed session status response."""
    session_id: str
    status: str
    language: str
    fields_collected: int
    fields_total: int
    fields_status: list[FieldStatusItem]
    current_data: dict[str, Any]
    is_complete: bool
    turn_count: int
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


class FinalizeResponse(BaseModel):
    """Response after finalizing a completed session."""
    session_id: str = Field(description="Session identifier")
    success: bool = Field(description="Whether finalization was successful")
    message: str = Field(description="Status message")
    doctor_data: dict[str, Any] = Field(description="Complete doctor data ready for registration")
    confidence_scores: dict[str, float] = Field(description="Confidence score for each field")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "550e8400-e29b-41d4-a716-446655440000",
                    "success": True,
                    "message": "Session finalized successfully",
                    "doctor_data": {
                        "name": "Dr. Sarah Johnson",
                        "specialization": "Cardiology",
                        "medical_registration_number": "MED123456",
                        "email": "sarah.johnson@hospital.com"
                    },
                    "confidence_scores": {
                        "name": 0.95,
                        "specialization": 0.92,
                        "medical_registration_number": 0.98,
                        "email": 0.99
                    }
                }
            ]
        }
    }


VoiceServiceDep = Annotated[VoiceOnboardingService, Depends(get_voice_service)]


def build_fields_status(session: VoiceSession) -> list[FieldStatusItem]:
    active_config = session.get_active_config()
    return [
        FieldStatusItem(
            field_name=field_name,
            display_name=cfg["display"],
            is_collected=field_name in session.collected_fields,
            value=session.collected_data.get(field_name),
            confidence=session.field_confidence.get(field_name, 0.0),
        )
        for field_name, cfg in active_config.items()
    ]


# ============================================================================
# Voice Onboarding Endpoints
# ============================================================================

@router.post(
    "/start",
    response_model=StartSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="🎤 Start Voice Onboarding Session",
    description="""
Start a new voice-based doctor onboarding session.

**How it works:**
1. Call this endpoint to create a new session
2. Receive a greeting and session ID
3. Use the `/chat` endpoint to send user responses
4. Continue until all fields are collected
5. Call `/finalize` to complete registration

**Supported Languages:** English (en), Spanish (es), Hindi (hi)

**Session Expiry:** Sessions expire after 30 minutes of inactivity.
    """,
    responses={
        201: {"description": "Session created successfully"},
        503: {"description": "AI service unavailable"},
    },
)
async def start_session(
    request: StartSessionRequest,
    service: VoiceServiceDep,
    current_user: CurrentUser,
) -> StartSessionResponse:
    # Prepare initial data from user profile
    initial_data = {}
    # We only skip the phone number as it's the primary identifier.
    # The user wants the AI to ask for the email.
    if current_user.phone:
        initial_data["phone"] = current_user.phone

    session, greeting = await service.start_session(
        language=request.language,
        context=request.context,
        initial_data=initial_data
    )
    # Calculate fields total based on active config (context or default)
    active_config = session.get_active_config()
    return StartSessionResponse(
        session_id=session.session_id,
        status=session.status.value,
        greeting=greeting,
        fields_total=len(active_config),
        created_at=session.created_at,
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="💬 Send Message in Conversation",
    description="""
Send a user's speech transcript and receive an AI response.

**Process:**
1. User speaks → Speech-to-text converts to transcript
2. Send transcript to this endpoint
3. AI extracts data and responds with follow-up questions
4. Repeat until `is_complete` is `True`

**Tips:**
- The AI understands natural language, users can provide multiple pieces of information at once
- If the AI misunderstands, users can correct it in subsequent messages
- Check `fields_status` to see what has been collected

**Example Flow:**
```
User: "Hi, I'm Dr. Sarah Johnson, a cardiologist"
AI: "Nice to meet you, Dr. Johnson! I've noted your specialization as Cardiology. What's your medical registration number?"
```
    """,
    responses={
        200: {"description": "Message processed successfully"},
        404: {"description": "Session not found"},
        410: {"description": "Session expired"},
    },
)
async def process_chat(
    request: ChatRequest,
    service: VoiceServiceDep,
    current_user: CurrentUser,
) -> ChatResponse:
    try:
        session, ai_response = await service.process_message(
            session_id=request.session_id,
            user_message=request.user_transcript,
            context=request.context,
        )
        active_config = session.get_active_config()
        return ChatResponse(
            session_id=session.session_id,
            status=session.status.value,
            ai_response=ai_response,
            fields_collected=len(session.collected_fields),
            fields_total=len(active_config),
            fields_status=build_fields_status(session),
            current_data=session.collected_data,
            is_complete=session.is_complete,
            turn_number=session.turn_count,
        )
    except SessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    except SessionExpiredError:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Session expired")


@router.get(
    "/session/{session_id}",
    response_model=SessionStatusResponse,
    summary="📊 Get Session Status",
    description="""
Retrieve the current status of a voice onboarding session.

**Use this to:**
- Check which fields have been collected
- View the current collected data
- Verify session hasn't expired
- Resume an interrupted session

**Note:** Sessions expire 30 minutes after the last activity.
    """,
    responses={
        200: {"description": "Session status retrieved"},
        404: {"description": "Session not found"},
        410: {"description": "Session expired"},
    },
)
async def get_session_status(
    session_id: str,
    service: VoiceServiceDep,
    current_user: CurrentUser,
) -> SessionStatusResponse:
    try:
        session = await service.get_session_status(session_id)
        active_config = session.get_active_config()
        return SessionStatusResponse(
            session_id=session.session_id,
            status=session.status.value,
            language=session.language,
            fields_collected=len(session.collected_fields),
            fields_total=len(active_config),
            fields_status=build_fields_status(session),
            current_data=session.collected_data,
            is_complete=session.is_complete,
            turn_count=session.turn_count,
            created_at=session.created_at,
            updated_at=session.updated_at,
            expires_at=session.expires_at,
        )
    except SessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    except SessionExpiredError:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Session expired")


@router.post(
    "/session/{session_id}/finalize",
    response_model=FinalizeResponse,
    summary="✅ Finalize Completed Session",
    description="""
Finalize a completed voice onboarding session and get the doctor data.

**Requirements:**
- Session must have `is_complete: true` (all fields collected)
- Session must not be expired

**What happens:**
1. Validates all required fields are present
2. Formats data for doctor registration
3. Returns complete doctor data with confidence scores
4. Optionally creates doctor record in database

**Next Steps:**
- Use the returned `doctor_data` to create a doctor record via `POST /api/v1/doctors`
- Review fields with low confidence scores before submission
    """,
    responses={
        200: {"description": "Session finalized successfully"},
        400: {"description": "Session not complete - missing required fields"},
        404: {"description": "Session not found"},
        410: {"description": "Session expired"},
    },
)
async def finalize_session(
    session_id: str,
    service: VoiceServiceDep,
    current_user: CurrentUser,
) -> FinalizeResponse:
    try:
        session = await service.get_session_status(session_id)

        if not session.is_complete:
            # Get missing fields for better error message
            active_config = session.get_active_config()
            missing_fields = [
                active_config[field]["display"]
                for field in session.missing_fields
                if field in active_config and active_config[field]["required"]
            ]

            error_detail = {
                "error": "Session incomplete",
                "message": f"Missing {len(missing_fields)} required field(s)",
                "missing_fields": missing_fields,
                "fields_collected": len(session.collected_fields),
                "fields_required": len([f for f, cfg in active_config.items() if cfg["required"]]),
            }
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail
            )

        doctor_data = await service.finalize_session(session_id)
        return FinalizeResponse(
            session_id=session_id,
            success=True,
            message="Session finalized",
            doctor_data=doctor_data,
            confidence_scores=session.field_confidence,
        )
    except SessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    except SessionExpiredError:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Session expired")


@router.delete(
    "/session/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="🗑️ Cancel Session",
    description="""
Cancel and delete a voice onboarding session.

**Use this when:**
- User abandons the onboarding process
- Need to start fresh with a new session
- Cleaning up test sessions

**Note:** This action is irreversible. All collected data will be lost.
    """,
    responses={
        204: {"description": "Session cancelled successfully"},
        404: {"description": "Session not found"},
    },
)
async def cancel_session(
    session_id: str,
    service: VoiceServiceDep,
    current_user: CurrentUser,
) -> None:
    try:
        await service.cancel_session(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")


# Separate router for the WebSocket endpoint — it cannot use the router-level
# require_authentication dependency because that dependency accepts `Request`
# which is not available on WebSocket connections.
voice_ws_router = APIRouter(prefix="/voice", tags=["Voice Onboarding"])

@voice_ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, context: str = "{}"):
    """
    WebSocket endpoint for bidirectional audio streaming with Gemini Live API.
    Used by the frontend to send raw 16kHz PCM audio and receive 24kHz PCM audio.
    Token auth is handled via the ?token= query parameter sent by the frontend.
    """
    from ....services.gemini_live_service import GeminiLiveService
    from fastapi import WebSocketDisconnect
    import json
    
    await websocket.accept()
    logger.info("Voice WebSocket connection established.")
    
    try:
        parsed_context = json.loads(context)
    except:
        parsed_context = {}

    try:
        # Create Gemini service instance for this connection
        service = GeminiLiveService(websocket, context=parsed_context)
        
        # Start the bidirectional communication loop
        await service.run()
        
    except WebSocketDisconnect:
        logger.info("Voice WebSocket client disconnected")
    except Exception as e:
        logger.error(f"Error in Voice WebSocket connection: {e}", exc_info=True)
        try:
            await websocket.close()
        except:
            pass
