from uuid import UUID

from terrasatch.radio.schemas import TransmissionCreateRequest


SITE_ID = UUID("11111111-2222-3333-4444-555555555555")


def test_existing_transmission_payload_stays_valid_without_activation_metadata() -> None:
    payload = TransmissionCreateRequest(
        site_id=SITE_ID,
        text="Routine field observation",
        source="terrasatch-edge-stt",
        source_message_id="legacy-edge-payload",
        transcript_provider="faster_whisper",
        transcript_model="base.en",
    )

    assert payload.activation is None
    assert payload.text == "Routine field observation"
    assert payload.source == "terrasatch-edge-stt"


def test_activation_metadata_is_optional_and_normalized_when_present() -> None:
    payload = TransmissionCreateRequest(
        site_id=SITE_ID,
        text="Field Team to TerraSatch. Wind loading observed.",
        source_message_id="activation-edge-payload",
        activation={
            "detected": True,
            "phrase": "  Field Team to TerraSatch  ",
            "confidence": 0.93,
            "provider_channel": "  Operations 5  ",
        },
    )

    assert payload.activation is not None
    assert payload.activation.detected is True
    assert payload.activation.phrase == "Field Team to TerraSatch"
    assert payload.activation.provider_channel == "Operations 5"
    assert payload.activation.confidence == 0.93
