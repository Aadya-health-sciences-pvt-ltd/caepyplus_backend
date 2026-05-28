"""
LinQMD Sync Service.

Production-grade service for syncing doctor profiles to the LinQMD platform.
Handles data transformation, file uploads, and error handling.

Features:
- Configurable endpoints (dev/prod)
- Automatic retry with exponential backoff
- Comprehensive error handling and logging
- Data transformation from internal schema to LinQMD format
"""
from __future__ import annotations

import logging
import secrets
import string
from dataclasses import dataclass, field
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from ..core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class LinQMDUserPayload:
    """Data structure for LinQMD user creation API payload."""
    
    # Required fields
    name: str  # Username for login
    mail: str  # Email address
    password: str  # User password
    fullname: str  # Display name
    phone_number: str
    
    # Professional info
    degree: str = ""  # Qualification/degree
    speciality: str = ""  # Primary specialization
    overview: str = ""  # Professional overview
    specialities_long: str = ""  # Detailed specialities
    expertise_summary: str = ""  # Summary of expertise
    education_details: str = ""  # Education details
    
    # Arrays of expertise items
    expertises: list[dict[str, str]] = field(default_factory=list)
    
    # YouTube videos
    youtube_videos: list[dict[str, str]] = field(default_factory=list)
    
    # Display picture (optional file path or bytes)
    display_picture_path: str | None = None

    # Practice hub theme (dp_1 | dp_2)
    theme: str = "dp_1"
    
    def to_form_data(self) -> dict[str, str]:
        """
        Convert to urlencoded data format expected by LinQMD API.
        
        Mandatory fields: name, mail, pass, theme
        Optional fields: fullname, phone_number, degree, speciality, overview, 
                        specialities_long, expertise_summary, education_details
        
        Returns:
            Dictionary ready for application/x-www-form-urlencoded submission
        """
        # Mandatory fields - always include these
        payload = {
            'name': self.name,
            'mail': self.mail,
            'pass': self.password,
            'theme': self.theme,
        }
        
        # Optional fields - only include if they have values
        optional_fields = {
            'fullname': self.fullname,
            'phone_number': self.phone_number,
            'degree': self.degree,
            'speciality': self.speciality,
            'overview': self.overview,
            'specialities_long': self.specialities_long,
            'expertise_summary': self.expertise_summary,
            'education_details': self.education_details,
        }
        
        # Add non-empty optional fields
        for key, value in optional_fields.items():
            if value:
                payload[key] = value
        
        return payload


@dataclass
class LinQMDSyncResult:
    """Result of a LinQMD sync operation."""
    
    success: bool
    doctor_id: int
    linqmd_response: dict[str, Any] | None = None
    error_message: str | None = None
    http_status_code: int | None = None


class LinQMDSyncService:
    """
    Service for syncing doctor data to LinQMD platform.
    
    Transforms internal doctor data format to LinQMD API format
    and handles the HTTP communication with proper error handling.
    
    Usage:
        service = get_linqmd_sync_service()
        result = await service.sync_doctor(doctor_identity, doctor_details)
    """
    
    def __init__(self) -> None:
        """Initialize the sync service with configuration."""
        self.settings = get_settings()
        self._client: httpx.AsyncClient | None = None
    
    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.settings.LINQMD_API_TIMEOUT,
                follow_redirects=True,
            )
        return self._client
    
    def _get_headers(self) -> dict[str, str]:
        """Build request headers for LinQMD API."""
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        
        # Auth token already includes "Basic " prefix from config
        if self.settings.LINQMD_PRACTICE_HUB_AUTH_TOKEN:
            headers['Authorization'] = self.settings.LINQMD_PRACTICE_HUB_AUTH_TOKEN
        
        if self.settings.LINQMD_PRACTICE_HUB_COOKIE:
            headers['Cookie'] = self.settings.LINQMD_PRACTICE_HUB_COOKIE
        
        return headers
    

    @staticmethod
    def _slug_field_segment(value: str) -> str:
        """Lowercase alphanumeric slug for a single field (speciality or location)."""
        return ''.join(c.lower() for c in (value or '').strip() if c.isalnum())

    _HONORIFIC_PREFIXES = frozenset({'dr', 'mr', 'mrs', 'ms', 'prof'})

    @classmethod
    def _slug_name_word_segments(cls, full_name: str) -> list[str]:
        """
        Split full name into hyphen-joined word segments.

        Honorifics (e.g. Dr) are merged with the following word:
        "Dr Murali Mohan Selvam" -> drmurali, mohan, selvam
        """
        raw_words = (full_name or '').split()
        segments: list[str] = []
        i = 0
        while i < len(raw_words):
            segment = ''.join(c.lower() for c in raw_words[i] if c.isalnum())
            if not segment:
                i += 1
                continue

            if (
                segment in cls._HONORIFIC_PREFIXES
                and i + 1 < len(raw_words)
            ):
                next_segment = ''.join(
                    c.lower() for c in raw_words[i + 1] if c.isalnum()
                )
                if next_segment:
                    segments.append(segment + next_segment)
                    i += 2
                    continue

            segments.append(segment)
            i += 1

        return segments

    def _generate_username(
        self,
        speciality: str,
        primary_location: str,
        full_name: str,
        email: str = '',
    ) -> str:
        """
        Generate LinQMD login username: speciality-primarylocation-drfullname.

        Example: Cardiology, Bangalore, "Dr Murali Mohan Selvam"
        -> cardiology-bangalore-drmurali-mohan-selvam
        """
        parts: list[str] = []

        spec = self._slug_field_segment(speciality)
        if spec:
            parts.append(spec)

        loc = self._slug_field_segment(primary_location)
        if loc:
            parts.append(loc)

        parts.extend(self._slug_name_word_segments(full_name))

        username = '-'.join(parts)
        if len(username) >= 3:
            return username

        # Fallback when required profile fields are missing
        if email and '@' in email:
            email_username = email.split('@')[0].lower()
            email_username = ''.join(
                c for c in email_username if c.isalnum() or c in '._-'
            )
            if len(email_username) >= 3:
                return email_username

        name_base = ''.join(c.lower() for c in (full_name or '') if c.isalnum())
        suffix = ''.join(secrets.choice(string.digits) for _ in range(4))
        return f"{name_base or 'doctor'}{suffix}"
    
    _LINQMD_TEMP_PASSWORD_SPECIALS = '!#'
    _LINQMD_PASSWORD_ADJECTIVES = (
        'Velvet', 'Crimson', 'Golden', 'Silver', 'Amber', 'Azure', 'Jade', 'Ivory',
        'Noble', 'Royal', 'Bright', 'Crystal', 'Pearl', 'Starlit', 'Radiant', 'Serene',
        'Alpine', 'Coastal', 'Lunar', 'Solar', 'Arctic', 'Floral', 'Mystic', 'Gentle',
        'Quiet', 'Swift', 'Clear', 'Sunset', 'Stellar', 'Opal', 'Satin', 'Copper',
    )
    _LINQMD_PASSWORD_NOUNS = (
        'Horizon', 'Summit', 'Meadow', 'Harbor', 'Canyon', 'Valley', 'Garden', 'Phoenix',
        'Marina', 'Prism', 'Orion', 'Cypress', 'Willow', 'Blossom', 'Cascade', 'Meridian',
        'Zephyr', 'Lotus', 'Echo', 'Nova', 'Comet', 'Ridge', 'Brook', 'Shore', 'Crest',
        'Gate', 'Bloom', 'Spark', 'Atlas', 'Falcon', 'Harbour', 'Aurora', 'Ember',
    )

    def _generate_password(self) -> str:
        """
        Generate a temporary LinQMD password.

        Format: {Adjective}{Noun}{digits}{special}
        Example: VelvetHorizon742!

        The word pair is randomized from memorable, name-like tokens (PascalCase).
        Special character is randomized from ! or # only.
        """
        prefix = (
            f'{secrets.choice(self._LINQMD_PASSWORD_ADJECTIVES)}'
            f'{secrets.choice(self._LINQMD_PASSWORD_NOUNS)}'
        )
        digits = ''.join(secrets.choice(string.digits) for _ in range(3))
        special = secrets.choice(self._LINQMD_TEMP_PASSWORD_SPECIALS)
        return f'{prefix}{digits}{special}'
    
    def transform_doctor_data(
        self,
        identity: dict[str, Any],
        details: dict[str, Any] | None = None,
        media: list[dict[str, Any]] | None = None,
    ) -> LinQMDUserPayload:
        """
        Transform internal doctor data to LinQMD API format.
        
        Args:
            identity: Doctor identity data (from doctor_identity table)
            details: Doctor details data (from doctor_details table)
            media: Doctor media files (from doctor_media table)
            
        Returns:
            LinQMDUserPayload ready for API submission
        """
        details = details or {}
        media = media or []
        
        # Get full name
        fullname = identity.get('full_name', '').strip()

        speciality = (
            details.get('speciality', '')
            or details.get('specialty', '')
            or identity.get('speciality', '')
            or identity.get('specialty', '')
            or ''
        )
        primary_location = (
            details.get('primary_practice_location', '')
            or details.get('primary_location', '')
            or identity.get('primary_practice_location', '')
            or ''
        )

        username = self._generate_username(
            speciality,
            primary_location,
            fullname,
            identity.get('email', ''),
        )

        # Format qualifications as degree string
        qualifications = details.get('qualifications', []) or []
        degree_parts = []
        for qual in qualifications:
            if isinstance(qual, dict):
                deg = qual.get('degree', '')
                if deg:
                    degree_parts.append(deg)
            elif isinstance(qual, str):
                degree_parts.append(qual)
        degree = ', '.join(degree_parts) if degree_parts else ''
        
        # Format education details
        education_lines = []
        for qual in qualifications:
            if isinstance(qual, dict):
                deg = qual.get('degree', '')
                inst = qual.get('institution', '')
                year = qual.get('year', '')
                if deg:
                    line = deg
                    if inst:
                        line += f" - {inst}"
                    if year:
                        line += f" ({year})"
                    education_lines.append(line)
            elif isinstance(qual, str):
                education_lines.append(qual)
        education_details = '\n'.join(education_lines)
        
        # Format specialities (speciality resolved above for username)
        if not speciality:
            speciality = details.get('speciality', '') or ''
        sub_specialities = details.get('sub_specialities', []) or []
        specialities_long = ', '.join([speciality] + sub_specialities) if sub_specialities else speciality
        
        # Build expertises array from areas_of_expertise
        expertises = []
        areas = details.get('areas_of_expertise', []) or []
        for area in areas:
            if isinstance(area, str) and area:
                expertises.append({
                    'head': area,
                    'content': f"Expert in {area}"  # Basic content
                })
        
        # Add conditions treated as expertises
        conditions = details.get('conditions_treated', []) or []
        for condition in conditions[:5]:  # Limit to 5
            if isinstance(condition, str) and condition:
                expertises.append({
                    'head': f"Treatment: {condition}",
                    'content': f"Specialized treatment for {condition}"
                })
        
        # Build expertise summary
        procedures = details.get('procedures_performed', []) or []
        expertise_parts = []
        if areas:
            expertise_parts.append(f"Areas of Expertise: {', '.join(areas[:5])}")
        if procedures:
            expertise_parts.append(f"Procedures: {', '.join(procedures[:5])}")
        expertise_summary = '\n'.join(expertise_parts)
        
        # Get overview/about text
        overview = details.get('professional_overview', '') or details.get('about_me', '') or ''
        
        return LinQMDUserPayload(
            name=username,
            mail=identity.get('email', ''),
            password=self._generate_password(),
            fullname=fullname,
            phone_number=identity.get('phone_number', ''),
            theme=secrets.choice(('dp_1', 'dp_2')),
            degree=degree,
            speciality=speciality,
            overview=overview,
            specialities_long=specialities_long,
            expertise_summary=expertise_summary,
            education_details=education_details,
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _send_to_linqmd(
        self,
        payload: LinQMDUserPayload,
    ) -> tuple[int, dict[str, Any]]:
        """
        Send user data to LinQMD API with retry logic.
        
        Args:
            payload: User data to send
            
        Returns:
            Tuple of (status_code, response_json)
        """
        form_data = payload.to_form_data()
        headers = self._get_headers()
        
        logger.info(f"Sending user to LinQMD: {payload.mail}")
        create_url = self.settings.linqmd_user_create_url
        logger.debug(f"LinQMD API URL: {create_url}")
        logger.debug(f"Request data: {form_data}")

        response = await self.client.post(
            create_url,
            data=form_data,
            headers=headers,
        )
        
        logger.info(f"LinQMD response: status={response.status_code}")
        
        try:
            response_json = response.json()
        except Exception:
            response_json = {"raw_response": response.text[:500]}

        if isinstance(response_json, dict):
            response_json = dict(response_json)
        else:
            response_json = {"raw_response": response_json}

        response_json["Username"] = payload.name
        response_json["Password"] = payload.password

        return response.status_code, response_json
    
    async def sync_doctor(
        self,
        identity: dict[str, Any],
        details: dict[str, Any] | None = None,
        media: list[dict[str, Any]] | None = None,
        doctor_id: int | None = None,
    ) -> LinQMDSyncResult:
        """
        Sync a doctor's data to LinQMD platform.
        
        Args:
            identity: Doctor identity data
            details: Doctor details data (optional)
            media: Doctor media files (optional)
            doctor_id: Internal doctor ID for tracking
            
        Returns:
            LinQMDSyncResult with success status and details
        """
        doctor_id = doctor_id or identity.get('doctor_id', 0)
        
        try:
            # Transform data to LinQMD format
            payload = self.transform_doctor_data(identity, details, media)
            
            # Send to LinQMD
            status_code, response_json = await self._send_to_linqmd(payload)
            
            # Check for success (2xx status codes, no error payload)
            success = 200 <= status_code < 300
            api_error = (
                response_json.get("error")
                if isinstance(response_json, dict)
                else None
            )
            if success and api_error:
                success = False

            if success:
                logger.info(f"Successfully synced doctor {doctor_id} to LinQMD")
            else:
                logger.error(f"Failed to sync doctor {doctor_id} to LinQMD: {response_json}")

            error_message: str | None = None
            if not success:
                if api_error:
                    error_message = str(api_error)
                elif isinstance(response_json, dict) and response_json.get("message"):
                    error_message = str(response_json["message"])
                else:
                    error_message = f"API returned status {status_code}"

            return LinQMDSyncResult(
                success=success,
                doctor_id=doctor_id,
                linqmd_response=response_json,
                http_status_code=status_code,
                error_message=error_message,
            )
            
        except httpx.TimeoutException as e:
            logger.error(f"Timeout syncing doctor {doctor_id} to LinQMD: {e}")
            return LinQMDSyncResult(
                success=False,
                doctor_id=doctor_id,
                error_message=f"Request timeout: {e}",
            )
        except httpx.ConnectError as e:
            logger.error(f"Connection error syncing doctor {doctor_id} to LinQMD: {e}")
            return LinQMDSyncResult(
                success=False,
                doctor_id=doctor_id,
                error_message=f"Connection error: {e}",
            )
        except Exception as e:
            logger.exception(f"Unexpected error syncing doctor {doctor_id} to LinQMD")
            return LinQMDSyncResult(
                success=False,
                doctor_id=doctor_id,
                error_message=f"Unexpected error: {str(e)}",
            )
    
    async def sync_doctor_by_id(
        self,
        doctor_id: int,
        db_session: Any,
    ) -> LinQMDSyncResult:
        """
        Sync a doctor to LinQMD by their internal ID.
        
        Fetches data from database and syncs.
        
        Args:
            doctor_id: Internal doctor ID
            db_session: Database session for fetching data
            
        Returns:
            LinQMDSyncResult
        """
        from ..repositories.onboarding_repository import OnboardingRepository
        
        repo = OnboardingRepository(db_session)
        
        # Fetch doctor data
        identity = await repo.get_identity_by_doctor_id(doctor_id)
        if not identity:
            return LinQMDSyncResult(
                success=False,
                doctor_id=doctor_id,
                error_message=f"Doctor with ID {doctor_id} not found",
            )
        
        from ..repositories.doctor_repository import DoctorRepository
        doc_repo = DoctorRepository(db_session)
        
        details = await doc_repo.get_by_id(doctor_id)
        media = await repo.list_media(doctor_id)
        
        # Convert ORM objects to dicts
        identity_dict = {
            'doctor_id': identity.doctor_id,
            'full_name': identity.full_name,
            'email': identity.email,
            'phone_number': identity.phone_number,
        }
        
        details_dict = None
        if details:
            details_dict = {
                'gender': getattr(details, 'gender', None),
                'speciality': getattr(
                    details,
                    'specialty',
                    getattr(details, 'speciality', getattr(details, 'primary_specialization', None)),
                ),
                'primary_practice_location': getattr(details, 'primary_practice_location', None),
                'sub_specialities': getattr(details, 'sub_specialities', []),
                'areas_of_expertise': getattr(details, 'areas_of_clinical_interest', []),
                'qualifications': getattr(details, 'qualifications', []),
                'professional_overview': getattr(details, 'professional_overview', getattr(details, 'professional_achievement', None)),
                'about_me': getattr(details, 'about_me', getattr(details, 'personal_achievement', None)),
                'conditions_treated': getattr(details, 'conditions_treated', []),
                'procedures_performed': getattr(details, 'procedures_performed', []),
                'external_links': getattr(details, 'external_links', {}),
            }
        
        media_list = []
        for m in media:
            media_list.append({
                'media_category': m.media_category,
                'file_uri': m.file_uri,
                'is_primary': m.is_primary,
            })
        
        return await self.sync_doctor(identity_dict, details_dict, media_list, doctor_id)


# -----------------------------------------------------------------------------
# Singleton Pattern
# -----------------------------------------------------------------------------

_linqmd_sync_service: LinQMDSyncService | None = None


def get_linqmd_sync_service() -> LinQMDSyncService:
    """Get the global LinQMD sync service instance."""
    global _linqmd_sync_service
    if _linqmd_sync_service is None:
        _linqmd_sync_service = LinQMDSyncService()
    return _linqmd_sync_service