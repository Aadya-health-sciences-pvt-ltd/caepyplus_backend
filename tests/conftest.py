"""Pytest fixtures and configuration."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.app.core.config import get_settings

settings = get_settings()
from src.app.db.session import Base, get_db
from src.app.main import app

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


def _base64url_encode(data: bytes) -> str:
    """Encode bytes using base64 URL-safe encoding without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _create_test_jwt(
    subject: str = "+919999999999",
    doctor_id: int | None = 1,
    email: str | None = "admin@example.com",
    role: str = "admin",
    expire_minutes: int = 30,
) -> str:
    """Create a test JWT token for authentication in tests.
    
    Uses the same encoding logic as the production auth module.
    """
    secret = settings.SECRET_KEY
    algorithm = "HS256"

    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expire_minutes)

    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "doctor_id": doctor_id,
        "phone": subject,
        "email": email,
        "role": role,
    }

    header = {"alg": algorithm, "typ": "JWT"}

    header_json = json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    encoded_header = _base64url_encode(header_json)
    encoded_payload = _base64url_encode(payload_json)

    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    encoded_signature = _base64url_encode(signature)

    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"

# Test database URL (in-memory SQLite for tests)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Get authentication headers with a valid test JWT token."""
    token = _create_test_jwt()
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="function")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create a test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async_session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    """Create a test HTTP client with overridden dependencies.

    The admin user required by ``auth_headers`` is seeded here — in the same
    session factory used by ``override_get_db`` — so it is visible to all
    requests made through this client.  The previous ``setup_admin_user``
    autouse fixture used the separate ``db_session`` fixture whose transaction
    is rolled back before client requests run, making the admin user invisible.
    """
    from sqlalchemy import select as _select

    from src.app.models.enums import UserRole
    from src.app.models.user import User

    async_session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    # Seed the admin user once, committed so every subsequent request sees it.
    async with async_session_factory() as seed_session:
        result = await seed_session.execute(
            _select(User).where(User.phone == "+919999999999")
        )
        if result.scalar_one_or_none() is None:
            seed_session.add(
                User(
                    phone="+919999999999",
                    email="admin@example.com",
                    role=UserRole.ADMIN.value,
                    is_active=True,
                )
            )
            await seed_session.commit()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def sample_doctor_data() -> dict:
    """Sample doctor data for tests.
    
    Matches the current DoctorCreate schema.
    """
    return {
        "first_name": "John",
        "last_name": "Smith",
        "email": "john.smith@hospital.com",
        "phone_number": "+1-555-0123",
        "title": "Dr.",
        "gender": "Male",
        "primary_specialization": "Cardiology",
        "medical_registration_number": "MED-12345",
        "medical_council": "Medical Council of India",
        "registration_year": 2005,
        "registration_authority": "Medical Council",
        "years_of_experience": 15,
        "consultation_fee": 150.00,
        # qualifications is list[str] in current schema
        "qualifications": [
            "MBBS - Harvard Medical School (2005)",
            "MD Cardiology - Johns Hopkins (2008)",
        ],
        # practice_locations now uses PracticeLocationBase schema
        "practice_locations": [
            {
                "hospital_name": "City Hospital",
                "address": "123 Medical Center Drive",
                "city": "New York",
                "state": "NY",
                "phone_number": "+1-555-0100",
            }
        ],
    }

@pytest.fixture
def sample_update_data() -> dict:
    """Sample update data for tests."""
    return {
        "first_name": "Jonathan",
        "phone_number": "+1-555-9999",
        "years_of_experience": 16,
    }


@pytest.fixture
def mock_firebase(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock Firebase token verification to prevent actual API calls.

    ``verify_firebase_token`` is async — the mock must also be async so that
    ``await verify_firebase_token(...)`` in the Google Sign-In endpoint does
    not raise ``TypeError: object dict can't be used in 'await' expression``.
    """
    async def mock_verify_token(token: str) -> dict:
        return {
            "uid": "test_firebase_uid",
            "email": "test@example.com",
            "name": "Test User",
            "email_verified": True,
            "picture": "https://example.com/photo.jpg",
        }
    monkeypatch.setattr("src.app.core.firebase_config.verify_firebase_token", mock_verify_token)


@pytest.fixture
def mock_gemini() -> Generator[MagicMock, None, None]:
    """Mock Gemini service to prevent actual LLM generation calls."""
    with patch("src.app.services.gemini_service.GeminiService") as mock_cls:
        mock_instance = mock_cls.return_value
        mock_instance.generate.return_value = "Mocked generation response"
        mock_instance.generate_with_retry.return_value = "Mocked retry response"
        mock_instance.generate_structured.return_value = {"mocked_key": "mocked_value"}
        mock_instance.generate_with_vision.return_value = {"extracted_text": "Mocked OCR text"}

        # Patch the singleton getter
        with patch("src.app.services.gemini_service.get_gemini_service", return_value=mock_instance):
            yield mock_instance


@pytest.fixture
def mock_blob_storage() -> Generator[MagicMock, None, None]:
    """Mock Blob Storage service to prevent actual file I/O."""
    with patch("src.app.services.blob_storage_service.LocalBlobStorageService") as mock_cls:
        mock_instance = mock_cls.return_value

        # Setup AsyncMock for async methods
        mock_instance.upload_from_bytes = AsyncMock(return_value=MagicMock(
            success=True,
            blob_id="mock_blob_123",
            file_uri="/api/v1/blobs/mock_blob_123",
            file_size=1024,
            mime_type="image/jpeg",
            content_hash="mockhash",
            error_message=None
        ))
        mock_instance.upload_from_url = AsyncMock(return_value=MagicMock(
            success=True,
            blob_id="mock_blob_from_url_123",
            file_uri="/api/v1/blobs/mock_blob_from_url_123",
            file_size=2048,
            mime_type="application/pdf",
            content_hash="mockhash_url",
            error_message=None
        ))
        mock_instance.get_blob = AsyncMock(return_value=(b"mocked bytes", MagicMock(mime_type="image/jpeg")))
        mock_instance.delete_blob = AsyncMock(return_value=True)
        mock_instance.get_blob_uri = MagicMock(return_value="/api/v1/blobs/mock_blob_123")
        mock_instance.blob_exists = AsyncMock(return_value=True)

        yield mock_instance


