from terrasatch.billing.plans import (
    BillingInterval,
    PlanCode,
    get_plan,
    public_plan_catalog,
)


def test_public_subscription_prices_are_stable() -> None:
    individual = get_plan(PlanCode.FIELD)
    team = get_plan(PlanCode.TEAM)
    site = get_plan(PlanCode.OPERATIONS)
    enterprise = get_plan(PlanCode.ENTERPRISE)

    assert individual.name == "Individual"
    assert individual.amount_cents(BillingInterval.MONTHLY) == 2_400
    assert individual.amount_cents(BillingInterval.ANNUAL) is None
    assert team.amount_cents(BillingInterval.MONTHLY) == 39_900
    assert team.amount_cents(BillingInterval.ANNUAL) is None
    assert site.amount_cents(BillingInterval.MONTHLY) == 199_900
    assert site.amount_cents(BillingInterval.ANNUAL) is None
    assert enterprise.amount_cents(BillingInterval.ANNUAL) is None
    assert {individual.trial_days, team.trial_days} == {30}
    assert site.trial_days == 0
    assert enterprise.trial_days == 0


def test_team_plan_is_recommended_and_has_expected_entitlements() -> None:
    team = get_plan(PlanCode.TEAM)

    assert team.recommended is True
    assert team.entitlements.max_sites == 1
    assert team.entitlements.max_members == 10
    assert team.entitlements.max_edge_devices == 6
    assert team.entitlements.max_channels == 12
    assert team.entitlements.included_processing_hours == 75
    assert team.entitlements.retention_days == 90
    assert team.entitlements.api_access is True


def test_individual_supports_one_personal_connection() -> None:
    individual = get_plan(PlanCode.FIELD)

    assert individual.self_service is True
    assert individual.entitlements.max_members == 1
    assert individual.entitlements.max_edge_devices == 1
    assert individual.entitlements.max_channels == 1
    assert individual.lookup_key(BillingInterval.MONTHLY) == "terrasatch_individual_monthly_v2"
    assert individual.lookup_key(BillingInterval.ANNUAL) is None


def test_site_and_enterprise_are_scoped_not_self_service() -> None:
    site = get_plan(PlanCode.OPERATIONS)
    enterprise = get_plan(PlanCode.ENTERPRISE)

    assert site.self_service is False
    assert site.lookup_key(BillingInterval.ANNUAL) is None
    assert enterprise.self_service is False
    assert enterprise.lookup_key(BillingInterval.ANNUAL) is None


def test_public_plan_catalog_never_exposes_stripe_lookup_keys() -> None:
    catalog = public_plan_catalog()

    assert [entry["code"] for entry in catalog] == [
        "field",
        "team",
        "operations",
        "enterprise",
    ]
    assert all("monthly_lookup_key" not in entry for entry in catalog)
    assert all("annual_lookup_key" not in entry for entry in catalog)
    assert all("stripe" not in key.casefold() for entry in catalog for key in entry)
