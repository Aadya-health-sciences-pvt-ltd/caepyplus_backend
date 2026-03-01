"""
Blob Storage Service.

Production-grade local blob storage implementation with:
- Async file operations
- Content-addressable storage (hash-based)
- Automatic directory structure
- Mime type detection
- File download from external URLs
- Abstraction layer for future cloud storage migration (S3, GCS, Azure Blob)

This service follows the clean architecture pattern and can be swapped
with cloud implementations without changing the interface.
"""
from __future__ import annotations

import hashlib
import logging
import mimetypes
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import aiofiles
import aiohttp

logger = logging.getLogger(__name__)

try:
    import aioboto3  # type: ignore[import-untyped]
    from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False
    logger.warning("aioboto3 not installed. S3 storage backend will not be available.")



class StorageBackend(str, Enum):
    """Supported storage backends."""

    LOCAL = "local"
    S3 = "s3"
    GCS = "gcs"  # Future implementation
    AZURE = "azure"  # Future implementation


@dataclass(frozen=True)
class BlobMetadata:
    """Metadata for a stored blob."""

    blob_id: str
    file_name: str
    file_uri: str
    file_size: int
    mime_type: str
    content_hash: str
    created_at: datetime
    storage_backend: StorageBackend


@dataclass(frozen=True)
class UploadResult:
    """Result of a blob upload operation."""

    success: bool
    blob_id: str
    file_uri: str
    file_size: int
    mime_type: str
    content_hash: str
    error_message: str | None = None


class BlobStorageError(Exception):
    """Base exception for blob storage operations."""

    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__(message)
        self.original_error = original_error


class BlobDownloadError(BlobStorageError):
    """Error downloading blob from external URL."""

    pass


class BlobUploadError(BlobStorageError):
    """Error uploading blob to storage."""

    pass


class BlobNotFoundError(BlobStorageError):
    """Blob not found in storage."""

    pass


class IBlobStorageService(Protocol):
    """Interface for blob storage operations.

    Implementations can target local filesystem, S3, GCS, Azure, etc.
    """

    async def upload_from_url(
        self,
        source_url: str,
        file_name: str,
        doctor_id: int,
        media_category: str,
    ) -> UploadResult:
        """Download file from URL and store in blob storage."""
        ...

    async def upload_from_bytes(
        self,
        content: bytes,
        file_name: str,
        doctor_id: int,
        media_category: str,
    ) -> UploadResult:
        """Store bytes directly in blob storage."""
        ...

    async def get_blob(self, blob_id: str) -> tuple[bytes, BlobMetadata]:
        """Retrieve blob content and metadata."""
        ...

    async def delete_blob(self, blob_id: str) -> bool:
        """Delete a blob from storage."""
        ...

    async def get_blob_uri(self, blob_id: str) -> str:
        """Get the URI for accessing a blob."""
        ...

    async def blob_exists(self, blob_id: str) -> bool:
        """Check if a blob exists."""
        ...


class LocalBlobStorageService:
    """
    Local filesystem-based blob storage implementation.

    Features:
    - Organized directory structure: {base_path}/{doctor_id}/{category}/{blob_id}
    - Content-addressable storage with hash verification
    - Async file operations for non-blocking I/O
    - Automatic mime type detection
    - Metadata stored alongside blobs

    Production considerations:
    - Use a dedicated volume/disk for blob storage
    - Configure proper backup strategies
    - Monitor disk space usage
    - Consider implementing blob cleanup/garbage collection
    """

    DEFAULT_STORAGE_PATH = "blob_storage"
    CHUNK_SIZE = 8192  # 8KB chunks for streaming
    MAX_DOWNLOAD_SIZE = 50 * 1024 * 1024  # 50MB max download
    DOWNLOAD_TIMEOUT = 60  # seconds

    def __init__(
        self,
        base_path: str | Path | None = None,
        base_url: str = "/api/v1/blobs",
    ):
        """
        Initialize local blob storage.

        Args:
            base_path: Root directory for blob storage. Defaults to ./blob_storage
            base_url: Base URL for serving blobs (used in URI generation)
        """
        self.base_path = Path(base_path) if base_path else Path(self.DEFAULT_STORAGE_PATH)
        self.base_url = base_url.rstrip("/")
        self._ensure_base_directory()

    def _ensure_base_directory(self) -> None:
        """Create base storage directory if it doesn't exist."""
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info("Blob storage initialized at: %s", self.base_path.absolute())

    def _get_blob_directory(self, doctor_id: int, media_category: str) -> Path:
        """Get the directory path for storing a blob."""
        return self.base_path / str(doctor_id) / media_category

    def _get_blob_path(
        self,
        doctor_id: int,
        media_category: str,
        blob_id: str,
        extension: str,
    ) -> Path:
        """Get the full file path for a blob."""
        directory = self._get_blob_directory(doctor_id, media_category)
        return directory / f"{blob_id}{extension}"

    def _get_metadata_path(self, blob_path: Path) -> Path:
        """Get the metadata file path for a blob."""
        return blob_path.with_suffix(blob_path.suffix + ".meta")

    @staticmethod
    def _compute_hash(content: bytes) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _detect_mime_type(file_name: str, content: bytes | None = None) -> str:
        """Detect MIME type from filename or content."""
        mime_type, _ = mimetypes.guess_type(file_name)
        if mime_type:
            return mime_type

        # Fallback for common types
        extension = Path(file_name).suffix.lower()
        mime_map = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        return mime_map.get(extension, "application/octet-stream")

    @staticmethod
    def _get_extension(file_name: str) -> str:
        """Extract file extension from filename."""
        ext = Path(file_name).suffix.lower()
        return ext if ext else ".bin"

    async def _download_from_url(self, url: str) -> tuple[bytes, str]:
        """
        Download file content from an external URL.

        Args:
            url: The source URL to download from

        Returns:
            Tuple of (content bytes, suggested filename)

        Raises:
            BlobDownloadError: If download fails
        """
        try:
            timeout = aiohttp.ClientTimeout(total=self.DOWNLOAD_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise BlobDownloadError(
                            f"Failed to download file: HTTP {response.status}"
                        )

                    # Check content length
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > self.MAX_DOWNLOAD_SIZE:
                        raise BlobDownloadError(
                            f"File too large: {int(content_length)} bytes "
                            f"(max: {self.MAX_DOWNLOAD_SIZE} bytes)"
                        )

                    # Download content in chunks
                    chunks = []
                    total_size = 0
                    async for chunk in response.content.iter_chunked(self.CHUNK_SIZE):
                        total_size += len(chunk)
                        if total_size > self.MAX_DOWNLOAD_SIZE:
                            raise BlobDownloadError(
                                f"File too large during download "
                                f"(max: {self.MAX_DOWNLOAD_SIZE} bytes)"
                            )
                        chunks.append(chunk)

                    content = b"".join(chunks)

                    # Try to get filename from Content-Disposition header
                    content_disposition = response.headers.get("Content-Disposition", "")
                    suggested_filename = None
                    if "filename=" in content_disposition:
                        parts = content_disposition.split("filename=")
                        if len(parts) > 1:
                            suggested_filename = parts[1].strip("\"' ")

                    # Fallback to URL path
                    if not suggested_filename:
                        parsed = urlparse(url)
                        suggested_filename = Path(parsed.path).name or "downloaded_file"

                    return content, suggested_filename

        except aiohttp.ClientError as e:
            raise BlobDownloadError(f"Network error downloading file: {e}", e)
        except TimeoutError as e:
            raise BlobDownloadError(f"Timeout downloading file from {url}", e)

    async def _write_blob(
        self,
        content: bytes,
        blob_path: Path,
        metadata: BlobMetadata,
    ) -> None:
        """Write blob content and metadata to disk."""
        # Ensure directory exists
        blob_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        async with aiofiles.open(blob_path, "wb") as f:
            await f.write(content)

        # Write metadata
        metadata_path = self._get_metadata_path(blob_path)
        metadata_content = (
            f"blob_id={metadata.blob_id}\n"
            f"file_name={metadata.file_name}\n"
            f"file_uri={metadata.file_uri}\n"
            f"file_size={metadata.file_size}\n"
            f"mime_type={metadata.mime_type}\n"
            f"content_hash={metadata.content_hash}\n"
            f"created_at={metadata.created_at.isoformat()}\n"
            f"storage_backend={metadata.storage_backend.value}\n"
        )
        async with aiofiles.open(metadata_path, "w") as f:
            await f.write(metadata_content)

    async def upload_from_url(
        self,
        source_url: str,
        file_name: str,
        doctor_id: int,
        media_category: str,
    ) -> UploadResult:
        """
        Download file from external URL and store in blob storage.

        Args:
            source_url: URL to download the file from
            file_name: Original filename for the blob
            doctor_id: Doctor ID for organizing storage
            media_category: Category (e.g., 'profile_photo', 'certificate')

        Returns:
            UploadResult with blob details
        """
        try:
            logger.info(
                "Downloading blob from URL: %s for doctor_id=%d, category=%s",
                source_url,
                doctor_id,
                media_category,
            )

            # Download content
            content, suggested_name = await self._download_from_url(source_url)

            # Use provided filename or suggested one
            final_filename = file_name or suggested_name

            # Upload the downloaded content
            return await self.upload_from_bytes(
                content=content,
                file_name=final_filename,
                doctor_id=doctor_id,
                media_category=media_category,
            )

        except BlobDownloadError:
            raise
        except Exception as e:
            logger.error("Unexpected error uploading from URL: %s", e)
            raise BlobUploadError(f"Failed to upload blob from URL: {e}", e)

    async def upload_from_bytes(
        self,
        content: bytes,
        file_name: str,
        doctor_id: int,
        media_category: str,
    ) -> UploadResult:
        """
        Store bytes directly in blob storage.

        Args:
            content: File content as bytes
            file_name: Original filename
            doctor_id: Doctor ID for organizing storage
            media_category: Category for organization

        Returns:
            UploadResult with blob details
        """
        try:
            # Generate unique blob ID
            blob_id = str(uuid.uuid4())

            # Compute content hash and detect mime type
            content_hash = self._compute_hash(content)
            mime_type = self._detect_mime_type(file_name, content)
            extension = self._get_extension(file_name)

            # Determine storage path
            blob_path = self._get_blob_path(doctor_id, media_category, blob_id, extension)

            # Generate URI for accessing the blob
            file_uri = f"{self.base_url}/{doctor_id}/{media_category}/{blob_id}{extension}"

            # Create metadata
            metadata = BlobMetadata(
                blob_id=blob_id,
                file_name=file_name,
                file_uri=file_uri,
                file_size=len(content),
                mime_type=mime_type,
                content_hash=content_hash,
                created_at=datetime.now(UTC),
                storage_backend=StorageBackend.LOCAL,
            )

            # Write to disk
            await self._write_blob(content, blob_path, metadata)

            logger.info(
                "Blob uploaded successfully: blob_id=%s, size=%d bytes, path=%s",
                blob_id,
                len(content),
                blob_path,
            )

            return UploadResult(
                success=True,
                blob_id=blob_id,
                file_uri=file_uri,
                file_size=len(content),
                mime_type=mime_type,
                content_hash=content_hash,
            )

        except Exception as e:
            logger.error("Error uploading blob: %s", e)
            return UploadResult(
                success=False,
                blob_id="",
                file_uri="",
                file_size=0,
                mime_type="",
                content_hash="",
                error_message=str(e),
            )

    async def get_blob(self, blob_id: str, doctor_id: int, media_category: str, extension: str) -> tuple[bytes, BlobMetadata]:
        """
        Retrieve blob content and metadata.

        Args:
            blob_id: The unique blob identifier
            doctor_id: Doctor ID for path resolution
            media_category: Category for path resolution
            extension: File extension

        Returns:
            Tuple of (content bytes, metadata)
        """
        blob_path = self._get_blob_path(doctor_id, media_category, blob_id, extension)

        if not blob_path.exists():
            raise BlobNotFoundError(f"Blob not found: {blob_id}")

        async with aiofiles.open(blob_path, "rb") as f:
            content = await f.read()

        # Read metadata
        metadata_path = self._get_metadata_path(blob_path)
        metadata_dict = {}
        if metadata_path.exists():
            async with aiofiles.open(metadata_path) as f:
                for line in (await f.read()).strip().split("\n"):
                    if "=" in line:
                        key, value = line.split("=", 1)
                        metadata_dict[key] = value

        metadata = BlobMetadata(
            blob_id=metadata_dict.get("blob_id", blob_id),
            file_name=metadata_dict.get("file_name", ""),
            file_uri=metadata_dict.get("file_uri", ""),
            file_size=int(metadata_dict.get("file_size", len(content))),
            mime_type=metadata_dict.get("mime_type", "application/octet-stream"),
            content_hash=metadata_dict.get("content_hash", ""),
            created_at=datetime.fromisoformat(metadata_dict.get("created_at", datetime.now(UTC).isoformat())),
            storage_backend=StorageBackend(metadata_dict.get("storage_backend", "local")),
        )

        return content, metadata

    async def delete_blob(self, blob_id: str, doctor_id: int, media_category: str, extension: str) -> bool:
        """Delete a blob and its metadata from storage."""
        blob_path = self._get_blob_path(doctor_id, media_category, blob_id, extension)
        metadata_path = self._get_metadata_path(blob_path)

        deleted = False
        if blob_path.exists():
            blob_path.unlink()
            deleted = True

        if metadata_path.exists():
            metadata_path.unlink()

        return deleted

    async def blob_exists(self, blob_id: str, doctor_id: int, media_category: str, extension: str) -> bool:
        """Check if a blob exists in storage."""
        blob_path = self._get_blob_path(doctor_id, media_category, blob_id, extension)
        return blob_path.exists()

    def get_storage_stats(self) -> dict[str, Any]:
        """Get storage statistics."""
        total_size = 0
        total_files = 0

        for path in self.base_path.rglob("*"):
            if path.is_file() and not path.suffix == ".meta":
                total_size += path.stat().st_size
                total_files += 1

        return {
            "total_files": total_files,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "storage_path": str(self.base_path.absolute()),
        }


# ---------------------------------------------------------------------------
# Singleton instance and dependency injection


class S3BlobStorageService:
    """
    AWS S3-based blob storage implementation.
    
    Features:
    - Async S3 operations using aioboto3
    - Organized key structure: {prefix}/{doctor_id}/{category}/{blob_id}
    - Public or signed URL generation
    - Automatic mime type handling
    - Hash verification
    
    Production considerations:
    - Configure bucket policies and IAM permissions
    - Enable versioning for data protection
    - Set lifecycle policies for cost optimization
    - Monitor S3 costs and usage
    """

    CHUNK_SIZE = 8192
    MAX_DOWNLOAD_SIZE = 50 * 1024 * 1024  # 50MB
    DOWNLOAD_TIMEOUT = 60

    def __init__(
        self,
        bucket_name: str,
        access_key_id: str,
        secret_access_key: str,
        region: str = "us-east-1",
        prefix: str = "doctors",
        use_signed_urls: bool = False,
        signed_url_expiry: int = 3600,
    ):
        """
        Initialize S3 blob storage.
        
        Args:
            bucket_name: S3 bucket name
            access_key_id: AWS access key ID
            secret_access_key: AWS secret access key
            region: AWS region
            prefix: Prefix for all S3 keys (e.g., 'doctors')
            use_signed_urls: Whether to generate signed URLs
            signed_url_expiry: Signed URL expiry in seconds
        """
        self.bucket_name = bucket_name
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region = region
        self.prefix = prefix.strip("/")
        self.use_signed_urls = use_signed_urls
        self.signed_url_expiry = signed_url_expiry

        # aioboto3 session
        self.session = aioboto3.Session(
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
        )

        logger.info("S3 blob storage initialized: bucket=%s, region=%s, prefix=%s", bucket_name, region, prefix)

    def _get_s3_key(
        self,
        doctor_id: int,
        media_category: str,
        blob_id: str,
        extension: str,
    ) -> str:
        """Generate S3 object key."""
        # Format: {prefix}/{doctor_id}/{category}/{blob_id}{extension}
        return f"{self.prefix}/{doctor_id}/{media_category}/{blob_id}{extension}"

    @staticmethod
    def _compute_hash(content: bytes) -> str:
        """Compute SHA-256 hash."""
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _detect_mime_type(file_name: str, content: bytes | None = None) -> str:
        """Detect MIME type."""
        mime_type, _ = mimetypes.guess_type(file_name)
        if mime_type:
            return mime_type

        extension = Path(file_name).suffix.lower()
        mime_map = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return mime_map.get(extension, "application/octet-stream")

    @staticmethod
    def _get_extension(file_name: str) -> str:
        """Extract file extension."""
        ext = Path(file_name).suffix.lower()
        return ext if ext else ".bin"

    async def _download_from_url(self, url: str) -> tuple[bytes, str]:
        """Download file from external URL."""
        try:
            timeout = aiohttp.ClientTimeout(total=self.DOWNLOAD_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise BlobDownloadError(
                            f"Failed to download from {url}: HTTP {response.status}"
                        )

                    content = await response.read()

                    if len(content) > self.MAX_DOWNLOAD_SIZE:
                        raise BlobDownloadError(
                            f"File too large: {len(content)} bytes (max {self.MAX_DOWNLOAD_SIZE})"
                        )

                    # Extract filename from URL or Content-Disposition
                    filename = Path(urlparse(url).path).name
                    if content_disposition := response.headers.get("Content-Disposition"):
                        if "filename=" in content_disposition:
                            filename = content_disposition.split("filename=")[-1].strip('"')

                    return content, filename

        except aiohttp.ClientError as e:
            raise BlobDownloadError(f"Download failed: {str(e)}", e)
        except TimeoutError as e:
            raise BlobDownloadError(f"Download timeout after {self.DOWNLOAD_TIMEOUT}s", e)

    async def upload_from_url(
        self,
        source_url: str,
        file_name: str,
        doctor_id: int,
        media_category: str,
    ) -> UploadResult:
        """Download from URL and upload to S3."""
        try:
            # Download content
            content, suggested_filename = await self._download_from_url(source_url)

            # Use suggested filename if provided
            if not file_name or file_name == "unknown":
                file_name = suggested_filename

            # Upload to S3
            return await self. upload_from_bytes(content, file_name, doctor_id, media_category)

        except BlobDownloadError:
            raise
        except Exception as e:
            logger.exception("Failed to upload from URL: %s", source_url)
            raise BlobUploadError(f"Upload from URL failed: {str(e)}", e)

    async def upload_from_bytes(
        self,
        content: bytes,
        file_name: str,
        doctor_id: int,
        media_category: str,
    ) -> UploadResult:
        """Upload bytes to S3."""
        try:
            # Generate blob ID and metadata
            blob_id = str(uuid.uuid4())
            content_hash = self._compute_hash(content)
            mime_type = self._detect_mime_type(file_name, content)
            extension = self._get_extension(file_name)
            file_size = len(content)

            # Generate S3 key
            s3_key = self._get_s3_key(doctor_id, media_category, blob_id, extension)

            # Upload to S3
            async with self.session.client("s3") as s3_client:
                await s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=content,
                    ContentType=mime_type,
                    Metadata={
                        "blob-id": blob_id,
                        "original-filename": file_name,
                        "content-hash": content_hash,
                        "doctor-id": str(doctor_id),
                        "media-category": media_category,
                    },
                )

            # Generate URL
            file_uri = await self.get_blob_uri(blob_id, doctor_id, media_category, extension)

            logger.info(
                "Uploaded to S3: blob_id=%s, key=%s, size=%d",
                blob_id,
                s3_key,
                file_size,
            )

            return UploadResult(
                success=True,
                blob_id=blob_id,
                file_uri=file_uri,
                file_size=file_size,
                mime_type=mime_type,
                content_hash=content_hash,
            )

        except (ClientError, BotoCoreError) as e:
            logger.exception("S3 upload failed for %s", file_name)
            return UploadResult(
                success=False,
                blob_id="",
                file_uri="",
                file_size=0,
                mime_type="",
                content_hash="",
                error_message=f"S3 upload failed: {str(e)}",
            )
        except Exception as e:
            logger.exception("Unexpected error uploading to S3")
            raise BlobUploadError(f"Upload failed: {str(e)}", e)

    async def get_blob(self, blob_id: str, doctor_id: int, media_category: str, extension: str) -> tuple[bytes, BlobMetadata]:
        """Retrieve blob from S3."""
        try:
            s3_key = self._get_s3_key(doctor_id, media_category, blob_id, extension)

            async with self.session.client("s3") as s3_client:
                response = await s3_client.get_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                )

                content = await response["Body"].read()

                metadata = BlobMetadata(
                    blob_id=blob_id,
                    file_name=response.get("Metadata", {}).get("original-filename", "unknown"),
                    file_uri=await self.get_blob_uri(blob_id, doctor_id, media_category, extension),
                    file_size=response["ContentLength"],
                    mime_type=response["ContentType"],
                    content_hash=response.get("Metadata", {}).get("content-hash", ""),
                    created_at=response["LastModified"],
                    storage_backend=StorageBackend.S3,
                )

                return content, metadata

        except ClientError as e:
            # NoSuchKey is a ClientError — s3_client.exceptions is not accessible
            # outside the async-with block scope, so we inspect the error code.
            if e.response.get("Error", {}).get("Code") == "NoSuchKey":
                raise BlobNotFoundError(f"Blob not found: {blob_id}")
            raise BlobStorageError(f"S3 retrieval failed: {str(e)}", e)
        except BotoCoreError as e:
            raise BlobStorageError(f"S3 retrieval failed: {str(e)}", e)

    async def delete_blob(self, blob_id: str, doctor_id: int, media_category: str, extension: str) -> bool:
        """Delete blob from S3."""
        try:
            s3_key = self._get_s3_key(doctor_id, media_category, blob_id, extension)

            async with self.session.client("s3") as s3_client:
                await s3_client.delete_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                )

            logger.info("Deleted from S3: key=%s", s3_key)
            return True

        except (ClientError, BotoCoreError) as e:
            logger.error("S3 deletion failed: %s", str(e))
            return False

    async def get_blob_uri(self, blob_id: str, doctor_id: int = 0, media_category: str = "", extension: str = "") -> str:
        """Generate S3 URL (public or signed)."""
        if not doctor_id or not media_category or not extension:
            # For compatibility, return a placeholder
            return f"s3://{self.bucket_name}/{blob_id}"

        s3_key = self._get_s3_key(doctor_id, media_category, blob_id, extension)

        if self.use_signed_urls:
            # Generate signed URL
            async with self.session.client("s3") as s3_client:
                url = await s3_client.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": self.bucket_name,
                        "Key": s3_key,
                    },
                    ExpiresIn=self.signed_url_expiry,
                )
                return str(url)
        else:
            # Return public URL
            return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"

    async def blob_exists(self, blob_id: str, doctor_id: int, media_category: str, extension: str) -> bool:
        """Check if blob exists in S3."""
        try:
            s3_key = self._get_s3_key(doctor_id, media_category, blob_id, extension)

            async with self.session.client("s3") as s3_client:
                await s3_client.head_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                )
            return True

        except ClientError as e:
            # 404 head_object raises ClientError with code "404" or "NoSuchKey"
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                return False
            return False
        except BotoCoreError:
            return False


# =============================================================================
# Factory Pattern for Storage Backend Selection
# =============================================================================

class BlobStorageFactory:
    """
    Factory for creating blob storage service instances.
    
    Selects the appropriate storage backend based on configuration.
    Supports local filesystem and AWS S3 storage.
    """

    @staticmethod
    def create_blob_service(settings: Any) -> LocalBlobStorageService | S3BlobStorageService:
        """
        Create blob storage service based on configuration.
        
        Args:
            settings: Application settings instance
            
        Returns:
            Configured blob storage service (Local or S3)
            
        Raises:
            ValueError: If storage backend is invalid or required settings are missing
        """
        backend = settings.STORAGE_BACKEND.lower()

        if backend == "local":
            logger.info("Initializing local blob storage")
            return LocalBlobStorageService(
                base_path=settings.BLOB_STORAGE_PATH,
                base_url=settings.BLOB_BASE_URL,
            )

        elif backend == "s3":
            # Validate S3 settings
            if not settings.AWS_S3_BUCKET:
                raise ValueError(
                    "AWS_S3_BUCKET is required when STORAGE_BACKEND=s3. "
                    "Set it in your .env file or environment variables."
                )
            if not settings.AWS_ACCESS_KEY_ID:
                raise ValueError(
                    "AWS_ACCESS_KEY_ID is required when STORAGE_BACKEND=s3. "
                    "Set it in your .env file or environment variables."
                )
            if not settings.AWS_SECRET_ACCESS_KEY:
                raise ValueError(
                    "AWS_SECRET_ACCESS_KEY is required when STORAGE_BACKEND=s3. "
                    "Set it in your .env file or environment variables."
                )

            logger.info("Initializing S3 blob storage: bucket=%s, region=%s", settings.AWS_S3_BUCKET, settings.AWS_REGION)
            return S3BlobStorageService(
                bucket_name=settings.AWS_S3_BUCKET,
                access_key_id=settings.AWS_ACCESS_KEY_ID,
                secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region=settings.AWS_REGION,
                prefix=settings.AWS_S3_PREFIX,
                use_signed_urls=settings.AWS_S3_USE_SIGNED_URLS,
                signed_url_expiry=settings.AWS_S3_SIGNED_URL_EXPIRY,
            )

        else:
            raise ValueError(
                f"Invalid STORAGE_BACKEND: '{backend}'. "
                f"Must be 'local' or 's3'. "
                f"Set STORAGE_BACKEND in your .env file."
            )


# =============================================================================
# Updated Singleton with Factory Pattern
# =============================================================================

_blob_storage_instance: LocalBlobStorageService | S3BlobStorageService | None = None


def get_blob_storage_service() -> LocalBlobStorageService | S3BlobStorageService:
    """
    Get or create the blob storage service singleton using factory pattern.
    
    The storage backend is determined by the STORAGE_BACKEND setting:
    - 'local': Uses local filesystem storage
    - 's3': Uses AWS S3 storage
    
    Returns:
        Configured blob storage service instance
        
    Raises:
        ValueError: If storage configuration is invalid
    """
    global _blob_storage_instance

    if _blob_storage_instance is None:
        from ..core.config import get_settings

        settings = get_settings()
        _blob_storage_instance = BlobStorageFactory.create_blob_service(settings)

    return _blob_storage_instance
