from typing import Any

from httpx import AsyncClient

from testkit import auth


async def create_item(
    client: AsyncClient, hub: Any, *, title: str, body: str = "Some content for this item.", owner: Any = None,
    backup: Any = None, category_id: Any = None, visibility: str = "company", team: Any = None, kind: str = "sop",
    critical: bool = False, **extra: Any,
) -> dict[str, Any]:
    owner = owner or hub.meera
    payload = {
        "title": title, "kind": kind, "body": body, "owner_id": str(owner.id),
        "backup_owner_id": str(backup.id) if backup else None,
        "category_id": str(category_id) if category_id else None, "visibility": visibility,
        "team_department_id": str(team.id) if team else None, "is_critical": critical, **extra,
    }
    response = await client.post("/knowledge/items", json=payload, headers=auth(owner))
    assert response.status_code == 201, response.text
    return response.json()
