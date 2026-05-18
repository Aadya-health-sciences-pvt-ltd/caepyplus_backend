"""Blog Studio API Endpoints.

Handles generic CRUD for Blogs, Comments, and AI/Drupal stubs.
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, UploadFile, File
from typing import Any
from datetime import datetime
import re

from sqlalchemy import select, delete

from ....core.security import require_authentication
from ....core.prompts import get_prompt_manager
from ....services.gemini_service import get_gemini_service
from ....db.session import DbSession
from ....models.blog import Blog, BlogKeyword, BlogComment
from ....schemas.blog import (
    BlogResponse,
    BlogCreate,
    BlogUpdate,
    BlogPublishConfig,
    BlogCommentResponse,
    CommentStatusUpdate,
    AITopicsResponse,
    AIKeywordSuggestionResponse,
    AITopicCard,
    AIBlogContentGenerateRequest,
    AIBlogContentResponse,
)
from ....models.enums import BlogStatus, CommentStatus, CommentAuthorType

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

# ---------------------------------------------------------------------------
# AI Suggestions (Static Paths First)
# ---------------------------------------------------------------------------

@router.get("/insights/topics", response_model=AITopicsResponse)
async def get_ai_topics() -> AITopicsResponse:
    """Get AI suggested blog topics for the doctor using Gemini."""
    try:
        gemini = get_gemini_service()
        prompts = get_prompt_manager()
        
        prompt = prompts.get_blog_topics_prompt()
        result = await gemini.generate_structured(prompt)
        return AITopicsResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate topics: {str(e)}"
        )

@router.get("/insights/keywords", response_model=AIKeywordSuggestionResponse)
async def get_ai_keywords(topic: str) -> AIKeywordSuggestionResponse:
    """Get AI suggested keywords based on the selected topic using Gemini."""
    try:
        gemini = get_gemini_service()
        prompts = get_prompt_manager()
        
        prompt = prompts.get_blog_keywords_prompt(topic)
        result = await gemini.generate_structured(prompt)
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
        result = await gemini.generate_structured(prompt)
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
    status: str | None = None,
    doctor_id_str: str = Depends(require_authentication),
) -> Any:
    """Get all comments for the authenticated doctor's blogs."""
    doctor_id = int(doctor_id_str)

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
    doctor_id_str: str = Depends(require_authentication),
) -> dict[str, Any]:
    """Approve or reject a comment."""
    doctor_id = int(doctor_id_str)

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
    status: str | None = None,
    doctor_id_str: str = Depends(require_authentication),
) -> Any:
    """List blogs for the authenticated doctor, optionally filtered by status."""
    doctor_id = int(doctor_id_str)
    
    query = select(Blog).where(Blog.doctor_id == doctor_id).order_by(Blog.created_at.desc())
    if status:
        query = query.where(Blog.status == status)
        
    result = await db.execute(query)
    blogs = list(result.scalars().all())
    
    # Hydrate image_urls with fresh presigned URLs so the browser can render them
    for blog in blogs:
        if blog.image_urls:
            blog.image_urls = await _resolve_image_urls(blog.image_urls)
    
    return blogs


@router.post("", response_model=BlogResponse, status_code=status.HTTP_201_CREATED)
async def create_blog(
    db: DbSession,
    payload: BlogCreate,
    doctor_id_str: str = Depends(require_authentication),
) -> Any:
    """Create a new draft blog for the authenticated doctor."""
    doctor_id = int(doctor_id_str)

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
async def get_blog(
    blog_id: int,
    db: DbSession,
    doctor_id_str: str = Depends(require_authentication),
) -> Any:
    """Get an existing blog by ID."""
    doctor_id = int(doctor_id_str)

    result = await db.execute(
        select(Blog).where(Blog.id == blog_id, Blog.doctor_id == doctor_id)
    )
    blog = result.scalar_one_or_none()
    if blog is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog not found")

    return blog


@router.put("/{blog_id}", response_model=BlogResponse)
async def update_blog(
    blog_id: int,
    payload: BlogUpdate,
    db: DbSession,
    doctor_id_str: str = Depends(require_authentication),
) -> Any:
    """Update a draft blog. Replaces keywords atomically."""
    doctor_id = int(doctor_id_str)

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
    
    return blog

@router.post("/{blog_id}/publish")
async def publish_blog(
    blog_id: int,
    payload: BlogPublishConfig,
    db: DbSession,
    doctor_id_str: str = Depends(require_authentication),
) -> dict[str, Any]:
    """Mark a blog as published."""
    doctor_id = int(doctor_id_str)

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
    doctor_id_str: str = Depends(require_authentication),
) -> dict[str, Any]:
    """Delete a blog (draft or published)."""
    doctor_id = int(doctor_id_str)

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
    file: UploadFile = File(...),
    doctor_id_str: str = Depends(require_authentication),
) -> dict[str, str]:
    """Upload an image for a blog post and store it in blob storage."""
    from fastapi import HTTPException
    import os
    import uuid
    import mimetypes
    from ....services.blob_storage_service import get_blob_storage_service

    doctor_id = int(doctor_id_str)
    
    # Verify ownership
    result = await db.execute(
        select(Blog).where(Blog.id == blog_id, Blog.doctor_id == doctor_id)
    )
    blog = result.scalar_one_or_none()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")

    blob_service = get_blob_storage_service()
    
    file_bytes = await file.read()
    original_filename = file.filename or "image.jpg"
    
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
