from uuid import uuid4

import pytest
from pydantic import ValidationError

from terrasatch.radio.schemas import TransmissionCreateRequest


def test_transmission_accepts_stt_provenance_without_breaking_text_contract() -> None:
    payload = TransmissionCreateRequest(
        site_id=uuid4(),
        text=" Shooting cracks below Cardiff Bowl. ",
        source="terrasatch-edge-stt",
        source_message_id="edge-radio-1",
        transcript_provider=" faster_whisper ",
        transcript_model=" base.en ",
        transcript_language=" en ",
        transcript_confidence=0.93,
    )
    assert payload.text == "Shooting cracks below Cardiff Bowl."
    assert payload.transcript_provider == "faster_whisper"
    assert payload.transcript_model == "base.en"
    assert payload.transcript_language == "en"
    assert payload.transcript_confidence == pytest.approx(0.93)


def test_transcript_confidence_is_bounded() -> None:
    with pytest.raises(ValidationError):
        TransmissionCreateRequest(
            site_id=uuid4(),
            text="test",
            source_message_id="id-1",
            transcript_confidence=1.2,
        )
