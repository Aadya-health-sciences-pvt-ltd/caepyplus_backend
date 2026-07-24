"""Content Creator blog routes — act on behalf of verified doctors."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import delete, select

from ....core.rbac import ContentCreatorUser
from ....db.session import DbSession
from ....models.blog import Blog, BlogComment, BlogKeyword
from ....models.enums import BlogStatus
from ....repositories.doctor_repository import DoctorRepository
from ....repositories.linqmd_credentials_repository import LinqmdCredentialsRepository
from ....schemas.blog import (
    AIBlogContentGenerateRequest,
    AIBlogContentResponse,
    AIKeywordSuggestionResponse,
    AITopicsResponse,
    BlogCommentResponse,
    BlogCreate,
    BlogPublishConfig,
    BlogPublishPracticeHubRequest,
    BlogPublishPracticeHubResponse,
    BlogResponse,
    BlogUpdate,
    CommentStatusUpdate,
)
from ....services.linqmd_practice_hub_service import (
    LinqmdLoginError,
    LinqmdPublishError,
    PracticeHubBlogPayload,
    extract_image_alt_from_html,
    get_linqmd_practice_hub_service,
)
from .blogs import (
    _doctor_onboarding_status,
    _resolve_image_urls,
    generate_ai_blog_content,
    get_ai_keywords,
    get_ai_topics,
)

router = APIRouter(
    prefix="/content/doctors/{doctor_id}/blogs",
    tags=["Content - Blogs"],
)


async def require_verified_doctor(
    doctor_id: int,
    db: DbSession,
    _user: ContentCreatorUser,
) -> int:
    """Ensure doctor exists and onboarding status is verified."""
    doctor = await DoctorRepository(db).get_by_id(doctor_id)
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )
    onboarding_status = await _doctor_onboarding_status(db, doctor_id)
    if onboarding_status != "verified":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Content can only be managed for verified doctors",
        )
    return doctor_id


VerifiedDoctorId = Annotated[int, Depends(require_verified_doctor)]


@router.get("/insights/topics", response_model=AITopicsResponse)
async def content_get_ai_topics(
    _doctor_id: VerifiedDoctorId,
) -> AITopicsResponse:
    return await get_ai_topics()


@router.get("/insights/keywords", response_model=AIKeywordSuggestionResponse)
async def content_get_ai_keywords(
    topic: str,
    _doctor_id: VerifiedDoctorId,
) -> AIKeywordSuggestionResponse:
    return await get_ai_keywords(topic)


@router.post("/insights/generate-content", response_model=AIBlogContentResponse)
async def content_generate_ai_blog_content(
    payload: AIBlogContentGenerateRequest,
    _doctor_id: VerifiedDoctorId,
) -> AIBlogContentResponse:
    return await generate_ai_blog_content(payload)


@router.get("/comments", response_model=list[BlogCommentResponse])
async def content_get_comments(
    db: DbSession,
    doctor_id: VerifiedDoctorId,
    status: str | None = None,
) -> Any:
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
async def content_update_comment_status(
    comment_id: int,
    payload: CommentStatusUpdate,
    db: DbSession,
    doctor_id: VerifiedDoctorId,
) -> dict[str, Any]:
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
        "comment_id": comment_id,
    }


@router.get("", response_model=list[BlogResponse])
async def content_list_blogs(
    db: DbSession,
    doctor_id: VerifiedDoctorId,
    status: str | None = None,
) -> Any:
    query = select(Blog).where(Blog.doctor_id == doctor_id).order_by(Blog.created_at.desc())
    if status:
        query = query.where(Blog.status == status)
    result = await db.execute(query)
    blogs = list(result.scalars().all())
    for blog in blogs:
        if blog.image_urls:
            blog.image_urls = await _resolve_image_urls(blog.image_urls)
    return blogs


@router.post("", response_model=BlogResponse, status_code=status.HTTP_201_CREATED)
async def content_create_blog(
    db: DbSession,
    payload: BlogCreate,
    doctor_id: VerifiedDoctorId,
) -> Any:
    blog = Blog(
        doctor_id=doctor_id,
        title=payload.title,
        status=BlogStatus.DRAFT.value,
    )
    db.add(blog)
    await db.flush()
    await db.commit()
    await db.refresh(blog)
    return blog


@router.get("/{blog_id}", response_model=BlogResponse)
async def content_get_blog(
    blog_id: int,
    db: DbSession,
    doctor_id: VerifiedDoctorId,
) -> Any:
    result = await db.execute(
        select(Blog).where(Blog.id == blog_id, Blog.doctor_id == doctor_id)
    )
    blog = result.scalar_one_or_none()
    if blog is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog not found")
    return blog


@router.put("/{blog_id}", response_model=BlogResponse)
async def content_update_blog(
    blog_id: int,
    payload: BlogUpdate,
    db: DbSession,
    doctor_id: VerifiedDoctorId,
) -> Any:
    result = await db.execute(
        select(Blog).where(Blog.id == blog_id, Blog.doctor_id == doctor_id)
    )
    blog = result.scalar_one_or_none()
    if blog is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog not found")

    if payload.title is not None:
        blog.title = payload.title
    if payload.subtitle is not None:
        blog.subtitle = payload.subtitle
    if payload.opening_quote is not None:
        blog.opening_quote = payload.opening_quote
    if payload.content is not None:
        blog.content = payload.content

    if payload.content:
        raw_text = payload.content.replace("<", " <").replace(">", "> ")
        words = len(re.findall(r"\w+", raw_text))
        blog.estimated_read_time = max(1, round(words / 200))

    if payload.keywords is not None:
        await db.execute(delete(BlogKeyword).where(BlogKeyword.blog_id == blog_id))
        for kw in payload.keywords:
            if kw.strip():
                db.add(BlogKeyword(blog_id=blog_id, keyword=kw.strip()))

    await db.commit()
    await db.refresh(blog)
    return blog


@router.post(
    "/{blog_id}/publish-practice-hub",
    response_model=BlogPublishPracticeHubResponse,
)
async def content_publish_blog_to_practice_hub(
    blog_id: int,
    payload: BlogPublishPracticeHubRequest,
    db: DbSession,
    doctor_id: VerifiedDoctorId,
) -> BlogPublishPracticeHubResponse:
    result = await db.execute(
        select(Blog).where(Blog.id == blog_id, Blog.doctor_id == doctor_id)
    )
    blog = result.scalar_one_or_none()
    if blog is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog not found")

    creds_repo = LinqmdCredentialsRepository(db)
    stored_creds = await creds_repo.get_by_doctor_id(doctor_id)
    if stored_creds is None and payload.credentials is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No LinQMD Practice Hub profile found. Contact admin to sync profile.",
        )

    using_override = payload.credentials is not None
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
    try:
        login_result = await hub_service.login(username, password)
    except LinqmdLoginError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "linqmd_credentials_invalid",
                "message": "Practice Hub login failed.",
                "error": str(exc),
            },
        ) from exc

    if using_override:
        if stored_creds is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No LinQMD profile to update. Contact admin to sync profile first.",
            )
        await creds_repo.update_credentials(doctor_id, username, password)

    image_bytes = None
    image_filename = None
    image_content_type = None
    if blog.image_urls and len(blog.image_urls) > 0:
        loaded = await hub_service.load_blog_image_from_storage(blog.image_urls[0])
        if loaded:
            image_bytes, image_filename, image_content_type = loaded

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

    try:
        practice_hub_response = await hub_service.publish_blog(
            login_result.access_token,
            hub_payload,
        )
    except LinqmdPublishError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "linqmd_publish_failed", "message": str(exc)},
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
    await db.commit()
    await db.refresh(blog)

    return BlogPublishPracticeHubResponse(
        blog_id=blog_id,
        status=blog.status,
        drupal_node_id=drupal_node_id,
        practice_hub_response=practice_hub_response,
    )


@router.post("/{blog_id}/publish")
async def content_publish_blog(
    blog_id: int,
    payload: BlogPublishConfig,
    db: DbSession,
    doctor_id: VerifiedDoctorId,
) -> dict[str, Any]:
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
async def content_delete_blog(
    blog_id: int,
    db: DbSession,
    doctor_id: VerifiedDoctorId,
) -> dict[str, Any]:
    result = await db.execute(
        select(Blog).where(Blog.id == blog_id, Blog.doctor_id == doctor_id)
    )
    blog = result.scalar_one_or_none()
    if blog is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog not found")
    await db.execute(delete(BlogKeyword).where(BlogKeyword.blog_id == blog_id))
    await db.delete(blog)
    await db.commit()
    return {
        "status": "success",
        "message": "Blog deleted successfully",
        "blog_id": blog_id,
    }


@router.post("/{blog_id}/images")
async def content_upload_blog_image(
    blog_id: int,
    db: DbSession,
    doctor_id: VerifiedDoctorId,
    file: UploadFile = File(...),
) -> dict[str, str]:
    from ....services.blob_storage_service import get_blob_storage_service

    result = await db.execute(
        select(Blog).where(Blog.id == blog_id, Blog.doctor_id == doctor_id)
    )
    blog = result.scalar_one_or_none()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")

    blob_service = get_blob_storage_service()
    file_bytes = await file.read()
    original_filename = file.filename or "image.jpg"
    upload_result = await blob_service.upload_from_bytes(
        content=file_bytes,
        file_name=original_filename,
        doctor_id=doctor_id,
        media_category="blogs",
    )
    if not upload_result.success:
        raise HTTPException(
            status_code=500,
            detail=f"Image upload failed: {upload_result.error_message}",
        )
    s3_key = upload_result.file_uri
    current_images = list(blog.image_urls) if blog.image_urls else []
    current_images.append(s3_key)
    blog.image_urls = current_images
    await db.commit()
    viewable_url = (await _resolve_image_urls([s3_key]))[0]
    return {"url": viewable_url, "message": "Image uploaded successfully"}
