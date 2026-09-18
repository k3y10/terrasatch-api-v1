"""Public request and response contracts for TerraSatch billing."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from terrasatch.billing.plans import BillingInterval, PlanCode


class EntitlementsResponse(BaseModel):
    max_sites: int | None
    max_members: int | None
    max_edge_devices: int | None
    max_channels: int | None
    included_processing_hours: int | None
    retention_days: int | None
    api_access: bool
    priority_support: bool


class BillingPlanResponse(BaseModel):
    code: PlanCode
    name: str
    description: str
    monthly_amount_cents: int | None
    annual_amount_cents: int | None
    trial_days: int
    self_service: bool
    recommended: bool
    entitlements: EntitlementsResponse


class CheckoutRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=255)
    email: str = Field(min_length=5, max_length=320)
    organization_name: str = Field(min_length=2, max_length=255)
    plan_code: PlanCode
    billing_interval: BillingInterval

    @field_validator("display_name", "organization_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("Value must contain at least two visible characters")
        return normalized

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        local, separator, domain = normalized.partition("@")
        if (
            not separator
            or not local
            or "." not in domain
            or domain.startswith(".")
            or domain.endswith(".")
        ):
            raise ValueError("A valid email address is required")
        return normalized


class CheckoutSessionResponse(BaseModel):
    signup_id: UUID
    checkout_session_id: str | None
    checkout_url: str
    expires_at: datetime
    plan_code: PlanCode
    billing_interval: BillingInterval
    trial_days: int
    amount_due_today_cents: Literal[0] = 0
    recurring_amount_cents: int


class CheckoutStatusResponse(BaseModel):
    state: Literal["processing", "ready", "expired"]
    plan_code: PlanCode
    billing_interval: BillingInterval
    recurring_amount_cents: int
    subscription_status: str | None
    service_access: Literal["full", "grace", "restricted", "legacy"] | None
    trial_ends_at: datetime | None
    current_period_end: datetime | None
    activation_required: bool


class SubscriptionResponse(BaseModel):
    organization_id: UUID
    managed: bool
    plan_code: PlanCode | None
    billing_interval: BillingInterval | None
    status: str
    service_access: Literal["full", "grace", "restricted", "legacy"]
    trial_ends_at: datetime | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    grace_ends_at: datetime | None
    entitlements: EntitlementsResponse | None


class CustomerPortalResponse(BaseModel):
    url: str


class ActivationRequest(BaseModel):
    token: str = Field(min_length=32, max_length=512)
    password: str = Field(min_length=12, max_length=256)


class ActivationResponse(BaseModel):
    activated: bool
    organization_id: UUID


class WebhookResponse(BaseModel):
    received: bool = True
    duplicate: bool = False


class EmailProviderWebhookResponse(BaseModel):
    received: bool = True
    matched: bool = False
    duplicate: bool = False
