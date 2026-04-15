"""Shared Enums for the application.

Defines enum types used across models and schemas.
"""
from enum import Enum


class UserRole(str, Enum):
    """User role enum for authorization.
    
    Attributes:
        ADMIN: Full system access, can manage all resources
        OPERATION: Limited admin access for operation tasks
        USER: Regular doctor/user access (default for doctors)
    """
    ADMIN = "admin"
    OPERATION = "operation"
    USER = "user"

    @classmethod
    def default(cls) -> "UserRole":
        """Return the default role for new users."""
        return cls.USER


class BlogStatus(str, Enum):
    """Status of a blog post."""
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    REJECTED = "rejected"


class CommentStatus(str, Enum):
    """Status of a blog comment."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REPLIED = "replied"


class CommentAuthorType(str, Enum):
    """Type of author for a comment."""
    PATIENT = "patient"
    ANONYMOUS = "anonymous"
    SUSPICIOUS = "suspicious"
