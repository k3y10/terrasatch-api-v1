from uuid import UUID

import pytest

from terrasatch.errors import InvalidConfiguration
from terrasatch.radio.activation import (
    ActivationEvidence,
    ActivationPolicy,
    activation_policy_from_remote_config,
    evaluate_activation,
)

CHANNEL_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_CHANNEL_ID = UUID("22222222-2222-2222-2222-222222222222")


def test_legacy_ingest_remains_accepted_when_activation_is_not_required() -> None:
    decision = evaluate_activation(
        policy=ActivationPolicy(required=False, phrase="Example Ops to TerraSatch"),
        text="Routine field traffic without an activation phrase",
        channel_id=None,
    )

    assert decision.accepted is True
    assert decision.enforced is False
    assert decision.intelligence_text == "Routine field traffic without an activation phrase"


def test_required_activation_accepts_configured_phrase_and_strips_only_processing_copy() -> None:
    decision = evaluate_activation(
        policy=ActivationPolicy(
            required=True,
            phrase="Example Ops to TerraSatch",
            logical_channel_id=CHANNEL_ID,
        ),
        text="Example Ops to TerraSatch. Wind loading observed on the north ridge.",
        channel_id=CHANNEL_ID,
        evidence=ActivationEvidence(
            detected=True,
            phrase="Example Ops to TerraSatch",
            confidence=0.96,
        ),
    )

    assert decision.accepted is True
    assert decision.enforced is True
    assert decision.intelligence_text == "Wind loading observed on the north ridge."


def test_required_activation_rejects_phrase_mentioned_later() -> None:
    with pytest.raises(InvalidConfiguration, match="did not begin"):
        evaluate_activation(
            policy=ActivationPolicy(required=True, phrase="Example Ops to TerraSatch"),
            text="Wind loading observed. Example Ops to TerraSatch please log that.",
            channel_id=None,
        )


def test_required_activation_rejects_different_organization_phrase() -> None:
    with pytest.raises(InvalidConfiguration, match="did not begin"):
        evaluate_activation(
            policy=ActivationPolicy(required=True, phrase="Example Ops to TerraSatch"),
            text="Other Team to TerraSatch. Wind loading observed.",
            channel_id=None,
        )


def test_required_activation_rejects_wrong_logical_channel() -> None:
    with pytest.raises(InvalidConfiguration, match="channel does not match"):
        evaluate_activation(
            policy=ActivationPolicy(
                required=True,
                phrase="Example Ops to TerraSatch",
                logical_channel_id=CHANNEL_ID,
            ),
            text="Example Ops to TerraSatch. Wind loading observed.",
            channel_id=OTHER_CHANNEL_ID,
        )


def test_provider_channel_evidence_cannot_override_configured_policy() -> None:
    with pytest.raises(InvalidConfiguration, match="Provider channel"):
        evaluate_activation(
            policy=ActivationPolicy(
                required=True,
                phrase="Example Ops to TerraSatch",
                provider_channel="Operations 5 / Code 10",
            ),
            text="Example Ops to TerraSatch. Wind loading observed.",
            channel_id=None,
            evidence=ActivationEvidence(
                detected=True,
                provider_channel="Operations 2",
            ),
        )


def test_remote_config_parser_is_generic_and_defaults_enforcement_off() -> None:
    default_policy = activation_policy_from_remote_config({})
    assert default_policy.required is False
    assert default_policy.phrase == "TerraSatch"
    assert default_policy.position == "start"

    configured = activation_policy_from_remote_config(
        {
            "radio": {
                "ai_channel": {
                    "activation_required": True,
                    "activation_phrase": "Field Command to TerraSatch",
                    "activation_position": "start",
                    "logical_channel_id": str(CHANNEL_ID),
                    "provider_channel": "Command",
                }
            }
        }
    )
    assert configured.required is True
    assert configured.phrase == "Field Command to TerraSatch"
    assert configured.logical_channel_id == CHANNEL_ID
    assert configured.provider_channel == "Command"


def test_required_activation_rejects_empty_observation_after_phrase() -> None:
    with pytest.raises(InvalidConfiguration, match="did not contain an observation"):
        evaluate_activation(
            policy=ActivationPolicy(required=True, phrase="Field Command to TerraSatch"),
            text="Field Command to TerraSatch.",
            channel_id=None,
        )
