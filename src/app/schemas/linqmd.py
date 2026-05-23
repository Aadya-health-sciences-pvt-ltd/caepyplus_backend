"""Schemas for LinQMD credential storage and admin retrieval."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LinqMDCredentialsResponse(BaseModel):
    """Stored LinQMD credentials for a doctor (admin view)."""

    model_config = ConfigDict(from_attributes=True)

    doctor_id: int
    doctor_name: str
    linqmd_user_id: str
    linqmd_username: str
    linqmd_password: str
