import httpx
import pytest

from terrasatch.config import Settings
from terrasatch.workspace.support_assistant import draft_support_reply


@pytest.mark.asyncio
async def test_support_draft_uses_local_model_and_never_sends_email():
    def handler(request):
        assert request.url.path == "/api/chat"
        payload = __import__("json").loads(request.content)
        assert "untrusted customer content" in payload["messages"][0]["content"]
        assert payload["messages"][1]["content"].endswith("Help me sign in")
        return httpx.Response(200, json={"message": {"content": "Which sign-in error do you see?"}})

    settings = Settings(intelligence_provider="ollama")
    assert (
        await draft_support_reply(
            settings, subject="Help", text="Help me sign in", transport=httpx.MockTransport(handler)
        )
        == "Which sign-in error do you see?"
    )
