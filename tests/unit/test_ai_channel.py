from types import SimpleNamespace

from terrasatch.admin.ai_channel import ai_channel_config, ai_channel_lines


def _device(*, capabilities=None, remote_config=None):
    return SimpleNamespace(
        capabilities=capabilities or [],
        remote_config=remote_config or {},
    )


def test_satchy_ai_channel_defaults_are_logical_and_non_transmitting() -> None:
    device = _device(capabilities=["radio:receive"])

    config = ai_channel_config(device)

    assert config["name"] == "Satchy AI Channel"
    assert config["agent_name"] == "Satchy"
    assert config["activation_phrase"] == "TerraSatch"
    assert config["logical_channel_id"] is None
    assert config["reply_route"] == "dashboard"
    assert config["rf_reply_enabled"] is False
    assert config["response_mode"] == "suggest"
    assert "reply_radio" in config["allowed_action_types"]
    assert "admin" in config["authorized_approver_roles"]
    assert config["conversation_timeout_seconds"] == 300
    assert config["emergency_auto_broadcast"] is False


def test_satchy_ai_channel_preserves_remote_binding_policy() -> None:
    device = _device(
        capabilities=["radio:receive", "radio:transmit"],
        remote_config={
            "radio": {
                "ai_channel": {
                    "logical_channel_id": "11111111-1111-1111-1111-111111111111",
                    "provider_channel": "Operations 2",
                    "frequency_hz": 462575000,
                    "modulation": "nfm",
                    "reply_route": "rf",
                    "rf_reply_enabled": True,
                }
            }
        },
    )

    config = ai_channel_config(device)
    lines = "\n".join(ai_channel_lines(device))

    assert config["agent_name"] == "Satchy"
    assert config["provider_channel"] == "Operations 2"
    assert config["frequency_hz"] == 462575000
    assert config["reply_route"] == "rf"
    assert "core never autonomously transmits RF" in lines
