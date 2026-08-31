"""Generic Edge activation-policy evaluation for TerraSatch radio ingestion.

This module intentionally contains no partner-specific names. Organizations, sites,
logical channels, and paired Edge credentials remain the routing boundary; an
activation phrase is only an opt-in processing gate inside that boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from terrasatch.errors import InvalidConfiguration


@dataclass(frozen=True, slots=True)
class ActivationPolicy:
    required: bool = False
    phrase: str = "TerraSatch"
    position: str = "start"
    case_sensitive: bool = False
    logical_channel_id: UUID | None = None
    provider_channel: str | None = None


@dataclass(frozen=True, slots=True)
class ActivationEvidence:
    detected: bool | None = None
    phrase: str | None = None
    confidence: float | None = None
    provider_channel: str | None = None


@dataclass(frozen=True, slots=True)
class ActivationDecision:
    enforced: bool
    accepted: bool
    intelligence_text: str


def _clean_optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def activation_policy_from_remote_config(
    remote_config: dict[str, object] | None,
) -> ActivationPolicy:
    """Build a generic activation policy from the existing Edge remote-config contract."""

    config = dict(remote_config or {})
    raw_radio = config.get("radio")
    radio = dict(raw_radio) if isinstance(raw_radio, dict) else {}
    raw_ai = radio.get("ai_channel")
    ai = dict(raw_ai) if isinstance(raw_ai, dict) else {}

    phrase = _clean_optional_text(ai.get("activation_phrase")) or "TerraSatch"
    position = (_clean_optional_text(ai.get("activation_position")) or "start").lower()
    if position != "start":
        raise InvalidConfiguration("activation_position must currently be 'start'")

    logical_channel_id: UUID | None = None
    raw_channel_id = _clean_optional_text(ai.get("logical_channel_id"))
    if raw_channel_id is not None:
        try:
            logical_channel_id = UUID(raw_channel_id)
        except ValueError as exc:
            raise InvalidConfiguration("Configured logical_channel_id must be a UUID") from exc

    return ActivationPolicy(
        required=bool(ai.get("activation_required", False)),
        phrase=phrase,
        position=position,
        case_sensitive=bool(ai.get("activation_case_sensitive", False)),
        logical_channel_id=logical_channel_id,
        provider_channel=_clean_optional_text(ai.get("provider_channel")),
    )


def _starts_with_phrase(text: str, phrase: str, *, case_sensitive: bool) -> bool:
    candidate = text if case_sensitive else text.casefold()
    expected = phrase if case_sensitive else phrase.casefold()
    if not candidate.startswith(expected):
        return False
    if len(text) == len(phrase):
        return True
    # Do not accept prefixes such as "TerraSatcher" for a "TerraSatch" policy.
    return not text[len(phrase)].isalnum()


def strip_activation_prefix(text: str, phrase: str) -> str:
    """Remove one already-validated activation phrase while preserving source text elsewhere."""

    remainder = text[len(phrase) :].lstrip()
    remainder = remainder.lstrip(".,:;-—– ")
    return " ".join(remainder.split())


def evaluate_activation(
    *,
    policy: ActivationPolicy,
    text: str,
    channel_id: UUID | None,
    evidence: ActivationEvidence | None = None,
) -> ActivationDecision:
    """Evaluate an opt-in activation gate without determining tenant identity.

    When ``policy.required`` is false, legacy ingestion behavior is preserved. When it
    is true, the API independently checks the configured phrase and logical channel;
    device-supplied evidence is treated only as consistency metadata.
    """

    normalized_text = " ".join(text.strip().split())
    if not policy.required:
        return ActivationDecision(
            enforced=False,
            accepted=True,
            intelligence_text=normalized_text,
        )

    phrase = policy.phrase.strip()
    if not phrase:
        raise InvalidConfiguration("Activation enforcement is enabled without a phrase")

    if policy.logical_channel_id is not None and channel_id != policy.logical_channel_id:
        raise InvalidConfiguration(
            "Transmission channel does not match the Edge activation policy"
        )

    if evidence is not None:
        if evidence.detected is False:
            raise InvalidConfiguration("Edge reported that the activation phrase was not detected")
        if evidence.phrase is not None:
            supplied = evidence.phrase.strip()
            if supplied.casefold() != phrase.casefold():
                raise InvalidConfiguration(
                    "Activation evidence does not match the configured phrase"
                )
        if (
            policy.provider_channel is not None
            and evidence.provider_channel is not None
            and evidence.provider_channel.strip().casefold()
            != policy.provider_channel.strip().casefold()
        ):
            raise InvalidConfiguration(
                "Provider channel does not match the Edge activation policy"
            )

    if not _starts_with_phrase(normalized_text, phrase, case_sensitive=policy.case_sensitive):
        raise InvalidConfiguration(
            "Transmission did not begin with the configured activation phrase"
        )

    intelligence_text = strip_activation_prefix(normalized_text, phrase)
    if not intelligence_text:
        raise InvalidConfiguration("Activated transmission did not contain an observation")

    return ActivationDecision(
        enforced=True,
        accepted=True,
        intelligence_text=intelligence_text,
    )
