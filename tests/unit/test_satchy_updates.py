from types import SimpleNamespace
from uuid import uuid4

import pytest

from terrasatch.satchy.agent import answer_workspace
from terrasatch.satchy.schemas import SatchyContext
from terrasatch.satchy.updates import verified_update_answer
from terrasatch.workspace.routes import _deterministic_workspace_fallback


def context(evidence=None):
    return SatchyContext(organization_id=uuid4(), site_id=uuid4(), evidence=evidence or [])


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["ollama", "deterministic"])
@pytest.mark.parametrize("message", ["No worries. Any other updates?", "Anything new?"])
async def test_empty_update_request_never_calls_model_or_reuses_assistant_history(
    monkeypatch, provider, message
):
    def no_model(*args, **kwargs):
        raise AssertionError("An evidence-only update reply must not contact a model")

    monkeypatch.setattr("terrasatch.satchy.agent.httpx.AsyncClient", no_model)
    answer, model = await answer_workspace(
        settings=SimpleNamespace(intelligence_provider=provider),
        context=context(),
        message=message,
        history=[{"role": "assistant", "content": "Wind probably caused an evacuation."}],
    )
    assert model == "satchy-verified-updates"
    assert answer.startswith("No verified updates are available in the current Workspace context.")
    assert "Activity or Map" in answer
    assert "unavailable" not in answer
    assert "evacuation" not in answer


def test_existing_evidence_is_quoted_without_claiming_it_is_new_or_executing_actions():
    source = "Wind increased from light to moderate and visibility decreased."
    ctx = context([{"id": "source-123", "summary": source}])
    before = ctx.model_dump()
    answer, model = verified_update_answer(ctx, "Thanks! Any more updates?")
    assert source in answer
    assert "cannot determine which are new" in answer
    assert "source records and timestamps" in answer
    assert "No verified updates" not in answer
    assert model == "satchy-verified-updates"
    assert ctx.model_dump() == before
    assert _deterministic_workspace_fallback(ctx, "Any updates?") == (answer, model)


@pytest.mark.parametrize(
    "message",
    ["Any updates on the weather?", "Send any new updates to Slack", "Why is visibility down?"],
)
def test_specific_questions_and_outbound_requests_keep_their_existing_paths(message):
    assert verified_update_answer(context(), message) is None


def test_missing_or_blank_summaries_do_not_become_verified_updates():
    answer, _ = verified_update_answer(
        context([{"id": "empty"}, {"id": "blank", "summary": "  "}]), "Any updates?"
    )
    assert answer.startswith("No verified updates")


def test_update_reply_is_bounded_to_three_source_summaries():
    answer, _ = verified_update_answer(
        context([{"summary": f"Record {i}"} for i in range(6)]), "Any updates?"
    )
    assert "Record 0" not in answer
    assert "Record 2" not in answer
    assert all(f"Record {i}" in answer for i in (3, 4, 5))
