from terrasatch.billing.plans import (
    BillingInterval,
    PlanCode,
    get_plan,
    public_plan_catalog,
)


def test_self_service_plan_prices_and_trial_are_stable() -> None:
    field = get_plan(PlanCode.FIELD)
    team = get_plan(PlanCode.TEAM)
    operations = get_plan(PlanCode.OPERATIONS)

    assert field.amount_cents(BillingInterval.MONTHLY) == 9_900
    assert field.amount_cents(BillingInterval.ANNUAL) == 99_000
    assert team.amount_cents(BillingInterval.MONTHLY) == 34_900
    assert team.amount_cents(BillingInterval.ANNUAL) == 349_000
    assert operations.amount_cents(BillingInterval.MONTHLY) == 99_900
    assert operations.amount_cents(BillingInterval.ANNUAL) == 999_000
    assert {field.trial_days, team.trial_days, operations.trial_days} == {30}


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


def test_enterprise_is_not_self_service() -> None:
    enterprise = get_plan(PlanCode.ENTERPRISE)

    assert enterprise.self_service is False
    assert enterprise.amount_cents(BillingInterval.MONTHLY) is None
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
