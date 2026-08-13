from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from terrasatch.radio.schemas import TransmissionCreateRequest


def _payload(**overrides):
    payload = {
        "site_id": uuid4(),
        "text": "Field update",
        "source": "simulator",
        "source_message_id": "message-1",
    }
    payload.update(overrides)
    return payload


def test_transmission_input_is_trimmed_before_persistence() -> None:
    request = TransmissionCreateRequest.model_validate(
        _payload(
            text="  Field update  ",
            source="  simulator  ",
            source_message_id="  message-1  ",
            callsign="  Patrol 4  ",
        )
    )

    assert request.text == "Field update"
    assert request.source == "simulator"
    assert request.source_message_id == "message-1"
    assert request.callsign == "Patrol 4"


@pytest.mark.parametrize("field", ["text", "source", "source_message_id"])
def test_required_transmission_text_fields_reject_whitespace_only(field: str) -> None:
    with pytest.raises(ValidationError):
        TransmissionCreateRequest.model_validate(_payload(**{field: "   "}))


def test_blank_optional_callsign_normalizes_to_none() -> None:
    request = TransmissionCreateRequest.model_validate(_payload(callsign="   "))

    assert request.callsign is None


def test_transmission_rejects_naive_timestamps() -> None:
    with pytest.raises(ValidationError):
        TransmissionCreateRequest.model_validate(
            _payload(started_at=datetime(2026, 8, 12, 22, 0, 0))
        )


def test_transmission_rejects_end_before_start() -> None:
    started = datetime.now(UTC)

    with pytest.raises(ValidationError):
        TransmissionCreateRequest.model_validate(
            _payload(started_at=started, ended_at=started - timedelta(seconds=1))
        )


def test_transmission_accepts_ordered_time_window() -> None:
    started = datetime.now(UTC)
    request = TransmissionCreateRequest.model_validate(
        _payload(started_at=started, ended_at=started + timedelta(seconds=1))
    )

    assert request.started_at == started
