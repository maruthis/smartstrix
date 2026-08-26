"""Shared Pydantic response/request models used across routers.

Domain-specific request/response shapes that are only used by one router
live colocated in that router module instead of here, to keep this file
from becoming an unmanageable grab-bag.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(ORMModel):
    id: str
    email: str
    name: str
    two_factor_enabled: bool


class OrganizationOut(ORMModel):
    id: str
    name: str
    created_at: datetime


class MembershipOut(ORMModel):
    id: str
    org_id: str
    role: str
    user: UserOut


class MeOut(BaseModel):
    user: UserOut
    active_org: OrganizationOut | None
    role: str | None
    organizations: list[OrganizationOut]
