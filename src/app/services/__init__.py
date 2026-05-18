"""Services package - Business logic layer."""
from __future__ import annotations
# Lazy imports to avoid circular dependencies
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .blob_storage_service import LocalBlobStorageService, S3BlobStorageService
    from .extraction_service import ResumeExtractionService
    from .gemini_service import GeminiService
    from .prompt_session_service import PromptSessionService
    from .voice_service import VoiceOnboardingService
    from .linqmd_sync_service import LinQMDsyncService


def get_extraction_service() -> ResumeExtractionService:
    """Get the global extraction service instance."""
    from .extraction_service import get_extraction_service as _get
    return _get()


def get_gemini_service() -> GeminiService:
    """Get the global Gemini service instance."""
    from .gemini_service import get_gemini_service as _get
    return _get()


def get_voice_service() -> VoiceOnboardingService:
    """Get the global voice service instance."""
    from .voice_service import get_voice_service as _get
    return _get()


def get_blob_storage_service() -> LocalBlobStorageService | S3BlobStorageService:
    """Get the global blob storage service instance."""
    from .blob_storage_service import get_blob_storage_service as _get
    return _get()


def get_prompt_session_service() -> PromptSessionService:
    """Get the global prompt session service instance."""
    from .prompt_session_service import get_prompt_session_service as _get
    return _get()

def get_linqmd_sync_service():
    """Get the global LinQMD sync service instance."""
    from .linqmd_sync_service import get_linqmd_sync_service as _get
    return _get()



__all__ = [
    "get_extraction_service",
    "get_gemini_service",
    "get_voice_service",
    "get_blob_storage_service",
    "get_prompt_session_service",
    "get_linqmd_sync_service",
]
