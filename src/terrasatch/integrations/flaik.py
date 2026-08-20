"""PII-minimized flaikConnect adapter using tenant/site-scoped source configuration."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field

from terrasatch.errors import InvalidConfiguration
from terrasatch.masterdata.partner_sources import PartnerSourceContext, resolve_environment_secret


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
    source_id: str
    site_id: str | None = None
    mode: str
    connected: bool
    resort_name: str
    synced_at: datetime
    groups_out: int = Field(default=0, ge=0)
    instructors_active: int = Field(default=0, ge=0)
    attention_count: int = Field(default=0, ge=0)
    groups: list[FlaikGroup] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    note: str | None = None


class FlaikRadioContext(BaseModel):
    provider: str = "flaik"
    source_id: str
    connected: bool
    group_id: str | None = None
    group_label: str | None = None
    instructor_ref: str | None = None
    participant_count: int | None = Field(default=None, ge=0)
    status: str | None = None
    meeting_area: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)


def _string(configuration: dict[str, object], key: str, default: str = "") -> str:
    value = configuration.get(key)
    return str(value).strip() if value is not None else default


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


def _fixture_groups() -> list[FlaikGroup]:
    return [
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
    ]


def _normalize_groups(payload: Any) -> list[FlaikGroup]:
    groups: list[FlaikGroup] = []
    for index, item in enumerate(
        _items(payload, "classes", "items", "results", "data"), start=1
    ):
        provider_id = _first(item, "id", "classId", "class_id", "identifier")
        label = _first(item, "name", "className", "class_name", "label") or f"Class {index}"
        instructor_id = _first(item, "instructorId", "instructor_id", "employeeId", "staffId")
        meeting_area = _first(item, "meetingArea", "meeting_area", "locationName", "location")
        groups.append(
            FlaikGroup(
                group_id=str(provider_id) if provider_id is not None else f"class-{index}",
                label=str(label)[:120],
                instructor_ref="Instructor assigned" if instructor_id is not None else None,
                participant_count=_safe_int(
                    _first(
                        item,
                        "guestCount",
                        "guest_count",
                        "participantCount",
                        "participant_count",
                    )
                ),
                status=str(_first(item, "status", "classStatus", "state") or "scheduled")[:40],
                meeting_area=str(meeting_area)[:120] if meeting_area is not None else None,
                start_time=str(
                    _first(item, "startTime", "start_time", "startDateTime") or ""
                )[:40]
                or None,
                end_time=str(_first(item, "endTime", "end_time", "endDateTime") or "")[:40]
                or None,
            )
        )
    return groups


class FlaikClient:
    def __init__(self, source: PartnerSourceContext) -> None:
        self.source = source
        self.configuration = source.configuration
        self.mode = _string(self.configuration, "mode", "disabled").casefold()
        if self.mode not in {"disabled", "fixture", "live"}:
            raise InvalidConfiguration("flaik source mode must be disabled, fixture, or live")

    def _snapshot(
        self,
        *,
        connected: bool,
        groups: list[FlaikGroup],
        capabilities: list[str],
        note: str | None = None,
    ) -> FlaikOperationalSnapshot:
        groups_out = sum(
            1
            for group in groups
            if group.status.casefold() not in {"scheduled", "complete", "completed"}
        )
        return FlaikOperationalSnapshot(
            source_id=str(self.source.source_id),
            site_id=str(self.source.site_id) if self.source.site_id else None,
            mode=self.mode,
            connected=connected,
            resort_name=_string(self.configuration, "resort_name", "Snowbird") or "Snowbird",
            synced_at=datetime.now(UTC),
            groups_out=groups_out,
            instructors_active=sum(1 for group in groups if group.instructor_ref),
            attention_count=sum(1 for group in groups if "attention" in group.status.casefold()),
            groups=groups,
            capabilities=capabilities,
            note=note,
        )

    async def snapshot(self) -> FlaikOperationalSnapshot:
        if self.mode == "disabled":
            return self._snapshot(
                connected=False,
                groups=[],
                capabilities=[],
                note="flaik source is disabled.",
            )
        if self.mode == "fixture":
            return self._snapshot(
                connected=True,
                groups=_fixture_groups(),
                capabilities=["class_management", "timekeeping"],
                note="Explicit preview fixture; no employee PII is exposed.",
            )

        if not self.source.endpoint_url:
            raise InvalidConfiguration("Live flaik source requires a source connection endpoint")
        auth_url = _string(self.configuration, "auth_url")
        client_id = _string(self.configuration, "client_id")
        if not auth_url or not client_id:
            raise InvalidConfiguration("Live flaik source requires auth_url and client_id")
        client_secret = resolve_environment_secret(self.source.credential_reference)
        if client_secret is None:
            raise InvalidConfiguration("Live flaik source requires a credential reference")

        scope = _string(self.configuration, "scope", "flaik.connect.api.read")
        timeout_seconds = float(self.configuration.get("timeout_seconds", 8.0))
        classes_path = _string(self.configuration, "classes_path")
        timekeeping_path = _string(self.configuration, "timekeeping_path")

        timeout = httpx.Timeout(max(1.0, min(timeout_seconds, 60.0)))
        async with httpx.AsyncClient(timeout=timeout) as client:
            token_response = await client.post(
                auth_url,
                auth=httpx.BasicAuth(client_id, client_secret),
                data={"grant_type": "client_credentials", "scope": scope},
            )
            token_response.raise_for_status()
            payload = token_response.json()
            token = payload.get("access_token") if isinstance(payload, dict) else None
            if not isinstance(token, str) or not token:
                raise InvalidConfiguration("flaik authentication did not return an access token")
            headers = {"Authorization": f"Bearer {token}"}
            base = self.source.endpoint_url.rstrip("/")
            health = await client.get(f"{base}/health", headers=headers)
            health.raise_for_status()

            class_payload: Any = []
            capabilities = ["health"]
            if classes_path:
                response = await client.get(f"{base}/{classes_path.lstrip('/')}", headers=headers)
                response.raise_for_status()
                class_payload = response.json() if response.content else []
                capabilities.append("class_management")
            if timekeeping_path:
                response = await client.get(
                    f"{base}/{timekeeping_path.lstrip('/')}", headers=headers
                )
                response.raise_for_status()
                capabilities.append("timekeeping")

        note = None
        if not classes_path or not timekeeping_path:
            note = (
                "Live flaik connection is healthy; module paths remain disabled until the "
                "authorized Snowbird/flaik contract supplies them."
            )
        return self._snapshot(
            connected=True,
            groups=_normalize_groups(class_payload),
            capabilities=capabilities,
            note=note,
        )


def correlate_radio_text(text: str, snapshot: FlaikOperationalSnapshot) -> FlaikRadioContext:
    lowered = " ".join(text.casefold().split())
    best: FlaikGroup | None = None
    confidence = 0.0
    for group in snapshot.groups:
        label = group.label.casefold()
        group_id = group.group_id.casefold()
        score = 0.0
        if group_id and group_id in lowered:
            score = 0.98
        elif label and label in lowered:
            score = 0.95
        else:
            parts = [part for part in label.split() if len(part) > 2]
            matches = sum(1 for part in parts if part in lowered)
            if parts and matches:
                score = min(0.55 + matches * 0.1, 0.85)
        if score > confidence:
            best = group
            confidence = score
    if best is None:
        return FlaikRadioContext(
            source_id=snapshot.source_id,
            connected=snapshot.connected,
        )
    return FlaikRadioContext(
        source_id=snapshot.source_id,
        connected=snapshot.connected,
        group_id=best.group_id,
        group_label=best.label,
        instructor_ref=best.instructor_ref,
        participant_count=best.participant_count,
        status=best.status,
        meeting_area=best.meeting_area,
        confidence=confidence,
    )
