import pytest
from pydantic import ValidationError

from terrasatch.radio.schemas import RfMetadata


def test_optional_repeater_provenance_and_legacy_metadata():
    assert RfMetadata(channel=19, frequency_hz=462650000).repeater is None
    metadata = RfMetadata(target_id="cottonwood-650", modulation="nfm", source_type="repeater",
                          repeater={"provider": "manual", "output_frequency_hz": 462650000,
                                    "input_frequency_hz": 467650000})
    assert metadata.repeater.output_frequency_hz == 462650000
    assert metadata.signal_dbfs is None and metadata.snr_db is None


@pytest.mark.parametrize("repeater", [{"output_frequency_hz": -1}, {"provider": "x" * 65},
                                       {"organization_id": "evil"}, {"transmit_authorized": True}])
def test_invalid_repeater_provenance_is_rejected(repeater):
    with pytest.raises(ValidationError):
        RfMetadata(repeater=repeater)
