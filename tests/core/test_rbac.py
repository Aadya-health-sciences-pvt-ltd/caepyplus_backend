"""Tests for Role-Based Access Control (RBAC) dependencies."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

from src.app.core.config import Settings
from src.app.core.exceptions import ForbiddenError, UnauthorizedError
from src.app.core.rbac import (
    _parse_jwt_doctor_id,
    get_current_user,
    require_admin,
    require_admin_or_operation,
    require_content_creator,
)
from src.app.models.enums import UserRole
from src.app.models.user import User


@pytest.fixture
def mock_settings():
    return Settings(SECRET_KEY="test-secret-key-that-is-at-least-32-characters", ENVIRONMENT="development")

@pytest.fixture
def active_user():
    return User(
        id=1,
        phone="+919999999999",
        role=UserRole.USER.value,
        is_active=True,
    )

@pytest.fixture
def inactive_user():
    return User(
        id=2,
        phone="+918888888888",
        role=UserRole.USER.value,
        is_active=False,
    )

@pytest.fixture
def admin_user():
    return User(
        id=3,
        phone="+917777777777",
        role=UserRole.ADMIN.value,
        is_active=True,
    )

@pytest.fixture
def operational_user():
    return User(
        id=4,
        phone="+916666666666",
        role=UserRole.OPERATION.value,
        is_active=True,
    )

@pytest.fixture
def content_creator_user():
    return User(
        id=5,
        phone="+919888888888",
        role=UserRole.CONTENT_CREATOR.value,
        is_active=True,
    )

@pytest.fixture
def valid_token_payload():
    return {"sub": "+919999999999", "exp": 9999999999}

# --- get_current_user tests ---

@pytest.mark.asyncio
async def test_get_current_user_success(mock_settings, active_user, valid_token_payload):
    request = MagicMock(spec=Request)
    request.headers.get.return_value = "Bearer valid_token"

    with patch("src.app.core.rbac._decode_jwt", return_value=valid_token_payload):
        with patch("src.app.core.rbac.UserRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_phone = AsyncMock(return_value=active_user)

            user = await get_current_user(request=request, settings=mock_settings, db=MagicMock())
            assert user.id == active_user.id

@pytest.mark.asyncio
async def test_get_current_user_missing_header(mock_settings):
    request = MagicMock(spec=Request)
    request.headers.get.return_value = None

    with pytest.raises(UnauthorizedError) as exc:
        await get_current_user(request=request, settings=mock_settings, db=MagicMock())
    assert "Authorization header" in str(exc.value)

@pytest.mark.asyncio
async def test_get_current_user_invalid_scheme(mock_settings):
    request = MagicMock(spec=Request)
    request.headers.get.return_value = "Basic something"

    with pytest.raises(UnauthorizedError):
        await get_current_user(request=request, settings=mock_settings, db=MagicMock())

@pytest.mark.asyncio
async def test_get_current_user_no_token(mock_settings):
    request = MagicMock(spec=Request)
    request.headers.get.return_value = "Bearer "

    with pytest.raises(UnauthorizedError):
        await get_current_user(request=request, settings=mock_settings, db=MagicMock())

@pytest.mark.asyncio
async def test_get_current_user_invalid_sub(mock_settings):
    request = MagicMock(spec=Request)
    request.headers.get.return_value = "Bearer valid_token"

    with patch("src.app.core.rbac._decode_jwt", return_value={"sub": None}):
        with pytest.raises(UnauthorizedError) as exc:
            await get_current_user(request=request, settings=mock_settings, db=MagicMock())
        assert "subject" in str(exc.value)

@pytest.mark.asyncio
async def test_get_current_user_not_in_db(mock_settings, valid_token_payload):
    request = MagicMock(spec=Request)
    request.headers.get.return_value = "Bearer valid_token"

    with patch("src.app.core.rbac._decode_jwt", return_value=valid_token_payload):
        with patch("src.app.core.rbac.UserRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_phone = AsyncMock(return_value=None)

            with pytest.raises(UnauthorizedError) as exc:
                await get_current_user(request=request, settings=mock_settings, db=MagicMock())
            assert "not found" in str(exc.value).lower()

@pytest.mark.asyncio
async def test_get_current_user_inactive(mock_settings, inactive_user, valid_token_payload):
    request = MagicMock(spec=Request)
    request.headers.get.return_value = "Bearer valid_token"
    valid_token_payload["sub"] = inactive_user.phone

    with patch("src.app.core.rbac._decode_jwt", return_value=valid_token_payload):
        with patch("src.app.core.rbac.UserRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_phone = AsyncMock(return_value=inactive_user)

            with pytest.raises(ForbiddenError) as exc:
                await get_current_user(request=request, settings=mock_settings, db=MagicMock())
            assert "deactivated" in str(exc.value)

# --- Role requirement tests ---

@pytest.mark.asyncio
async def test_require_admin_success(admin_user):
    user = await require_admin(current_user=admin_user)
    assert user.id == admin_user.id

@pytest.mark.asyncio
async def test_require_admin_failure(active_user, operational_user):
    with pytest.raises(ForbiddenError):
        await require_admin(current_user=active_user)
    with pytest.raises(ForbiddenError):
        await require_admin(current_user=operational_user)

@pytest.mark.asyncio
async def test_require_admin_or_operation_success(admin_user, operational_user):
    user = await require_admin_or_operation(current_user=admin_user)
    assert user.id == admin_user.id

    user = await require_admin_or_operation(current_user=operational_user)
    assert user.id == operational_user.id

@pytest.mark.asyncio
async def test_require_admin_or_operation_failure(active_user):
    with pytest.raises(ForbiddenError):
        await require_admin_or_operation(current_user=active_user)


@pytest.mark.asyncio
async def test_require_content_creator_success(content_creator_user):
    user = await require_content_creator(current_user=content_creator_user)
    assert user.id == content_creator_user.id


@pytest.mark.asyncio
async def test_require_content_creator_failure(admin_user, operational_user, active_user):
    with pytest.raises(ForbiddenError):
        await require_content_creator(current_user=admin_user)
    with pytest.raises(ForbiddenError):
        await require_content_creator(current_user=operational_user)
    with pytest.raises(ForbiddenError):
        await require_content_creator(current_user=active_user)


# --- JWT doctor_id parsing ---


class TestParseJwtDoctorId:
    def test_none_returns_none(self):
        assert _parse_jwt_doctor_id(None) is None

    def test_positive_int(self):
        assert _parse_jwt_doctor_id(42) == 42

    def test_numeric_string(self):
        assert _parse_jwt_doctor_id("  7 ") == 7

    def test_zero_and_negative_rejected(self):
        assert _parse_jwt_doctor_id(0) is None
        assert _parse_jwt_doctor_id(-3) is None

    def test_bool_rejected(self):
        assert _parse_jwt_doctor_id(True) is None

    def test_whole_float_accepted(self):
        assert _parse_jwt_doctor_id(12.0) == 12

    def test_non_numeric_string_rejected(self):
        assert _parse_jwt_doctor_id("abc") is None


@pytest.mark.asyncio
async def test_get_current_user_resolves_email_subject(mock_settings, active_user):
    request = MagicMock(spec=Request)
    request.headers.get.return_value = "Bearer valid_token"
    request.url.path = "/api/v1/test"
    active_user.email = "doctor@gmail.com"

    with patch("src.app.core.rbac._decode_jwt", return_value={"sub": "doctor@gmail.com"}):
        with patch("src.app.core.rbac.UserRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_email = AsyncMock(return_value=active_user)

            user = await get_current_user(request=request, settings=mock_settings, db=MagicMock())
            assert user.id == active_user.id
            mock_repo_instance.get_by_email.assert_awaited_once_with("doctor@gmail.com")


@pytest.mark.asyncio
async def test_get_current_user_falls_back_to_doctor_id(mock_settings, active_user):
    request = MagicMock(spec=Request)
    request.headers.get.return_value = "Bearer valid_token"
    request.url.path = "/api/v1/test"

    with patch(
        "src.app.core.rbac._decode_jwt",
        return_value={"sub": "doctor@gmail.com", "doctor_id": "15"},
    ):
        with patch("src.app.core.rbac.UserRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_email = AsyncMock(return_value=None)
            mock_repo_instance.get_by_doctor_id = AsyncMock(return_value=active_user)

            user = await get_current_user(request=request, settings=mock_settings, db=MagicMock())
            assert user.id == active_user.id
            mock_repo_instance.get_by_doctor_id.assert_awaited_once_with(15)

