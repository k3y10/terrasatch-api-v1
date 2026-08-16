from typer.testing import CliRunner

from terrasatch.cli.entrypoint import app


def test_edge_help_exposes_simple_demo_workflow() -> None:
    result = CliRunner().invoke(app, ["edge", "--help"])

    assert result.exit_code == 0
    expected_commands = (
        "setup",
        "status",
        "detect",
        "capture",
        "demo",
        "demo-submit",
        "rtl",
        "audio",
        "api",
    )
    for command in expected_commands:
        assert command in result.stdout


def test_demo_setup_requires_no_organization(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TERRASATCH_EDGE_PROFILE", str(tmp_path / "edge.json"))

    help_result = CliRunner().invoke(app, ["edge", "setup", "--help"])
    result = CliRunner().invoke(app, ["edge", "setup"])

    assert help_result.exit_code == 0
    assert "--organization" not in help_result.stdout
    assert result.exit_code == 0
    assert "mode: demo" in result.stdout
    assert "site_id: not configured" in result.stdout


def test_capture_and_demo_help_have_no_organization_selector() -> None:
    capture = CliRunner().invoke(app, ["edge", "capture", "--help"])
    demo = CliRunner().invoke(app, ["edge", "demo", "--help"])

    assert capture.exit_code == 0
    assert demo.exit_code == 0
    assert "--frequency-hz" in capture.stdout
    assert "--frequency-hz" in demo.stdout
    assert "--organization" not in capture.stdout
    assert "--organization" not in demo.stdout
    assert "automatic STT" in demo.stdout
