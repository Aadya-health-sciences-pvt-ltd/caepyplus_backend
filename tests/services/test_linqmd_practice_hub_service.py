"""Unit tests for LinQMD Practice Hub service (mocked HTTP)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.app.services.linqmd_practice_hub_service import (
    LinqmdLoginError,
    LinqmdPracticeHubService,
    LinqmdPublishError,
    PracticeHubBlogPayload,
    PracticeHubLoginResult,
    _stored_uri_to_s3_key,
    build_field_blog_title,
    build_blog_title_slug,
    extract_image_alt_from_html,
    parse_practice_hub_login_tokens,
)


class TestPracticeHubHelpers:
    def test_build_field_blog_title_strips_special_chars(self):
        assert build_field_blog_title("Heart Health: Tips & Tricks!!!") == "Heart Health Tips Tricks"

    def test_build_field_blog_title_truncates_at_word_boundary(self):
        title = "A" * 30 + " " + "B" * 30
        result = build_field_blog_title(title, max_len=40)
        assert len(result) <= 40
        assert not result.endswith(" ")

    def test_build_field_blog_title_defaults_when_empty(self):
        assert build_field_blog_title("!!!") == "Blog"

    def test_build_blog_title_slug_seo_format(self):
        assert build_blog_title_slug("Heart Health: Tips for 2026") == (
            "heart-health-tips-for-2026"
        )

    def test_build_blog_title_slug_strips_punctuation(self):
        assert build_blog_title_slug("Heart Health: Tips & Tricks!!!") == (
            "heart-health-tips-tricks"
        )

    def test_build_blog_title_slug_defaults_when_empty(self):
        assert build_blog_title_slug("!!!") == "blog"

    def test_build_blog_title_slug_truncates_at_hyphen_boundary(self):
        long_title = "word " * 30
        slug = build_blog_title_slug(long_title, max_len=40)
        assert len(slug) <= 40
        assert not slug.endswith("-")

    def test_extract_image_alt_from_html(self):
        html = '<p>Hi</p><img src="/x.jpg" alt="Doctor portrait" />'
        assert extract_image_alt_from_html(html) == "Doctor portrait"

    def test_extract_image_alt_returns_none_without_img(self):
        assert extract_image_alt_from_html("<p>No image</p>") is None

    def test_stored_uri_to_s3_key_from_amazon_url(self):
        uri = "https://bucket.s3.amazonaws.com/blogs/photo.jpg?X-Amz=1"
        assert _stored_uri_to_s3_key(uri) == "blogs/photo.jpg"

    def test_stored_uri_to_s3_key_from_bare_key(self):
        assert _stored_uri_to_s3_key("doctors/1/profile.jpg") == "doctors/1/profile.jpg"

    def test_parse_login_tokens_nested_data_wrapper(self):
        body = {
            "status_code": 200,
            "msg": "Login successful",
            "data": {
                "access_token": "eyJ.test",
                "refresh_token": "eyJ.refresh",
                "expires_in": 600,
                "token_type": "Bearer",
            },
        }
        access, refresh = parse_practice_hub_login_tokens(body)
        assert access == "eyJ.test"
        assert refresh == "eyJ.refresh"

    def test_parse_login_tokens_flat_legacy(self):
        access, refresh = parse_practice_hub_login_tokens(
            {"access_token": "a", "refresh_token": "r"}
        )
        assert access == "a"
        assert refresh == "r"


@pytest.fixture
def hub_service() -> LinqmdPracticeHubService:
    return LinqmdPracticeHubService()


def _mock_http_response(
    *,
    status_code: int = 200,
    json_body: dict | None = None,
    text: str = "",
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.content = b"{}" if json_body is not None else text.encode()
    response.text = text or (str(json_body) if json_body else "")
    response.json.return_value = json_body or {}
    return response


class TestPracticeHubLogin:
    @pytest.mark.asyncio
    async def test_login_success_parses_tokens(self, hub_service: LinqmdPracticeHubService):
        mock_response = _mock_http_response(
            json_body={"access_token": "tok-123", "refresh_token": "ref-456"},
        )
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        hub_service._client = mock_client
        result = await hub_service.login("dr-user", "secret")

        assert isinstance(result, PracticeHubLoginResult)
        assert result.access_token == "tok-123"
        assert result.refresh_token == "ref-456"
        mock_client.post.assert_awaited_once()
        call_kwargs = mock_client.post.await_args.kwargs
        assert call_kwargs["json"] == {"username": "dr-user", "password": "secret"}

    @pytest.mark.asyncio
    async def test_login_success_parses_nested_data_tokens(
        self, hub_service: LinqmdPracticeHubService
    ):
        mock_response = _mock_http_response(
            json_body={
                "status_code": 200,
                "msg": "Login successful",
                "data": {
                    "access_token": "nested-tok",
                    "refresh_token": "nested-ref",
                },
            },
        )
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        hub_service._client = mock_client
        result = await hub_service.login("dr-user", "secret")
        assert result.access_token == "nested-tok"
        assert result.refresh_token == "nested-ref"

    @pytest.mark.asyncio
    async def test_login_raises_on_non_200(self, hub_service: LinqmdPracticeHubService):
        mock_response = _mock_http_response(
            status_code=401,
            json_body={"error": "Invalid credentials"},
        )
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        hub_service._client = mock_client
        with pytest.raises(LinqmdLoginError) as exc:
            await hub_service.login("bad", "creds")

        assert exc.value.status_code == 401
        assert "Invalid credentials" in str(exc.value)

    @pytest.mark.asyncio
    async def test_login_raises_when_access_token_missing(
        self, hub_service: LinqmdPracticeHubService
    ):
        mock_response = _mock_http_response(json_body={"refresh_token": "only"})
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        hub_service._client = mock_client
        with pytest.raises(LinqmdLoginError, match="access_token was missing"):
            await hub_service.login("user", "pass")

    @pytest.mark.asyncio
    async def test_login_raises_on_timeout(self, hub_service: LinqmdPracticeHubService):
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        hub_service._client = mock_client
        with pytest.raises(LinqmdLoginError, match="timed out"):
            await hub_service.login("user", "pass")


class TestPracticeHubPublishBlog:
    @pytest.mark.asyncio
    async def test_publish_blog_without_image(self, hub_service: LinqmdPracticeHubService):
        mock_response = _mock_http_response(json_body={"id": "blog-1", "status": "published"})
        blog = PracticeHubBlogPayload(
            title="Heart Health Tips",
            subtitle="Stay active",
            content="<p>Content</p>",
        )

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        hub_service._client = mock_client
        body = await hub_service.publish_blog("tok-abc", blog)

        assert body["id"] == "blog-1"
        mock_client.post.assert_awaited_once()
        call_kwargs = mock_client.post.await_args.kwargs
        assert call_kwargs["headers"]["Authorization"] == "Bearer tok-abc"
        assert call_kwargs["data"]["Title"] == "heart-health-tips"
        assert call_kwargs["data"]["field_blog_title"] == "Heart Health Tips"
        assert call_kwargs["data"]["short_description"] == "Stay active"
        assert "files" not in call_kwargs

    @pytest.mark.asyncio
    async def test_publish_blog_with_image_multipart(self, hub_service: LinqmdPracticeHubService):
        mock_response = _mock_http_response(json_body={"id": "blog-2"})
        blog = PracticeHubBlogPayload(
            title="Photo Blog",
            subtitle=None,
            content="<p>Hi</p>",
            image_bytes=b"\xff\xd8\xff",
            image_filename="cover.jpg",
            image_content_type="image/jpeg",
            image_alt="Cover photo",
        )

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        hub_service._client = mock_client
        await hub_service.publish_blog("tok-abc", blog)

        call_kwargs = mock_client.post.await_args.kwargs
        assert call_kwargs["files"]["image"] == ("cover.jpg", b"\xff\xd8\xff", "image/jpeg")
        assert call_kwargs["data"]["image_alt"] == "Cover photo"

    @pytest.mark.asyncio
    async def test_publish_blog_raises_on_api_error(self, hub_service: LinqmdPracticeHubService):
        mock_response = _mock_http_response(
            status_code=422,
            json_body={"message": "Title required"},
        )
        blog = PracticeHubBlogPayload(title="", subtitle=None, content=None)

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        hub_service._client = mock_client
        with pytest.raises(LinqmdPublishError) as exc:
            await hub_service.publish_blog("tok", blog)

        assert exc.value.status_code == 422
        assert "Title required" in str(exc.value)


class TestPracticeHubLoadBlogImage:
    @pytest.mark.asyncio
    async def test_load_blog_image_from_s3(self, hub_service: LinqmdPracticeHubService):
        from src.app.services.blob_storage_service import S3BlobStorageService

        class _FakeS3(S3BlobStorageService):
            async def get_object_bytes(self, key: str):
                return (b"img-bytes", "photo.jpg", "image/jpeg")

        fake_blob = _FakeS3.__new__(_FakeS3)

        with patch(
            "src.app.services.blob_storage_service.get_blob_storage_service",
            return_value=fake_blob,
        ):
            loaded = await hub_service.load_blog_image_from_storage(
                "https://bucket.s3.amazonaws.com/blogs/photo.jpg",
            )

        assert loaded == (b"img-bytes", "photo.jpg", "image/jpeg")

    @pytest.mark.asyncio
    async def test_load_blog_image_returns_none_for_empty_uri(
        self, hub_service: LinqmdPracticeHubService
    ):
        assert await hub_service.load_blog_image_from_storage("") is None
