"""Authenticated Edge binding for optional radio activation enforcement."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.edge.models import EdgeDevice
from terrasatch.errors import InvalidConfiguration
from terrasatch.radio.activation import (
    ActivationDecision,
    ActivationEvidence,
    activation_policy_from_remote_config,
    evaluate_activation,
)
from terrasatch.radio.schemas import TransmissionCreateRequest


async def validate_edge_ingest_activation(
    session: AsyncSession,
    *,
    organization_id: UUID,
    api_key_id: UUID,
    payload: TransmissionCreateRequest,
) -> ActivationDecision:
    """Validate paired-Edge site/channel/activation policy before canonical ingestion.

    Existing non-device service credentials with ``edge:ingest`` keep legacy behavior.
    A paired Edge credential is always bound to its assigned organization and site. The
    activation phrase is enforced only when that device explicitly enables the gate in
    its existing remote config.
    """

    device = await session.scalar(
        select(EdgeDevice).where(
            EdgeDevice.organization_id == organization_id,
            EdgeDevice.api_key_id == api_key_id,
        )
    )

    if device is None:
        # Backward compatibility for existing service credentials that predate pairing.
        return evaluate_activation(
            policy=activation_policy_from_remote_config({}),
            text=payload.text,
            channel_id=payload.channel_id,
        )

    if not device.enabled:
        raise InvalidConfiguration("Paired Edge device is disabled")
    if device.site_id != payload.site_id:
        raise InvalidConfiguration("Transmission site does not match the paired Edge device")

    evidence: ActivationEvidence | None = None
    if payload.activation is not None:
        evidence = ActivationEvidence(
            detected=payload.activation.detected,
            phrase=payload.activation.phrase,
            confidence=payload.activation.confidence,
            provider_channel=payload.activation.provider_channel,
        )

    policy = activation_policy_from_remote_config(device.remote_config)
    return evaluate_activation(
        policy=policy,
        text=payload.text,
        channel_id=payload.channel_id,
        evidence=evidence,
    )
