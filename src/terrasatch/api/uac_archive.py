"""Read-only Utah Avalanche Center historical archive served from OCI-local storage."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

router = APIRouter(prefix="/uac", tags=["uac"])

_REGION_IDS = {
    "Logan": "logan",
    "Ogden": "ogden",
    "Salt Lake": "salt-lake",
    "Provo": "provo",
    "Uintas": "uintas",
    "Skyline": "skyline",
    "Moab": "moab",
    "Abajos": "abajos",
    "Southwest": "southwest",
}
_HUMAN_TRIGGERS = (
    "skier",
    "snowboarder",
    "snowmobiler",
    "snowbike",
    "hiker",
    "climber",
    "human",
    "explosive",
    "artillery",
    "cornice",
)


@dataclass(frozen=True)
class ArchiveIndex:
    records: tuple[dict[str, object], ...]
    loaded_at: str
    archive_total: int
    supported_total: int
    unsupported_total: int
    columns: int
    source_name: str


_cache_key: tuple[str, int, int] | None = None
_cache_index: ArchiveIndex | None = None


def _measure(value: str) -> str:
    text = value.strip()
    if text.endswith("'") and text[:-1].replace(",", "").replace(".", "").isdigit():
        return f"{text[:-1].strip()} ft"
    if text.endswith('"') and text[:-1].replace(",", "").replace(".", "").isdigit():
        return f"{text[:-1].strip()} in"
    return text


def _parse_date(value: str) -> str | None:
    text = value.strip()
    for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, pattern).replace(tzinfo=UTC)
            return parsed.isoformat().replace("+00:00", "Z")
        except ValueError:
            continue
    return None


def _coordinates(value: str) -> list[float] | None:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 2:
        return None
    try:
        latitude, longitude = (float(part) for part in parts)
    except ValueError:
        return None
    if abs(latitude) > 90 or abs(longitude) > 180:
        return None
    return [longitude, latitude]


def _positive_int(value: str) -> int | None:
    try:
        parsed = int(value.strip())
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _text(row: dict[str, str], key: str) -> str:
    return (row.get(key) or "").strip()


def _archive_context(
    row: dict[str, str],
    *,
    weak_layer: str,
    width: str,
    vertical: str,
) -> dict[str, object] | None:
    comments = [
        _text(row, "Comments 1"),
        _text(row, "Comments 2"),
        _text(row, "Comments 3"),
        _text(row, "Comments 4"),
        _text(row, "Comment"),
    ]
    comments = [comment for comment in comments if comment]
    context: dict[str, object] = {
        "triggerInfo": _text(row, "Trigger: additional info") or None,
        "weakLayer": weak_layer or None,
        "width": width or None,
        "vertical": vertical or None,
        "caught": _positive_int(_text(row, "Caught")),
        "carried": _positive_int(_text(row, "Carried")),
        "buriedPartly": _positive_int(_text(row, "Buried - Partly")),
        "buriedFully": _positive_int(_text(row, "Buried - Fully")),
        "injured": _positive_int(_text(row, "Injured")),
        "killed": _positive_int(_text(row, "Killed")),
        "accidentSummary": _text(row, "Accident and Rescue Summary") or None,
        "terrainSummary": _text(row, "Terrain Summary") or None,
        "weatherHistory": _text(row, "Weather Conditions and History") or None,
        "comments": comments or None,
    }
    return {key: value for key, value in context.items() if value is not None} or None


def _record(row: dict[str, str], row_index: int) -> dict[str, object] | None:
    region_name = _text(row, "Region")
    region = _REGION_IDS.get(region_name)
    date = _parse_date(_text(row, "Date"))
    location = _text(row, "Place")
    if not region or not date or not location:
        return None

    trigger = _text(row, "Trigger")
    weak_layer = _text(row, "Weak Layer")
    depth = _measure(_text(row, "Depth"))
    width = _measure(_text(row, "Width"))
    vertical = _measure(_text(row, "Vertical"))
    coordinates = _coordinates(_text(row, "Coordinates"))
    stable = hashlib.sha1(
        f"{date}|{region}|{location}|{trigger}|{_text(row, 'Coordinates')}|{row_index}".encode(),
        usedforsecurity=False,
    ).hexdigest()[:12]

    return {
        "id": f"csv-{date[:10]}-{region}-{stable}",
        "date": date,
        "region": region,
        "location": location,
        "trigger": trigger,
        "depth": depth,
        "width": width,
        "vertical": vertical,
        "aspect": _text(row, "Aspect"),
        "elevation": _measure(_text(row, "Elevation")),
        "slopeAngle": "",
        "avalancheType": "",
        "problem": "",
        "weakLayer": weak_layer,
        "coordinates": coordinates,
        "sourceUrl": "https://utahavalanchecenter.org/avalanches/filters",
        "source": "uac",
        "archiveContext": _archive_context(
            row,
            weak_layer=weak_layer,
            width=width,
            vertical=vertical,
        ),
    }


def _load_archive(path_value: str | None) -> ArchiveIndex:
    if not path_value:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TERRASATCH_UAC_ARCHIVE_PATH is not configured on this deployment.",
        )

    path = Path(path_value).expanduser()
    try:
        stat = path.stat()
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Configured UAC archive file is unavailable.",
        ) from error

    global _cache_key, _cache_index
    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    if _cache_key == key and _cache_index is not None:
        return _cache_index

    records: list[dict[str, object]] = []
    archive_total = 0
    unsupported_total = 0
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            required = {"Date", "Region", "Place", "Trigger", "Coordinates"}
            if not required.issubset(fieldnames):
                raise ValueError("UAC CSV columns were not recognized")
            for row_index, row in enumerate(reader):
                archive_total += 1
                parsed = _record(row, row_index)
                if parsed is None:
                    unsupported_total += 1
                    continue
                records.append(parsed)
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Configured UAC archive could not be parsed.",
        ) from error

    records.sort(key=lambda item: str(item["date"]), reverse=True)
    index = ArchiveIndex(
        records=tuple(records),
        loaded_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        archive_total=archive_total,
        supported_total=len(records),
        unsupported_total=unsupported_total,
        columns=len(fieldnames),
        source_name=path.name,
    )
    _cache_key = key
    _cache_index = index
    return index


def _trigger_group(trigger: str) -> Literal["natural", "human", "unknown"]:
    normalized = trigger.lower()
    if "natural" in normalized:
        return "natural"
    if any(keyword in normalized for keyword in _HUMAN_TRIGGERS):
        return "human"
    return "unknown"


def _record_search_text(record: dict[str, object]) -> str:
    context = record.get("archiveContext")
    context_text = ""
    if isinstance(context, dict):
        context_text = " ".join(
            str(value)
            for value in context.values()
            if value is not None
        )
    return " ".join(
        str(record.get(key) or "")
        for key in ("location", "trigger", "weakLayer", "aspect", "elevation")
    ) + f" {context_text}"


@router.get("/archive")
async def get_uac_archive(
    request: Request,
    response: Response,
    region: str = Query(default="all"),
    q: str | None = Query(default=None),
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    trigger: Literal["all", "natural", "human"] = Query(default="all"),
    mapped: bool = Query(default=False),
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    """Serve filtered public UAC history from the OCI-hosted archive file."""

    if region != "all" and region not in _REGION_IDS.values():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown UAC region")

    index = _load_archive(request.app.state.settings.uac_archive_path)
    normalized_query = (q or "").strip().lower()
    filtered: list[dict[str, object]] = []
    for record in index.records:
        if region != "all" and record["region"] != region:
            continue
        record_date = str(record["date"])[:10]
        if date_from and record_date < date_from:
            continue
        if date_to and record_date > date_to:
            continue
        if trigger != "all" and _trigger_group(str(record.get("trigger") or "")) != trigger:
            continue
        if mapped and not record.get("coordinates"):
            continue
        if normalized_query and normalized_query not in _record_search_text(record).lower():
            continue
        filtered.append(record)

    page = filtered[offset : offset + limit]
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=1800"
    return {
        "records": page,
        "metadata": {
            "dataMode": "terrasatch-oci-archive",
            "parserVersion": 1,
            "syncedAt": index.loaded_at,
            "source": f"TerraSatch OCI archive · {index.source_name}",
            "warning": None,
            "archiveTotal": index.archive_total,
            "supportedTotal": index.supported_total,
            "unsupportedTotal": index.unsupported_total,
            "matchedRecords": len(filtered),
            "returnedRecords": len(page),
            "offset": offset,
            "limit": limit,
            "coordinateCount": sum(1 for item in page if item.get("coordinates")),
            "csvColumns": index.columns,
        },
    }
