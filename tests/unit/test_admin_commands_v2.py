import pytest

from terrasatch.admin.commands_v2 import run_admin_command


@pytest.mark.asyncio
async def test_admin_help_exposes_satchy_commands() -> None:
    result = await run_admin_command(None, command="help", selected_organization=None)
    text = "\n".join(result.lines)
    assert "defaults to Satchy" in text
    assert "channel create <site_uuid>" in text
    assert "edge ai <device_uuid>" in text
    assert "reply dashboard|push|tts|rf" in text
