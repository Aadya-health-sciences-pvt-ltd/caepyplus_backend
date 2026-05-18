"""
Resume Extraction Service.

Handles extraction of structured doctor information from uploaded
resumes (PDF, images) using Google Gemini Vision API.

Uses external prompts loaded via PromptManager (no hardcoded prompts).
"""
from __future__ import annotations

import logging
import time

from ..core.exceptions import ExtractionError, FileValidationError
from ..core.prompts import get_prompt_manager
from ..schemas.doctor import ResumeExtractedData
from .gemini_service import get_gemini_service

logger = logging.getLogger(__name__)


class ResumeExtractionService:
    """
    Service for extracting structured data from doctor resumes.
    
    Uses Gemini Vision API to process PDF and image documents,
    extracting professional information into a standardized format.
    
    All prompts are loaded from external configuration via PromptManager.
    """

    # Supported MIME types
    MIME_TYPES: dict[str, str] = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
    }

    def __init__(self) -> None:
        """Initialize with dependencies."""
        self.gemini = get_gemini_service()
        self.prompt_manager = get_prompt_manager()

    def _get_mime_type(self, filename: str) -> str:
        """
        Determine MIME type from filename extension.
        
        Args:
            filename: Original filename
            
        Returns:
            MIME type string
            
        Raises:
            FileValidationError: If file type is not supported
        """
        extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        mime_type = self.MIME_TYPES.get(extension)

        if not mime_type:
            raise FileValidationError(
                message=f"Unsupported file type: {extension}",
                filename=filename,
                allowed_types=list(self.MIME_TYPES.keys()),
            )

        return mime_type

    def _get_extraction_prompt(self) -> str:
        """
        Get the extraction prompt from external configuration.
        
        Combines system prompt, response schema, and instruction.
        """
        return self.prompt_manager.get_resume_extraction_prompt()

    async def extract_from_file(
        self,
        file_content: bytes,
        filename: str,
    ) -> tuple[ResumeExtractedData, float]:
        """
        Extract structured data from an uploaded resume file.
        
        Args:
            file_content: Raw bytes of the uploaded file
            filename: Original filename (used to determine MIME type)
            
        Returns:
            Tuple of (extracted_data, processing_time_ms)
            
        Raises:
            FileValidationError: If file type is not supported
            ExtractionError: If data extraction fails
            AIServiceError: If AI service is unavailable
        """
        start_time = time.time()

        mime_type = self._get_mime_type(filename)

        logger.info("Extracting data from %s (%s)", filename, mime_type)

        try:
            # Get prompt from external config
            extraction_prompt = self._get_extraction_prompt()

            # Call Gemini Vision API
            parsed_data = await self.gemini.generate_with_vision(
                prompt=extraction_prompt,
                file_content=file_content,
                mime_type=mime_type,
                temperature=0.1,  # Low temperature for consistent extraction
            )

            # Validate and create response object
            extracted_data = ResumeExtractedData(**parsed_data)

            processing_time = (time.time() - start_time) * 1000

            logger.info("Successfully extracted data from %s in %.2fms", filename, processing_time)

            return extracted_data, processing_time

        except ExtractionError:
            raise
        except Exception as e:
            logger.error("Failed to extract from %s: %s", filename, e)
            raise ExtractionError(
                message="Failed to extract data from resume",
                source="resume",
                details={"filename": filename, "error": str(e)},
            )

    async def extract_from_text(
        self,
        text_content: str,
    ) -> tuple[ResumeExtractedData, float]:
        """
        Extract structured data from plain text resume content.
        
        Useful for copy-pasted resume text or OCR results.
        
        Args:
            text_content: Plain text resume content
            
        Returns:
            Tuple of (extracted_data, processing_time_ms)
        """
        start_time = time.time()

        logger.info("Extracting from text (%d chars)", len(text_content))

        try:
            extraction_prompt = self._get_extraction_prompt()
            full_prompt = f"{extraction_prompt}\n\n---\n\nRESUME TEXT:\n{text_content}"

            parsed_data = await self.gemini.generate_structured(
                prompt=full_prompt,
                temperature=0.1,
            )

            extracted_data = ResumeExtractedData(**parsed_data)
            processing_time = (time.time() - start_time) * 1000

            logger.info("Text extraction completed in %.2fms", processing_time)

            return extracted_data, processing_time

        except ExtractionError:
            raise
        except Exception as e:
            logger.error("Text extraction failed: %s", e)
            raise ExtractionError(
                message="Failed to extract data from text",
                source="text",
                details={"error": str(e)},
            )


# Singleton instance
_extraction_service: ResumeExtractionService | None = None


def get_extraction_service() -> ResumeExtractionService:
    """Get the global extraction service instance."""
    global _extraction_service
    if _extraction_service is None:
        _extraction_service = ResumeExtractionService()
    return _extraction_service
