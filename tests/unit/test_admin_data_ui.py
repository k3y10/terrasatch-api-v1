from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from terrasatch.admin.data_ui import render_data_inspector, render_data_sources
from terrasatch.masterdata.service import InspectorResult


def test_data_source_screen_explains_queued_isolation_and_secret_references() -> None:
    organization_id = uuid4()
    source_id = uuid4()
    organization = SimpleNamespace(id=organization_id, name="UAC")
    source = SimpleNamespace(
        id=source_id,
        name="Utah Avalanche Center",
        provider="uac",
        source_kind="avalanche_observations",
        adapter_key="manual_snapshot",
        adapter_version="1",
        status="ready",
        last_successful_sync=None,
        enabled=True,
    )

    html = render_data_sources(
        organizations=[organization],
        selected_organization=str(organization_id),
        selected_name="UAC",
        sources=[source],
        record_counts={source_id: 0},
        sync_runs=[],
        backups=[],
        csrf_token="csrf",
        error_message=None,
    )

    assert "/admin/data-sources" in html
    assert "/admin/data-inspector" in html
    assert "Provider syncs are queued only" in html
    assert "never a raw token" in html
    assert "Queue sync" in html
    assert "Backup execution remains outside the browser" in html


def test_data_inspector_renders_provenance_and_unresolved_spatial_state() -> None:
    organization_id = uuid4()
    organization = SimpleNamespace(id=organization_id, name="UAC")
    result = InspectorResult(
        record_type="operational_event",
        record_id=uuid4(),
        title="Shooting cracks observed",
        subtitle="avalanche_observation · Patrol 4",
        provenance="Edge → faster-whisper → TerraEngine",
        spatial="unresolved · Cardiff Bowl",
        details={"timestamp": datetime.now(UTC).isoformat()},
    )

    html = render_data_inspector(
        organizations=[organization],
        selected_organization=str(organization_id),
        selected_name="UAC",
        query="Cardiff Bowl",
        results=[result],
        error_message=None,
    )

    assert "Shooting cracks observed" in html
    assert "Edge → faster-whisper → TerraEngine" in html
    assert "unresolved · Cardiff Bowl" in html
    assert "TS-UT-SLC-004813" in html
