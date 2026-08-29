from types import SimpleNamespace
from uuid import UUID

import pytest

from terrasatch.errors import InvalidConfiguration, TenantAccessDenied
from terrasatch.radio.activation_service import validate_edge_ingest_activation
from terrasatch.radio.schemas import ActivationMetadata, TransmissionCreateRequest

ORG_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
API_KEY_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
SITE_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
OTHER_SITE_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
CHANNEL_ID = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
DEFAULT_SITE = object()


class FakeSession:
    def __init__(self, device, site=DEFAULT_SITE):
        self.results = [device]
        if device is not None:
            self.results.append(site)

    async def scalar(self, _statement):
        return self.results.pop(0)


def _payload(*, site_id=SITE_ID, text="Routine radio traffic", channel_id=None, activation=None):
    return TransmissionCreateRequest(
        site_id=site_id,
        channel_id=channel_id,
        text=text,
        source="terrasatch-edge-stt",
        source_message_id="activation-service-test",
        activation=activation,
    )


def _device(*, enabled=True, site_id=SITE_ID, remote_config=None):
    return SimpleNamespace(
        enabled=enabled,
        site_id=site_id,
        remote_config=remote_config or {},
    )


@pytest.mark.asyncio
async def test_unpaired_service_credential_keeps_legacy_ingestion_behavior() -> None:
    decision = await validate_edge_ingest_activation(
        FakeSession(None),
        organization_id=ORG_ID,
        api_key_id=API_KEY_ID,
        payload=_payload(),
    )

    assert decision.accepted is True
    assert decision.enforced is False


@pytest.mark.asyncio
async def test_paired_edge_is_always_bound_to_its_assigned_site() -> None:
    with pytest.raises(TenantAccessDenied, match="paired Edge device"):
        await validate_edge_ingest_activation(
            FakeSession(_device(site_id=SITE_ID)),
            organization_id=ORG_ID,
            api_key_id=API_KEY_ID,
            payload=_payload(site_id=OTHER_SITE_ID),
        )


@pytest.mark.asyncio
async def test_paired_edge_accepts_its_enabled_assigned_site() -> None:
    decision = await validate_edge_ingest_activation(
        FakeSession(_device()),
        organization_id=ORG_ID,
        api_key_id=API_KEY_ID,
        payload=_payload(),
    )
    assert decision.accepted is True


@pytest.mark.asyncio
async def test_paired_edge_rejects_disabled_assigned_site() -> None:
    with pytest.raises(TenantAccessDenied, match="site is disabled"):
        await validate_edge_ingest_activation(
            FakeSession(_device(), site=None),
            organization_id=ORG_ID,
            api_key_id=API_KEY_ID,
            payload=_payload(),
        )


@pytest.mark.asyncio
async def test_paired_edge_rejects_assigned_site_unavailable_in_organization() -> None:
    with pytest.raises(TenantAccessDenied, match="unavailable"):
        await validate_edge_ingest_activation(
            FakeSession(_device(site_id=OTHER_SITE_ID), site=None),
            organization_id=ORG_ID,
            api_key_id=API_KEY_ID,
            payload=_payload(site_id=OTHER_SITE_ID),
        )


@pytest.mark.asyncio
async def test_disabled_paired_edge_cannot_ingest() -> None:
    with pytest.raises(TenantAccessDenied, match="disabled"):
        await validate_edge_ingest_activation(
            FakeSession(_device(enabled=False)),
            organization_id=ORG_ID,
            api_key_id=API_KEY_ID,
            payload=_payload(),
        )


@pytest.mark.asyncio
async def test_paired_edge_can_require_phrase_and_logical_channel_without_partner_code() -> None:
    device = _device(
        remote_config={
            "radio": {
                "ai_channel": {
                    "activation_required": True,
                    "activation_phrase": "Field Team to TerraSatch",
                    "activation_position": "start",
                    "logical_channel_id": str(CHANNEL_ID),
                }
            }
        }
    )
    decision = await validate_edge_ingest_activation(
        FakeSession(device),
        organization_id=ORG_ID,
        api_key_id=API_KEY_ID,
        payload=_payload(
            channel_id=CHANNEL_ID,
            text="Field Team to TerraSatch. Wind loading observed near the ridge.",
            activation=ActivationMetadata(
                detected=True,
                phrase="Field Team to TerraSatch",
                confidence=0.94,
            ),
        ),
    )

    assert decision.enforced is True
    assert decision.intelligence_text == "Wind loading observed near the ridge."


@pytest.mark.asyncio
async def test_paired_edge_rejects_other_phrase_when_gate_is_required() -> None:
    device = _device(
        remote_config={
            "radio": {
                "ai_channel": {
                    "activation_required": True,
                    "activation_phrase": "Field Team to TerraSatch",
                }
            }
        }
    )
    with pytest.raises(InvalidConfiguration, match="did not begin"):
        await validate_edge_ingest_activation(
            FakeSession(device),
            organization_id=ORG_ID,
            api_key_id=API_KEY_ID,
            payload=_payload(text="Other Team to TerraSatch. Wind loading observed."),
        )
