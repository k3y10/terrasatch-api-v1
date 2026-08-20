"""PII-minimized server-side adapter for flaikConnect operational context.

The adapter intentionally keeps flaik credentials and raw provider payloads behind the
TerraSatch API trust boundary. Public/application responses expose only normalized operational
counts and pseudonymous group/instructor references suitable for field coordination.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import httpx
from pydantic import BaseModel, Field

from terrasatch.config import Settings


class FlaikMode(StrEnum):
    DISABLED = "disabled"
    FIXTURE = "fixture"
    LIVE = "live"


class FlaikGroup(BaseModel):
    group_id: str
    label: str
    instructor_ref: str | None = None
    participant_count: int = Field(default=0, ge=0)
    status: str = "scheduled"
    meeting_area: str | None = None
    start_time: str | None = None
    end_time: str | None = None


class FlaikOperationalSnapshot(BaseModel):
    provider: str = "flaik"
    mode: FlaikMode
    connected: bool
    source_site: str = "snowbird.flaik.com"
    resort_name: str = "Snowbird"
    synced_at: datetime
    groups_out: int = Field(default=0, ge=0)
    instructors_active: int = Field(default=0, ge=0)
    attention_count: int = Field(default=0, ge=0)
    groups: list[FlaikGroup] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    note: str | None = None


class FlaikRadioContext(BaseModel):
    provider: str = "flaik"
    connected: bool
    group_id: str | None = None
    group_label: str | None = None
    instructor_ref: str | None = None
    participant_count: int | None = Field(default=None, ge=0)
    status: str | None = None
    meeting_area: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)


def _fixture_snapshot() -> FlaikOperationalSnapshot:
    groups = [
        FlaikGroup(
            group_id="MS-101",
            label="Mountain School 1",
            instructor_ref="Instructor 01",
            participant_count=6,
            status="checked_in",
            meeting_area="Snowbird Center",
            start_time="09:00",
            end_time="12:00",
        ),
        FlaikGroup(
            group_id="MS-204",
            label="Mountain School 4",
            instructor_ref="Instructor 04",
            participant_count=5,
            status="on_mountain",
            meeting_area="Creekside",
            start_time="09:30",
            end_time="15:30",
        ),
        FlaikGroup(
            group_id="MS-307",
            label="Mountain School 7",
            instructor_ref="Instructor 07",
            participant_count=4,
            status="attention",
            meeting_area="Chickadee",
            start_time="10:00",
            end_time="13:00",
        ),
    ]
    return FlaikOperationalSnapshot(
        mode=FlaikMode.FIXTURE,
        connected=True,
        synced_at=datetime.now(UTC),
        groups_out=8,
        instructors_active=12,
        attention_count=1,
        groups=groups,
        capabilities=["resort_settings", "class_management", "timekeeping", "employees"],
        note="Demo fixture uses pseudonymous operational records; no employee PII is exposed.",
    )


def _first(payload: dict[str, Any], *keys: str) -> Any:
    lowered = {str(key).casefold(): value for key, value in payload.items()}
    for key in keys:
        value = lowered.get(key.casefold())
        if value not in (None, ""):
            return value
    return None


def _items(payload: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = _first(payload, key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _items(value, "items", "results", "data")
            if nested:
                return nested
    return []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return default


def _normalize_groups(payload: Any) -> list[FlaikGroup]:
    normalized: list[FlaikGroup] = []
    for index, item in enumerate(_items(payload, "classes", "items", "results", "data"), start=1):
        provider_id = _first(item, "id", "classId", "class_id", "identifier")
        group_id = str(provider_id) if provider_id is not None else f"class-{index}"
        label = _first(item, "name", "className", "class_name", "label") or f"Class {index}"
        participant_count = _safe_int(
            _first(item, "guestCount", "guest_count", "participantCount", "participant_count")
        )
        status = str(_first(item, "status", "classStatus", "state") or "scheduled")
        meeting_area = _first(item, "meetingArea", "meeting_area", "locationName", "location")
        start_time = _first(item, "startTime", "start_time", "startDateTime")
        end_time = _first(item, "endTime", "end_time", "endDateTime")
        instructor_id = _first(item, "instructorId", "instructor_id", "employeeId", "staffId")
        # Never expose provider employee IDs, names, emails, payroll IDs, phone numbers,
        # or raw employee payloads. A simple assignment state is enough for field context.
        instructor_ref = "Instructor assigned" if instructor_id is not None else None
        normalized.append(
            FlaikGroup(
                group_id=group_id,
                label=str(label)[:120],
                instructor_ref=instructor_ref,
                participant_count=participant_count,
                status=status[:40],
                meeting_area=str(meeting_area)[:120] if meeting_area is not None else None,
                start_time=str(start_time)[:40] if start_time is not None else None,
                end_time=str(end_time)[:40] if end_time is not None else None,
            )
        )
    return normalized


def _timekeeping_counts(payload: Any) -> tuple[int, int]:
    records = _items(payload, "paidActivities", "paid_activities", "timekeeping", "items", "results", "data")
    active = 0
    attention = 0
    for item in records:
        end_value = _first(item, "endTime", "end_time", "punchOut", "punch_out")
        status = str(_first(item, "status", "approvalStatus", "approval_status") or "").casefold()
        if end_value in (None, ""):
            active += 1
        if any(term in status for term in ("dispute", "attention", "error", "rejected")):
            attention += 1
    return active, attention


class FlaikClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mode = FlaikMode(settings.flaik_mode)

    def _require_live_config(self) -> tuple[str, str, str, str]:
        if self.settings.flaik_auth_url is None or self.settings.flaik_api_base_url is None:
            raise RuntimeError("flaik live mode requires auth and API base URLs")
        if not self.settings.flaik_client_id or self.settings.flaik_client_secret is None:
            raise RuntimeError("flaik live mode requires client credentials")
        return (
            str(self.settings.flaik_auth_url).rstrip("/"),
            str(self.settings.flaik_api_base_url).rstrip("/"),
            self.settings.flaik_client_id,
            self.settings.flaik_client_secret.get_secret_value(),
        )

    async def _token(self, client: httpx.AsyncClient) -> str:
        auth_url, _api_url, client_id, client_secret = self._require_live_config()
        response = await client.post(
            auth_url,
            auth=httpx.BasicAuth(client_id, client_secret),
            data={
                "grant_type": "client_credentials",
                "scope": self.settings.flaik_scope,
            },
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise RuntimeError("flaik authentication response did not include an access token")
        return token

    async def _get(self, client: httpx.AsyncClient, token: str, path: str) -> Any:
        _auth_url, api_url, _client_id, _client_secret = self._require_live_config()
        response = await client.get(
            f"{api_url}/{path.lstrip('/')}",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    async def snapshot(self) -> FlaikOperationalSnapshot:
        if self.mode == FlaikMode.DISABLED:
            return FlaikOperationalSnapshot(
                mode=self.mode,
                connected=False,
                synced_at=datetime.now(UTC),
                capabilities=[],
                note="flaik integration is disabled.",
            )
        if self.mode == FlaikMode.FIXTURE:
            return _fixture_snapshot()

        timeout = httpx.Timeout(self.settings.flaik_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            token = await self._token(client)
            await self._get(client, token, "/health")
            resort = await self._get(client, token, "/api/globalsettings/resort")
            class_payload: Any = []
            timekeeping_payload: Any = []
            capabilities = ["resort_settings"]
            if self.settings.flaik_classes_path:
                class_payload = await self._get(client, token, self.settings.flaik_classes_path)
                capabilities.append("class_management")
            if self.settings.flaik_timekeeping_path:
                timekeeping_payload = await self._get(
                    client, token, self.settings.flaik_timekeeping_path
                )
                capabilities.append("timekeeping")

        groups = _normalize_groups(class_payload)
        active_from_timekeeping, attention_from_timekeeping = _timekeeping_counts(timekeeping_payload)
        resort_name = "Snowbird"
        if isinstance(resort, dict):
            resort_name = str(_first(resort, "name", "resortName", "resort_name") or resort_name)
        groups_out = sum(
            1 for group in groups if group.status.casefold() not in {"scheduled", "complete", "completed"}
        )
        attention = sum(1 for group in groups if "attention" in group.status.casefold())
        note = None
        if not self.settings.flaik_classes_path or not self.settings.flaik_timekeeping_path:
            note = (
                "Live flaik health/resort access is configured. Class/timekeeping endpoint paths "
                "must be supplied from the Snowbird flaik environment before those modules are read."
            )
        return FlaikOperationalSnapshot(
            mode=self.mode,
            connected=True,
            resort_name=resort_name[:120],
            synced_at=datetime.now(UTC),
            groups_out=groups_out,
            instructors_active=max(active_from_timekeeping, groups_out),
            attention_count=attention + attention_from_timekeeping,
            groups=groups,
            capabilities=capabilities,
            note=note,
        )


def correlate_radio_text(text: str, snapshot: FlaikOperationalSnapshot) -> FlaikRadioContext:
    if not snapshot.connected:
        return FlaikRadioContext(connected=False)
    lowered = " ".join(text.casefold().split())
    best: FlaikGroup | None = None
    confidence = 0.0
    for group in snapshot.groups:
        label = group.label.casefold()
        group_id = group.group_id.casefold()
        score = 0.0
        if label and label in lowered:
            score = 0.95
        elif group_id and group_id in lowered:
            score = 0.98
        else:
            label_parts = [part for part in label.split() if len(part) > 2]
            matches = sum(1 for part in label_parts if part in lowered)
            if label_parts and matches:
                score = min(0.55 + matches * 0.1, 0.85)
        if score > confidence:
            best = group
            confidence = score
    if best is None:
        return FlaikRadioContext(connected=True)
    return FlaikRadioContext(
        connected=True,
        group_id=best.group_id,
        group_label=best.label,
        instructor_ref=best.instructor_ref,
        participant_count=best.participant_count,
        status=best.status,
        meeting_area=best.meeting_area,
        confidence=confidence,
    )


async def build_flaik_radio_context(settings: Settings, text: str) -> FlaikRadioContext | None:
    if not settings.flaik_enrich_transmissions or settings.flaik_mode == FlaikMode.DISABLED.value:
        return None
    try:
        snapshot = await FlaikClient(settings).snapshot()
        return correlate_radio_text(text, snapshot)
    except (httpx.HTTPError, RuntimeError, ValueError):
        # Partner-system availability must never prevent TerraSatch radio ingestion.
        return FlaikRadioContext(connected=False)
