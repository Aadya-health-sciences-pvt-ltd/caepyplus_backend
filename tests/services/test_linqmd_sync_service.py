"""Unit tests for LinQMD sync service (mocked HTTP, no external calls)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.app.services.linqmd_sync_service import (
    LinQMDSyncResult,
    LinQMDSyncService,
    LinQMDUserPayload,
)


@pytest.fixture
def sync_service() -> LinQMDSyncService:
    return LinQMDSyncService()


def _identity() -> dict:
    return {
        "doctor_id": 5,
        "full_name": "Dr Anjali Sharma",
        "email": "anjali@example.com",
        "phone_number": "+919876543210",
        "profile_photo": None,
    }


def _details() -> dict:
    return {
        "speciality": "Cardiology",
        "primary_practice_location": "Bangalore",
        "qualifications": ["MBBS", "MD"],
        "years_of_clinical_experience": 12,
    }


class TestPostUserMultipart:
    @pytest.mark.asyncio
    async def test_create_posts_form_fields_and_attaches_credentials(
        self, sync_service: LinQMDSyncService
    ):
        payload = LinQMDUserPayload(
            name="cardiology-bangalore-dranjali",
            mail="anjali@example.com",
            password="TempPass123!",
            fullname="Dr Anjali Sharma",
            phone_number="+919876543210",
            speciality="Cardiology",
            theme="dp_1",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"uid": "88"}

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        sync_service._client = mock_client
        status, body = await sync_service._post_user_multipart(
                "https://linqmd.example/create",
                payload,
                include_theme=True,
                attach_credentials_to_response=True,
            )

        assert status == 200
        assert body["uid"] == "88"
        assert body["Username"] == "cardiology-bangalore-dranjali"
        assert body["Password"] == "TempPass123!"
        call_kwargs = mock_client.post.await_args.kwargs
        assert call_kwargs["data"]["name"] == "cardiology-bangalore-dranjali"
        assert call_kwargs["data"]["theme"] == "dp_1"
        assert "pass" in call_kwargs["data"]

    @pytest.mark.asyncio
    async def test_create_with_display_picture_sends_multipart_file(
        self, sync_service: LinQMDSyncService
    ):
        payload = LinQMDUserPayload(
            name="user",
            mail="u@example.com",
            password="pass",
            fullname="Name",
            phone_number="+911111111111",
            display_picture_file=("profile.jpg", b"\xff\xd8\xff", "image/jpeg"),
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"uid": "1"}

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        sync_service._client = mock_client
        await sync_service._post_user_multipart(
            "https://linqmd.example/create",
            payload,
            include_theme=True,
            attach_credentials_to_response=True,
        )

        call_kwargs = mock_client.post.await_args.kwargs
        assert call_kwargs["files"]["displayPicture"] == (
            "profile.jpg",
            b"\xff\xd8\xff",
            "image/jpeg",
        )

    @pytest.mark.asyncio
    async def test_update_omits_theme_and_credentials(
        self, sync_service: LinQMDSyncService
    ):
        payload = LinQMDUserPayload(
            name="user",
            mail="u@example.com",
            password="pass",
            fullname="Name",
            phone_number="+911111111111",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        sync_service._client = mock_client
        _, body = await sync_service._post_user_multipart(
            "https://linqmd.example/update/99",
            payload,
            include_theme=False,
            attach_credentials_to_response=False,
        )

        assert "Username" not in body
        assert "Password" not in body
        assert "theme" not in mock_client.post.await_args.kwargs["data"]


def _mock_overview_service(overview_text: str = "AI generated overview text."):
    mock_svc = MagicMock()
    mock_svc.generate_with_fallback = AsyncMock(return_value=overview_text)
    return patch(
        "src.app.services.linqmd_overview_service.get_linqmd_overview_service",
        return_value=mock_svc,
    )


class TestSyncDoctor:
    @pytest.mark.asyncio
    async def test_sync_doctor_success(self, sync_service: LinQMDSyncService):
        with patch.object(
            sync_service,
            "_load_display_picture_file",
            new=AsyncMock(return_value=None),
        ):
            with _mock_overview_service():
                with patch.object(
                    sync_service,
                    "_send_to_linqmd",
                    new=AsyncMock(
                        return_value=(
                            200,
                            {
                                "uid": "42",
                                "Username": "cardiology-bangalore-dranjali",
                                "Password": "pw",
                            },
                        ),
                    ),
                ):
                    result = await sync_service.sync_doctor(
                        _identity(), _details(), doctor_id=5
                    )

        assert result.success is True
        assert result.doctor_id == 5
        assert result.linqmd_response["uid"] == "42"

    @pytest.mark.asyncio
    async def test_sync_doctor_includes_overview_in_create_payload(
        self, sync_service: LinQMDSyncService
    ):
        overview = (
            "Dr. Anjali Sharma is a distinguished cardiologist with extensive "
            "experience providing compassionate care to patients across Bangalore."
        )
        with patch.object(
            sync_service,
            "_load_display_picture_file",
            new=AsyncMock(return_value=None),
        ):
            with _mock_overview_service(overview):
                with patch.object(
                    sync_service,
                    "_send_to_linqmd",
                    new=AsyncMock(return_value=(200, {"uid": "42"})),
                ) as mock_send:
                    await sync_service.sync_doctor(_identity(), _details(), doctor_id=5)

        sent_payload = mock_send.await_args.args[0]
        assert sent_payload.overview == overview

    @pytest.mark.asyncio
    async def test_sync_doctor_persists_overview_on_success(
        self, sync_service: LinQMDSyncService
    ):
        overview = "Dr. Test is a skilled specialist with years of experience."
        mock_db = MagicMock()
        with patch.object(
            sync_service,
            "_load_display_picture_file",
            new=AsyncMock(return_value=None),
        ):
            with _mock_overview_service(overview):
                with patch.object(
                    sync_service,
                    "_send_to_linqmd",
                    new=AsyncMock(return_value=(200, {"uid": "42"})),
                ):
                    with patch.object(
                        sync_service,
                        "_persist_verbal_intro",
                        new=AsyncMock(),
                    ) as mock_persist:
                        await sync_service.sync_doctor(
                            _identity(),
                            _details(),
                            doctor_id=5,
                            db_session=mock_db,
                        )

        mock_persist.assert_awaited_once_with(5, overview, mock_db)

    @pytest.mark.asyncio
    async def test_sync_doctor_maps_api_error(self, sync_service: LinQMDSyncService):
        with patch.object(
            sync_service,
            "_load_display_picture_file",
            new=AsyncMock(return_value=None),
        ):
            with _mock_overview_service():
                with patch.object(
                    sync_service,
                    "_send_to_linqmd",
                    new=AsyncMock(return_value=(200, {"error": "Duplicate email"})),
                ):
                    result = await sync_service.sync_doctor(
                        _identity(), _details(), doctor_id=5
                    )

        assert result.success is False
        assert result.error_message == "Duplicate email"

    @pytest.mark.asyncio
    async def test_sync_doctor_timeout_returns_failure(
        self, sync_service: LinQMDSyncService
    ):
        with patch.object(
            sync_service,
            "_load_display_picture_file",
            new=AsyncMock(return_value=None),
        ):
            with _mock_overview_service():
                with patch.object(
                    sync_service,
                    "_send_to_linqmd",
                    new=AsyncMock(side_effect=httpx.TimeoutException("timeout")),
                ):
                    result = await sync_service.sync_doctor(
                        _identity(), _details(), doctor_id=5
                    )

        assert result.success is False
        assert "timeout" in (result.error_message or "").lower()


class TestSyncDoctorById:
    @pytest.mark.asyncio
    async def test_sync_doctor_by_id_missing_identity(
        self, sync_service: LinQMDSyncService
    ):
        with patch.object(
            sync_service,
            "_build_sync_context",
            new=AsyncMock(return_value=None),
        ):
            result = await sync_service.sync_doctor_by_id(99, MagicMock())

        assert result.success is False
        assert "not found" in (result.error_message or "").lower()


class TestSyncDoctorUpdateById:
    @pytest.mark.asyncio
    async def test_update_skipped_when_no_credentials(
        self, sync_service: LinQMDSyncService
    ):
        mock_db = MagicMock()
        with patch(
            "src.app.repositories.linqmd_credentials_repository.LinqmdCredentialsRepository"
        ) as MockCredsRepo:
            MockCredsRepo.return_value.get_by_doctor_id = AsyncMock(return_value=None)
            result = await sync_service.sync_doctor_update_by_id(5, mock_db)

        assert result.success is True
        assert result.linqmd_response == {"skipped": "no_linqmd_credentials"}

    @pytest.mark.asyncio
    async def test_update_uses_stored_credentials_and_update_url(
        self, sync_service: LinQMDSyncService
    ):
        mock_db = MagicMock()
        mock_creds = MagicMock()
        mock_creds.linqmd_user_id = "linq-99"
        mock_creds.linqmd_username = "stored-user"
        mock_creds.linqmd_password = "stored-pass"

        with patch(
            "src.app.repositories.linqmd_credentials_repository.LinqmdCredentialsRepository"
        ) as MockCredsRepo:
            MockCredsRepo.return_value.get_by_doctor_id = AsyncMock(return_value=mock_creds)
            with patch.object(
                sync_service,
                "_build_sync_context",
                new=AsyncMock(return_value=(_identity(), _details(), [])),
            ):
                with patch.object(
                    sync_service,
                    "_load_display_picture_file",
                    new=AsyncMock(return_value=None),
                ):
                    with patch.object(
                        sync_service,
                        "_send_update_to_linqmd",
                        new=AsyncMock(return_value=(200, {"ok": True})),
                    ) as mock_update:
                        result = await sync_service.sync_doctor_update_by_id(5, mock_db)

        assert result.success is True
        mock_update.assert_awaited_once()
        sent_user_id, sent_payload = mock_update.await_args.args
        assert sent_user_id == "linq-99"
        assert sent_payload.name == "stored-user"
        assert sent_payload.password == "stored-pass"
        assert sent_payload.overview == ""

    @pytest.mark.asyncio
    async def test_update_omits_overview_from_form_data(
        self, sync_service: LinQMDSyncService
    ):
        """Update payload must not include overview even if details have achievements."""
        mock_db = MagicMock()
        mock_creds = MagicMock()
        mock_creds.linqmd_user_id = "linq-99"
        mock_creds.linqmd_username = "stored-user"
        mock_creds.linqmd_password = "stored-pass"

        details = _details()
        details["professional_overview"] = "Should not be sent on update."

        with patch(
            "src.app.repositories.linqmd_credentials_repository.LinqmdCredentialsRepository"
        ) as MockCredsRepo:
            MockCredsRepo.return_value.get_by_doctor_id = AsyncMock(return_value=mock_creds)
            with patch.object(
                sync_service,
                "_build_sync_context",
                new=AsyncMock(return_value=(_identity(), details, [])),
            ):
                with patch.object(
                    sync_service,
                    "_load_display_picture_file",
                    new=AsyncMock(return_value=None),
                ):
                    with patch.object(
                        sync_service,
                        "_send_update_to_linqmd",
                        new=AsyncMock(return_value=(200, {"ok": True})),
                    ) as mock_update:
                        await sync_service.sync_doctor_update_by_id(5, mock_db)

        sent_payload = mock_update.await_args.args[1]
        form = sent_payload.to_form_data(include_theme=False)
        assert "overview" not in form


class TestGeneratePassword:
    def test_generated_password_matches_expected_pattern(self):
        service = LinQMDSyncService()
        password = service._generate_password()
        assert len(password) >= 12
        assert password[-1] in "!#"
        assert password[-4:-1].isdigit()
