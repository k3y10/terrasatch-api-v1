"""Canonical TerraSatch subscription plans and service entitlements."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum


class PlanCode(StrEnum):
    FIELD = "field"
    TEAM = "team"
    OPERATIONS = "operations"
    ENTERPRISE = "enterprise"


class BillingInterval(StrEnum):
    MONTHLY = "monthly"
    ANNUAL = "annual"


@dataclass(frozen=True, slots=True)
class Entitlements:
    """Server-enforced operating limits associated with one subscription plan."""

    max_sites: int | None
    max_members: int | None
    max_edge_devices: int | None
    max_channels: int | None
    included_processing_hours: int | None
    retention_days: int | None
    api_access: bool
    priority_support: bool


@dataclass(frozen=True, slots=True)
class PlanDefinition:
    """Stable product definition independent from Stripe object IDs."""

    code: PlanCode
    name: str
    description: str
    monthly_amount_cents: int | None
    annual_amount_cents: int | None
    trial_days: int
    self_service: bool
    recommended: bool
    monthly_lookup_key: str | None
    annual_lookup_key: str | None
    entitlements: Entitlements

    def amount_cents(self, interval: BillingInterval) -> int | None:
        if interval == BillingInterval.MONTHLY:
            return self.monthly_amount_cents
        return self.annual_amount_cents

    def lookup_key(self, interval: BillingInterval) -> str | None:
        if interval == BillingInterval.MONTHLY:
            return self.monthly_lookup_key
        return self.annual_lookup_key

    def public_payload(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "name": self.name,
            "description": self.description,
            "monthly_amount_cents": self.monthly_amount_cents,
            "annual_amount_cents": self.annual_amount_cents,
            "trial_days": self.trial_days,
            "self_service": self.self_service,
            "recommended": self.recommended,
            "entitlements": asdict(self.entitlements),
        }


# Public pricing evaluation: $24/month Individual, $399/month Team,
# Operations from $1,999/month, Enterprise custom. Optional annual offers
# and agent add-ons remain proposals; scoped plans cannot enter Checkout.
PLAN_CATALOG: dict[PlanCode, PlanDefinition] = {
    PlanCode.FIELD: PlanDefinition(
        code=PlanCode.FIELD,
        name="Individual",
        description="Personal Satchy for one person in the field.",
        monthly_amount_cents=2_400,
        annual_amount_cents=None,
        trial_days=14,
        self_service=True,
        recommended=False,
        monthly_lookup_key="terrasatch_individual_monthly_v2",
        annual_lookup_key=None,
        entitlements=Entitlements(
            max_sites=1,
            max_members=1,
            max_edge_devices=1,
            max_channels=1,
            included_processing_hours=15,
            retention_days=14,
            api_access=False,
            priority_support=False,
        ),
    ),
    PlanCode.TEAM: PlanDefinition(
        code=PlanCode.TEAM,
        name="Team",
        description=(
            "For a working crew sharing radios, channels, maps, logs, and operational context."
        ),
        monthly_amount_cents=39_900,
        annual_amount_cents=None,
        trial_days=14,
        self_service=True,
        recommended=True,
        monthly_lookup_key="terrasatch_team_monthly_v2",
        annual_lookup_key=None,
        entitlements=Entitlements(
            max_sites=1,
            max_members=10,
            max_edge_devices=6,
            max_channels=12,
            included_processing_hours=75,
            retention_days=90,
            api_access=True,
            priority_support=False,
        ),
    ),
    PlanCode.OPERATIONS: PlanDefinition(
        code=PlanCode.OPERATIONS,
        name="Operations",
        description="From $1,999/month for a scoped site or department deployment.",
        monthly_amount_cents=199_900,
        annual_amount_cents=None,
        trial_days=0,
        self_service=False,
        recommended=False,
        monthly_lookup_key=None,
        annual_lookup_key=None,
        entitlements=Entitlements(
            max_sites=1,
            max_members=30,
            max_edge_devices=20,
            max_channels=40,
            included_processing_hours=250,
            retention_days=365,
            api_access=True,
            priority_support=True,
        ),
    ),
    PlanCode.ENTERPRISE: PlanDefinition(
        code=PlanCode.ENTERPRISE,
        name="Enterprise",
        description=(
            "Higher-touch multi-site, integrated, private-hosting, security, "
            "and support deployments."
        ),
        monthly_amount_cents=None,
        annual_amount_cents=None,
        trial_days=0,
        self_service=False,
        recommended=False,
        monthly_lookup_key=None,
        annual_lookup_key=None,
        entitlements=Entitlements(
            max_sites=None,
            max_members=None,
            max_edge_devices=None,
            max_channels=None,
            included_processing_hours=None,
            retention_days=None,
            api_access=True,
            priority_support=True,
        ),
    ),
}


def get_plan(plan_code: PlanCode | str) -> PlanDefinition:
    """Resolve a supported plan code or raise ValueError for untrusted input."""

    code = plan_code if isinstance(plan_code, PlanCode) else PlanCode(plan_code)
    return PLAN_CATALOG[code]


def public_plan_catalog() -> list[dict[str, object]]:
    """Return customer-safe plan data without Stripe lookup keys or IDs."""

    return [PLAN_CATALOG[code].public_payload() for code in PlanCode]
