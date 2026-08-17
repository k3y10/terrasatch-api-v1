from types import SimpleNamespace

from terrasatch.admin.commands import (
    device_supports_receive,
    device_supports_transmit,
    radio_mode,
)


def _device(*, capabilities=None, inventory=None, remote_config=None):
    return SimpleNamespace(
        capabilities=capabilities or [],
        hardware_inventory=inventory or [],
        remote_config=remote_config or {},
    )


def test_nooelec_inventory_is_receive_only() -> None:
    device = _device(
        inventory=[{"provider": "rtl", "name": "Nooelec NESDR SMArt v5"}],
    )

    assert device_supports_receive(device)
    assert not device_supports_transmit(device)
    assert radio_mode(device) == "RX"


def test_tx_mode_requires_reported_transmit_capability_and_policy() -> None:
    device = _device(
        capabilities=["radio:receive", "radio:transmit"],
        remote_config={
            "radio": {
                "receive_enabled": True,
                "transmit_enabled": True,
            }
        },
    )

    assert device_supports_receive(device)
    assert device_supports_transmit(device)
    assert radio_mode(device) == "RX+TX"


def test_tx_capability_defaults_to_disabled() -> None:
    device = _device(capabilities=["radio:receive", "radio:transmit"])

    assert radio_mode(device) == "RX"
