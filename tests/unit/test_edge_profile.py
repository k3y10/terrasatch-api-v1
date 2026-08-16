import json
from uuid import uuid4

import pytest

from terrasatch.edge.profile import EdgeProfile, load_edge_profile, save_edge_profile


def test_missing_profile_defaults_to_organization_free_demo(monkeypatch, tmp_path) -> None:
    path = tmp_path / "edge.json"
    monkeypatch.setenv("TERRASATCH_EDGE_PROFILE", str(path))

    profile = load_edge_profile()

    assert profile.mode == "demo"
    assert profile.site_id is None
    assert profile.backend == "auto"
    assert profile.api_base_url == "https://api.terrasatch.com"


def test_saved_profile_never_contains_api_credentials(monkeypatch, tmp_path) -> None:
    path = tmp_path / "edge.json"
    monkeypatch.setenv("TERRASATCH_EDGE_PROFILE", str(path))
    monkeypatch.setenv("TERRASATCH_EDGE_API_KEY", "ts_secret_not_for_profile")

    save_edge_profile(EdgeProfile(mode="demo", site_id=uuid4(), backend="rtl"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload).lower()

    assert "api_key" not in serialized
    assert "secret" not in serialized
    assert "ts_secret_not_for_profile" not in serialized


def test_organization_mode_requires_site() -> None:
    with pytest.raises(ValueError, match="site_id"):
        EdgeProfile(mode="organization").validate()
