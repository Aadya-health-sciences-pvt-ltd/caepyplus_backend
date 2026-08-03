"""Blog Studio API Endpoints.

Handles generic CRUD for Blogs, Comments, and AI/Drupal stubs.
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, UploadFile, File
from typing import Annotated, Any
from datetime import datetime
import logging
import re

from sqlalchemy import select, delete

from ....core.blog_auth import AuthenticatedDoctorId, linqmd_login_error_code
from ....core.security import require_authentication
from ....core.config import Settings, get_settings
from ....core.prompts import get_prompt_manager
from ....core.exceptions import AIServiceError, ExtractionError
from ....services.gemini_service import GeminiService, get_gemini_service
from ....db.session import DbSession
from ....models.blog import Blog, BlogKeyword, BlogComment
from ....schemas.blog import (
    BlogResponse,
    BlogCreate,
    BlogUpdate,
    BlogPublishConfig,
    BlogPublishPracticeHubRequest,
    BlogPublishPracticeHubResponse,
    BlogCommentResponse,
    CommentStatusUpdate,
    AITopicsResponse,
    AIKeywordSuggestionResponse,
    AITopicCard,
    AIBlogContentGenerateRequest,
    AIBlogContentResponse,
)
from ....repositories.linqmd_credentials_repository import LinqmdCredentialsRepository
from ....repositories.onboarding_repository import OnboardingRepository
from ....services.linqmd_practice_hub_service import (
    LinqmdLoginError,
    LinqmdPublishError,
    PracticeHubBlogPayload,
    build_blog_live_url,
    extract_image_alt_from_html,
    get_linqmd_practice_hub_service,
    resolve_blog_live_url,
)
from ....services.practice_hub_publish_helpers import (
    get_blog_for_practice_hub_publish,
    get_owned_blog,
    linqmd_profile_missing_exception,
)
from ....models.enums import BlogStatus, CommentStatus, CommentAuthorType

logger = logging.getLogger(__name__)

# We will create two routers: one for authenticated user actions, one for webhooks
router = APIRouter(tags=["Blogs"], dependencies=[Depends(require_authentication)])
webhook_router = APIRouter(tags=["Webhooks"])


async def _resolve_image_urls(image_urls: list | None) -> list[str]:
    """Convert stored S3 keys into fresh presigned URLs.
    
    When STORAGE_BACKEND=s3 and the bucket is private, we store the raw S3 key
    in the DB (not a URL). This helper generates a fresh signed URL for each key
    so the browser can load images immediately.
    
    For local storage (keys starting with /api/v1/blobs) or already-absolute HTTPS
    URLs, the value is returned unchanged.
    """
    if not image_urls:
        return []
    
    from ....services.blob_storage_service import get_blob_storage_service, S3BlobStorageService
    
    blob_service = get_blob_storage_service()
    resolved = []
    
    for path in image_urls:
        if not path:
            continue
        # Already an absolute URL — pass through unchanged
        if path.startswith("http://") or path.startswith("https://"):
            resolved.append(path)
        # Local blob storage path — also pass through unchanged
        elif path.startswith("/"):
            resolved.append(path)
        # Otherwise treat as raw S3 key and generate a presigned URL
        elif isinstance(blob_service, S3BlobStorageService):
            try:
                signed_url = await blob_service.generate_presigned_url(path)
                resolved.append(signed_url)
            except Exception:
                resolved.append(path)  # fall back to raw key on error
        else:
            resolved.append(path)
    
    return resolved


async def _get_linqmd_username(db: DbSession, doctor_id: int) -> str | None:
    creds = await LinqmdCredentialsRepository(db).get_by_doctor_id(doctor_id)
    if creds and creds.linqmd_username:
        return creds.linqmd_username.strip().lstrip("/")
    return None


async def _blog_to_response(db: DbSession, doctor_id: int, blog: Blog) -> BlogResponse:
    if blog.image_urls:
        blog.image_urls = await _resolve_image_urls(blog.image_urls)
    username = await _get_linqmd_username(db, doctor_id)
    settings = get_settings()
    live_url = resolve_blog_live_url(
        blog_status=blog.status,
        title=blog.title,
        linqmd_username=username,
        base_url=settings.LINQMD_PRACTICE_HUB_API_URL,
        seo_schema_markup=blog.seo_schema_markup,
    )
    return BlogResponse.model_validate(blog).model_copy(update={"live_url": live_url})


async def _blogs_to_responses(
    db: DbSession,
    doctor_id: int,
    blogs: list[Blog],
) -> list[BlogResponse]:
    username = await _get_linqmd_username(db, doctor_id)
    settings = get_settings()
    base_url = settings.LINQMD_PRACTICE_HUB_API_URL
    responses: list[BlogResponse] = []
    for blog in blogs:
        if blog.image_urls:
            blog.image_urls = await _resolve_image_urls(blog.image_urls)
        live_url = resolve_blog_live_url(
            blog_status=blog.status,
            title=blog.title,
            linqmd_username=username,
            base_url=base_url,
            seo_schema_markup=blog.seo_schema_markup,
        )
        responses.append(
            BlogResponse.model_validate(blog).model_copy(update={"live_url": live_url})
        )
    return responses


# ---------------------------------------------------------------------------
# AI Suggestions (Static Paths First)
# ---------------------------------------------------------------------------

_TOPICS_MAX_TOKENS = 8192
_BLOG_STUDIO_MODEL_CONFIG_KEY = "GEMINI_RESUME_MODEL"


async def _blog_studio_generate_structured(
    gemini: GeminiService,
    prompt: str,
    *,
    max_tokens: int | None = None,
    settings: Settings | None = None,
) -> dict:
    """Blog Studio AI calls always use ``GEMINI_RESUME_MODEL``."""
    cfg = settings or get_settings()
    return await gemini.generate_structured(
        prompt,
        max_tokens=max_tokens,
        model=cfg.GEMINI_RESUME_MODEL,
        config_key=_BLOG_STUDIO_MODEL_CONFIG_KEY,
    )


def _topics_http_exception(exc: Exception) -> HTTPException:
    """Map AI failures to actionable API errors for the Blog Studio UI."""
    if isinstance(exc, AIServiceError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.message,
        )
    if isinstance(exc, ExtractionError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=exc.message,
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Failed to generate topics: {str(exc)}",
    )


@router.get("/insights/topics", response_model=AITopicsResponse)
async def get_ai_topics() -> AITopicsResponse:
    """Get AI suggested blog topics for the doctor using Gemini."""
    try:
        gemini = get_gemini_service()
        prompts = get_prompt_manager()

        prompt = prompts.get_blog_topics_prompt()
        result = await _blog_studio_generate_structured(
            gemini, prompt, max_tokens=_TOPICS_MAX_TOKENS
        )
        return AITopicsResponse(**result)
    except (AIServiceError, ExtractionError, HTTPException):
        raise
    except Exception as e:
        raise _topics_http_exception(e) from e

@router.get("/insights/keywords", response_model=AIKeywordSuggestionResponse)
async def get_ai_keywords(topic: str) -> AIKeywordSuggestionResponse:
    """Get AI suggested keywords based on the selected topic using Gemini."""
    try:
        gemini = get_gemini_service()
        prompts = get_prompt_manager()
        
        prompt = prompts.get_blog_keywords_prompt(topic)
        result = await _blog_studio_generate_structured(gemini, prompt)
        return AIKeywordSuggestionResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate keywords: {str(e)}"
        )

@router.post("/insights/generate-content", response_model=AIBlogContentResponse)
async def generate_ai_blog_content(
    payload: AIBlogContentGenerateRequest
) -> AIBlogContentResponse:
    """Generate AI subtitle, quote, and content based on topic and keywords."""
    try:
        gemini = get_gemini_service()
        prompts = get_prompt_manager()
        
        prompt = prompts.get_blog_content_prompt(payload.topic, payload.keywords)
        result = await _blog_studio_generate_structured(gemini, prompt)
        return AIBlogContentResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate content: {str(e)}"
        )

# ---------------------------------------------------------------------------
# Comment Moderation (Move before parameter-based routes like /{blog_id})
# ---------------------------------------------------------------------------

@router.get("/comments", response_model=list[BlogCommentResponse])
async def get_comments(
    db: DbSession,
    doctor_id: AuthenticatedDoctorId,
    status: str | None = None,
) -> Any:
    """Get all comments for the authenticated doctor's blogs."""

    # Join with blogs to ensure we only get comments for the doctor's blogs
    query = (
        select(BlogComment)
        .join(Blog)
        .where(Blog.doctor_id == doctor_id)
        .order_by(BlogComment.created_at.desc())
    )
    
    if status:
        query = query.where(BlogComment.status == status)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.put("/comments/{comment_id}/status")
async def update_comment_status(
    comment_id: int,
    payload: CommentStatusUpdate,
    db: DbSession,
    doctor_id: AuthenticatedDoctorId,
) -> dict[str, Any]:
    """Approve or reject a comment."""

    # Subquery to check ownership
    result = await db.execute(
        select(BlogComment)
        .join(Blog)
        .where(BlogComment.id == comment_id, Blog.doctor_id == doctor_id)
    )
    comment = result.scalar_one_or_none()
    
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found or access denied")

    comment.status = payload.status
    await db.commit()

    return {
        "status": "success",
        "message": f"Comment {payload.status} successfully",
        "comment_id": comment_id
    }

# ---------------------------------------------------------------------------
# Blogs CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=list[BlogResponse])
async def get_blogs(
    db: DbSession,
    doctor_id: AuthenticatedDoctorId,
    status: str | None = None,
) -> Any:
    """List blogs for the authenticated doctor, optionally filtered by status."""
    
    query = select(Blog).where(Blog.doctor_id == doctor_id).order_by(Blog.created_at.desc())
    if status:
        query = query.where(Blog.status == status)
        
    result = await db.execute(query)
    blogs = list(result.scalars().all())
    return await _blogs_to_responses(db, doctor_id, blogs)


@router.post("", response_model=BlogResponse, status_code=status.HTTP_201_CREATED)
async def create_blog(
    db: DbSession,
    payload: BlogCreate,
    doctor_id: AuthenticatedDoctorId,
) -> Any:
    """Create a new draft blog for the authenticated doctor."""

    blog = Blog(
        doctor_id=doctor_id,
        title=payload.title,
        status=BlogStatus.DRAFT.value,
    )
    db.add(blog)
    await db.flush()
    await db.commit()
    await db.refresh(blog)
    return await _blog_to_response(db, doctor_id, blog)


@router.get("/{blog_id}", response_model=BlogResponse)
async def get_blog(
    blog_id: int,
    db: DbSession,
    doctor_id: AuthenticatedDoctorId,
) -> Any:
    """Get an existing blog by ID."""
    blog = await get_owned_blog(
        db,
        blog_id=blog_id,
        doctor_id=doctor_id,
        route="GET /blogs/{blog_id}",
    )
    return await _blog_to_response(db, doctor_id, blog)


@router.put("/{blog_id}", response_model=BlogResponse)
async def update_blog(
    blog_id: int,
    payload: BlogUpdate,
    db: DbSession,
    doctor_id: AuthenticatedDoctorId,
) -> Any:
    """Update a draft blog. Replaces keywords atomically."""
    logger.info(
        "blog_update doctor_id=%s blog_id=%s",
        doctor_id,
        blog_id,
    )

    blog = await get_owned_blog(
        db,
        blog_id=blog_id,
        doctor_id=doctor_id,
        route="PUT /blogs/{blog_id}",
    )

    if payload.title is not None:
        blog.title = payload.title
    if payload.subtitle is not None:
        blog.subtitle = payload.subtitle
    if payload.opening_quote is not None:
        blog.opening_quote = payload.opening_quote
    if payload.content is not None:
        blog.content = payload.content

    if payload.content:
        raw_text = payload.content.replace('<', ' <').replace('>', '> ')
        words = len(re.findall(r'\w+', raw_text))
        blog.estimated_read_time = max(1, round(words / 200))

    if payload.keywords is not None:
        await db.execute(delete(BlogKeyword).where(BlogKeyword.blog_id == blog_id))
        for kw in payload.keywords:
            if kw.strip():
                db.add(BlogKeyword(blog_id=blog_id, keyword=kw.strip()))

    await db.commit()
    await db.refresh(blog)
    return await _blog_to_response(db, doctor_id, blog)


async def _doctor_onboarding_status(db: DbSession, doctor_id: int) -> str:
    """Prefer doctor_identity status; fall back to doctors.onboarding_status."""
    onboarding_repo = OnboardingRepository(db)
    identity = await onboarding_repo.get_identity_by_doctor_id(doctor_id)
    if identity is not None:
        status = identity.onboarding_status
        return (status.value if hasattr(status, "value") else str(status)).lower()
    from ....repositories.doctor_repository import DoctorRepository

    doctor = await DoctorRepository(db).get_by_id(doctor_id)
    if doctor is None:
        return "pending"
    return (doctor.onboarding_status or "pending").lower()


@router.post(
    "/{blog_id}/publish-practice-hub",
    response_model=BlogPublishPracticeHubResponse,
)
async def publish_blog_to_practice_hub(
    blog_id: int,
    payload: BlogPublishPracticeHubRequest,
    db: DbSession,
    doctor_id: AuthenticatedDoctorId,
) -> BlogPublishPracticeHubResponse:
    """Login to Practice Hub and publish blog; mark local blog as published."""
    logger.info(
        "practice_hub_publish doctor_id=%s blog_id=%s",
        doctor_id,
        blog_id,
    )

    onboarding_status = await _doctor_onboarding_status(db, doctor_id)
    if onboarding_status != "verified":
        logger.warning(
            "practice_hub_publish blocked_not_verified doctor_id=%s blog_id=%s status=%s",
            doctor_id,
            blog_id,
            onboarding_status,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Doctor verification pending. Publishing is available after verification.",
        )

    blog = await get_blog_for_practice_hub_publish(
        db,
        blog_id=blog_id,
        doctor_id=doctor_id,
        route="POST /blogs/{blog_id}/publish-practice-hub",
    )

    creds_repo = LinqmdCredentialsRepository(db)
    stored_creds = await creds_repo.get_by_doctor_id(doctor_id)
    using_override = payload.credentials is not None
    logger.info(
        "practice_hub_publish creds doctor_id=%s blog_id=%s stored_creds=%s using_override=%s",
        doctor_id,
        blog_id,
        stored_creds is not None,
        using_override,
    )
    if stored_creds is None and payload.credentials is None:
        raise linqmd_profile_missing_exception()

    if using_override:
        username = payload.credentials.username.strip()
        password = payload.credentials.password
    elif stored_creds:
        username = stored_creds.linqmd_username
        password = stored_creds.linqmd_password
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LinQMD credentials are required.",
        )

    hub_service = get_linqmd_practice_hub_service()
    logger.info(
        "practice_hub_publish login doctor_id=%s blog_id=%s username=%s",
        doctor_id,
        blog_id,
        username,
    )
    try:
        login_result = await hub_service.login(username, password)
    except LinqmdLoginError as exc:
        logger.warning(
            "practice_hub_publish login_failed doctor_id=%s blog_id=%s username=%s error=%s",
            doctor_id,
            blog_id,
            username,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": linqmd_login_error_code(exc),
                "message": (
                    "Practice Hub login failed. Please update your credentials and try again."
                    if linqmd_login_error_code(exc) == "linqmd_credentials_invalid"
                    else "Practice Hub returned an unexpected login response. Contact support or try again later."
                ),
                "error": str(exc),
            },
        ) from exc

    logger.info(
        "practice_hub_publish login_ok doctor_id=%s blog_id=%s has_refresh_token=%s",
        doctor_id,
        blog_id,
        login_result.refresh_token is not None,
    )

    if using_override and stored_creds is not None:
        await creds_repo.update_credentials(doctor_id, username, password)

    image_bytes = None
    image_filename = None
    image_content_type = None
    if blog.image_urls and len(blog.image_urls) > 0:
        loaded = await hub_service.load_blog_image_from_storage(blog.image_urls[0])
        if loaded:
            image_bytes, image_filename, image_content_type = loaded
        else:
            logger.warning(
                "practice_hub_publish image_load_failed doctor_id=%s blog_id=%s uri=%r",
                doctor_id,
                blog_id,
                blog.image_urls[0][:120],
            )

    image_alt = extract_image_alt_from_html(blog.content)
    hub_payload = PracticeHubBlogPayload(
        title=blog.title or "Untitled Blog",
        subtitle=blog.subtitle,
        content=blog.content,
        image_bytes=image_bytes,
        image_filename=image_filename,
        image_content_type=image_content_type,
        image_alt=image_alt,
    )

    logger.info(
        "practice_hub_publish calling_hub doctor_id=%s blog_id=%s has_image=%s "
        "content_len=%s",
        doctor_id,
        blog_id,
        image_bytes is not None,
        len(blog.content or ""),
    )
    try:
        practice_hub_response = await hub_service.publish_blog(
            login_result.access_token,
            hub_payload,
        )
    except LinqmdPublishError as exc:
        logger.warning(
            "practice_hub_publish hub_failed doctor_id=%s blog_id=%s error=%s",
            doctor_id,
            blog_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "linqmd_publish_failed",
                "message": str(exc),
            },
        ) from exc

    drupal_node_id = None
    if isinstance(practice_hub_response, dict):
        for key in ("nid", "node_id", "drupal_node_id", "id", "uid"):
            val = practice_hub_response.get(key)
            if val is not None:
                drupal_node_id = str(val)
                break

    blog.status = BlogStatus.PUBLISHED.value
    blog.published_at = datetime.now()
    if drupal_node_id:
        blog.drupal_node_id = drupal_node_id
    settings = get_settings()
    live_url = build_blog_live_url(
        base_url=settings.LINQMD_PRACTICE_HUB_API_URL,
        username=username,
        title=blog.title or "Untitled Blog",
    )
    markup = dict(blog.seo_schema_markup or {})
    markup["live_url"] = live_url
    blog.seo_schema_markup = markup
    await db.commit()
    await db.refresh(blog)

    logger.info(
        "practice_hub_publish success doctor_id=%s blog_id=%s drupal_node_id=%s",
        doctor_id,
        blog_id,
        drupal_node_id,
    )

    return BlogPublishPracticeHubResponse(
        blog_id=blog_id,
        status=blog.status,
        drupal_node_id=drupal_node_id,
        practice_hub_response=practice_hub_response,
    )


@router.post("/{blog_id}/publish")
async def publish_blog(
    blog_id: int,
    payload: BlogPublishConfig,
    db: DbSession,
    doctor_id: AuthenticatedDoctorId,
) -> dict[str, Any]:
    """Mark a blog as published."""

    result = await db.execute(
        select(Blog).where(Blog.id == blog_id, Blog.doctor_id == doctor_id)
    )
    blog = result.scalar_one_or_none()
    if blog is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog not found")

    blog.status = BlogStatus.PUBLISHED.value
    blog.published_at = datetime.now()
    await db.commit()

    return {
        "status": "success",
        "message": "Blog published successfully",
        "blog_id": blog_id,
        "drupal_node_id": None,
    }

@router.delete("/{blog_id}")
async def delete_blog(
    blog_id: int,
    db: DbSession,
    doctor_id: AuthenticatedDoctorId,
) -> dict[str, Any]:
    """Delete a blog (draft or published)."""

    result = await db.execute(
        select(Blog).where(Blog.id == blog_id, Blog.doctor_id == doctor_id)
    )
    blog = result.scalar_one_or_none()
    
    if blog is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog not found")

    # Delete keywords first due to foreign key constraints if not handled by cascade
    await db.execute(delete(BlogKeyword).where(BlogKeyword.blog_id == blog_id))
    
    # Delete the blog
    await db.delete(blog)
    await db.commit()

    return {
        "status": "success",
        "message": "Blog deleted successfully",
        "blog_id": blog_id
    }

@router.post("/{blog_id}/images")
async def upload_blog_image(
    blog_id: int,
    db: DbSession,
    doctor_id: AuthenticatedDoctorId,
    file: UploadFile = File(...),
) -> dict[str, str]:
    """Upload an image for a blog post and store it in blob storage."""
    from fastapi import HTTPException
    import os
    import uuid
    import mimetypes
    from ....services.blob_storage_service import get_blob_storage_service

    blog = await get_owned_blog(
        db,
        blog_id=blog_id,
        doctor_id=doctor_id,
        route="POST /blogs/{blog_id}/images",
    )
    
    file_bytes = await file.read()
    original_filename = file.filename or "image.jpg"

    blob_service = get_blob_storage_service()

    # The BlobStorageService automatically detects extension and mime_type from filename,
    # generates a safe UUID for the blob_id, and builds the path using doctor_id and category.
    upload_result = await blob_service.upload_from_bytes(
        content=file_bytes,
        file_name=original_filename,
        doctor_id=doctor_id,
        media_category="blogs"
    )
    
    if not upload_result.success:
        raise HTTPException(status_code=500, detail=f"Image upload failed: {upload_result.error_message}")
        
    s3_key = upload_result.file_uri  # This is the raw S3 key (not a URL)
    
    # Store the permanent S3 key in the blog table (NOT a signed URL which would expire)
    current_images = list(blog.image_urls) if blog.image_urls else []
    current_images.append(s3_key)
    blog.image_urls = current_images
    
    await db.commit()

    # Generate a fresh signed URL for the immediate frontend response
    viewable_url = (await _resolve_image_urls([s3_key]))[0]

    return {
        "url": viewable_url,
        "message": "Image uploaded successfully"
    }

# ---------------------------------------------------------------------------
# Drupal Webhooks (Static Paths)
# ---------------------------------------------------------------------------

@webhook_router.post("/drupal/comments")
async def handle_drupal_comment_webhook() -> dict[str, str]:
    return {"status": "received"}

@webhook_router.post("/drupal/nodes")
async def handle_drupal_node_webhook() -> dict[str, str]:
    return {"status": "received"}
