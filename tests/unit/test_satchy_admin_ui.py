from types import SimpleNamespace
from uuid import uuid4

from terrasatch.admin.satchy_ui import render_satchy_control_plane


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
    assert "Simulated ✓" in html
