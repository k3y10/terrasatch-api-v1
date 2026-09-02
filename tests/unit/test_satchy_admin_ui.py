import re
from html import escape
from types import SimpleNamespace
from uuid import uuid4

import pytest

from terrasatch.admin.satchy_ui import render_satchy_control_plane
from terrasatch.admin.ui import _styles as admin_styles


def test_satchy_admin_ui_shows_review_and_simulated_lifecycle() -> None:
    organization_id = uuid4()
    action_id = uuid4()
    html = render_satchy_control_plane(
        organizations=[SimpleNamespace(id=organization_id, name="UAC")],
        selected_organization=str(organization_id),
        selected_name="UAC",
        workflows=[
            {
                "action": SimpleNamespace(
                    id=action_id,
                    action_type="reply_radio",
                    status="awaiting_approval",
                    proposed_message="Control 2, Satchy. Go ahead.",
                ),
                "evaluation": SimpleNamespace(
                    confidence=0.94,
                    interpretation="Control 2 is calling Satchy",
                ),
                "transmission": SimpleNamespace(source_type="terrasatch-edge-stt"),
                "transcript": SimpleNamespace(raw_text="Satchy, Control 2."),
                "conversation": SimpleNamespace(
                    participants=["Control 2", "Satchy"],
                    primary_topic="operational radio",
                ),
                "outbound": None,
                "command": None,
            }
        ],
        csrf_token="csrf-token",
    )

    assert "Satchy, Control 2." in html
    assert "Control 2 ↔ Satchy" in html
    assert "Control 2, Satchy. Go ahead." in html
    assert "94%" in html
    assert f"/admin/satchy/actions/{action_id}/approve" in html
    assert "Approve" in html
    assert "Reject" in html
    assert "Queued" in html
    assert "Edge received" in html
    assert "Simulated" in html
    assert "Simulated ✓" not in html
    assert html.count('<li class="pending">') == 3
    assert admin_styles() in html
    assert '<body class="satchy-page"><div class="admin-shell">' in html
    assert 'aria-current="page"' in html
    assert f'/admin?organization={organization_id}#sites' in html
    assert '<label for="satchy-organization">Organization</label>' in html
    assert '<select id="satchy-organization" name="organization">' in html
    assert 'name="csrf_token" value="csrf-token"' in html
    assert f'name="organization" value="{organization_id}"' in html
    assert "SIMULATION ONLY" in html
    assert "unless explicit RF policy" not in html


def _render_state(
    action_status: str = "awaiting_approval",
    outbound_status: str | None = None,
    text: str = "Satchy, Control 2.",
) -> str:
    return render_satchy_control_plane(
        organizations=[SimpleNamespace(id="org-1", name="Snowbird")],
        selected_organization="org-1",
        selected_name="Snowbird",
        workflows=[{
            "action": SimpleNamespace(
                id="action-1",
                action_type="reply_radio",
                status=action_status,
                proposed_message=text,
            ),
            "transcript": SimpleNamespace(raw_text=text),
            "conversation": SimpleNamespace(participants=[text, "Satchy"], primary_topic=text),
            "evaluation": SimpleNamespace(confidence=0.88, interpretation=text),
            "outbound": SimpleNamespace(status=outbound_status) if outbound_status else None,
            "command": SimpleNamespace(id="command-1") if outbound_status else None,
        }],
        csrf_token="csrf-test",
    )


@pytest.mark.parametrize(
    ("outbound_status", "done_count"),
    [(None, 0), ("queued", 1), ("dispatched", 1), ("edge_received", 2),
     ("waiting_channel_clear", 2), ("simulated", 3), ("transmitting", 2),
     ("transmitted", 2), ("failed", 0), ("expired", 0), ("cancelled", 0)],
)
def test_lifecycle_only_marks_confirmed_simulation_complete(
    outbound_status: str | None, done_count: int,
) -> None:
    html = _render_state(outbound_status=outbound_status)
    assert html.count('<li class="done">') == done_count
    assert html.count('<li class="pending">') == 3 - done_count
    assert ("Simulated ✓" in html) is (outbound_status == "simulated")


@pytest.mark.parametrize(
    "action_status",
    ["queued", "executing", "completed", "rejected", "expired", "failed", "cancelled"],
)
def test_review_buttons_are_not_rendered_after_review(action_status: str) -> None:
    html = _render_state(action_status=action_status)
    assert '/actions/action-1/approve' not in html
    assert '/actions/action-1/reject' not in html
    assert 'name="message"' not in html
    assert action_status.title() in html


def test_review_form_contract_and_untrusted_content_are_preserved() -> None:
    text = '</textarea><script>alert("test")</script> & radio'
    html = _render_state(text=text)
    assert text not in html
    assert escape(text) in html
    assert '<script>' not in html
    assert re.search(r'<textarea name="message" rows="3">' + re.escape(escape(text)), html)
    assert 'method="post" action="/admin/satchy/actions/action-1/approve"' in html
    assert 'method="post" action="/admin/satchy/actions/action-1/reject"' in html
    assert html.count('name="csrf_token" value="csrf-test"') == 3  # includes logout
    assert html.count('name="organization" value="org-1"') == 2


@pytest.mark.parametrize("selected", ["", "org-1"])
def test_empty_and_error_states_use_the_same_admin_theme(selected: str) -> None:
    html = render_satchy_control_plane(
        organizations=[], selected_organization=selected, selected_name="<Organization>",
        workflows=[], csrf_token="csrf", error_message="<Invalid review>",
    )
    assert admin_styles() in html
    assert 'class="console-section satchy-empty"' in html
    assert 'class="terminal-alert error" role="alert">&lt;Invalid review&gt;' in html
    assert "&lt;Organization&gt;" in html
    assert ("No Satchy proposals yet" in html) is bool(selected)
    if not selected:
        assert "Choose an organization above" in html


def test_emergency_review_still_has_no_invented_reply() -> None:
    html = render_satchy_control_plane(
        organizations=[], selected_organization="org-1", selected_name="Snowbird",
        workflows=[{"action": SimpleNamespace(
            id="emergency-1", action_type="emergency_review", status="awaiting_approval",
            proposed_message=None,
        )}], csrf_token="csrf",
    )
    assert "Human emergency review required" in html
    assert "Emergency Review" in html
    assert "Simulated ✓" not in html
