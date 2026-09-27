"""Read-only, allowlisted Monday board snapshots for the internal workspace pilot."""

import httpx

from terrasatch.errors import InvalidConfiguration, ProviderUnavailable


async def monday_snapshot(settings, *, transport=None):
    ids = [part.strip() for part in settings.workspace_monday_board_ids.split(",") if part.strip()]
    if not settings.workspace_monday_api_token or not ids:
        return {
            "connected": False,
            "boards": [],
            "detail": "A Monday.com server connection has not been configured.",
        }
    if len(ids) > 8 or any(not item.isdigit() for item in ids):
        raise InvalidConfiguration("Monday board allowlist must contain up to eight numeric IDs")
    query = (
        "query ($ids: [ID!]!) { boards(ids: $ids) { id name "
        "items_page(limit: 100) { cursor items { id name column_values { id text type } } } } }"
    )
    try:
        async with httpx.AsyncClient(timeout=15, transport=transport) as client:
            result = await client.post(
                "https://api.monday.com/v2",
                headers={"Authorization": settings.workspace_monday_api_token.get_secret_value()},
                json={"query": query, "variables": {"ids": ids}},
            )
            result.raise_for_status()
            data = result.json()
            if data.get("errors"):
                raise ValueError("Monday rejected the request")
            boards = data.get("data", {}).get("boards")
            if not isinstance(boards, list) or not boards:
                raise ValueError("No permitted boards returned")
            return {
                "connected": True,
                "boards": [
                    {
                        "id": b["id"],
                        "name": b["name"],
                        "partial": bool(b["items_page"].get("cursor")),
                        "items": b["items_page"]["items"],
                    }
                    for b in boards
                    if str(b["id"]) in ids
                ],
            }
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise ProviderUnavailable(
            "Monday.com could not be read. Check the configured token and board access."
        ) from error
