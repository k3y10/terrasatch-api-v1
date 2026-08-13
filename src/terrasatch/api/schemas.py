"""Schemas shared by public API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    details: dict[str, object] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


class DependencyStatus(BaseModel):
    name: str
    status: Literal["healthy", "unhealthy"]
    detail: str | None = None


class HealthResponse(BaseModel):
    service: Literal["TerraSatch API"] = "TerraSatch API"
    status: Literal["healthy", "unhealthy"]
    environment: str
    deployment: str
    version: str
    timestamp: datetime
    dependencies: list[DependencyStatus] = Field(default_factory=list)


class ComponentStatus(BaseModel):
    name: str
    status: Literal["healthy", "unhealthy", "disabled"]
    detail: str | None = None


class ApiCatalogEntry(BaseModel):
    method: str
    path: str
    authorization: Literal["public", "bearer_api_key", "admin_session"]
    summary: str | None = None


class ErrorCodeReference(BaseModel):
    http_status: int
    code: str
    meaning: str


class QualityReport(BaseModel):
    status: Literal["pass", "degraded"]
    generated_at: datetime
    components: list[ComponentStatus]
    endpoints: list[ApiCatalogEntry]
    common_errors: list[ErrorCodeReference]


class SiteCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class SiteUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    enabled: bool | None = None


class SiteResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    slug: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class TeamCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    site_id: UUID | None = None


class TeamUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    site_id: UUID | None = None
    enabled: bool | None = None


class TeamResponse(BaseModel):
    id: UUID
    organization_id: UUID
    site_id: UUID | None
    name: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scopes: list[str] = Field(min_length=1, max_length=32)


class ApiKeyResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    revoked_at: datetime | None


class IssuedApiKeyResponse(ApiKeyResponse):
    token: str
