"""Search/ask (K-01), Library (K-07), access (K-05), lists/categories (K-06/K-13), dashboards (K-11/K-12), ladder (K-10)."""

from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.modules.knowledge.jobs import run_ladder
from app.modules.knowledge.models import KnowledgeItem
from app.modules.knowledge.rules import health, stages_due
from app.shared import clock
from conftest_helpers import create_item
from testkit import auth


def test_ladder_stages() -> None:
    due = clock.today()
    numbers = {d: [s.number for s in stages_due(due, due + timedelta(days=d))] for d in (-30, -20, -14, -7, 0, 1, 8, 14, 30, 90)}
    assert numbers[-30] == [1] and numbers[-20] == [] and numbers[-14] == [2] and numbers[-7] == [3] and numbers[0] == [4]
    assert numbers[1] == [5] and numbers[8] == [5]  # weekly while overdue
    assert 6 in numbers[14] and 7 in numbers[30] and 8 in numbers[90]


def test_health_score() -> None:
    weights = {"on_time": 0.7, "owner": 0.15, "backup": 0.15}
    h = health([("verified", True, True), ("overdue", True, False), ("due_soon", False, False), ("verified", True, True)], weights)
    assert (h.items, h.overdue, h.due_soon, h.no_owner, h.no_backup, h.on_time_pct) == (4, 1, 1, 1, 2, 75)
    assert h.score == round(100 * (0.7 * 0.75 + 0.15 * 0.75 + 0.15 * 0.5))


async def test_search_and_ask_respect_access_and_freshness(
    client: AsyncClient, hub, session: AsyncSession  # type: ignore[no-untyped-def]
) -> None:
    await create_item(client, hub, title="Refund process",
                      body="Refunds are allowed within 7 days of delivery. Approve up to 5,000 rupees yourself.")
    await create_item(client, hub, title="Secret salary bands", body="Refunds of salary advances are processed monthly.",
                      visibility="team", team=hub.hr, owner=hub.dev)
    hits = (await client.get("/knowledge/search?q=refund", headers=auth(hub.meera))).json()
    assert [h["item"]["title"] for h in hits] == ["Refund process"]  # the HR-only item stays hidden
    assert "Refunds are allowed" in hits[0]["snippet"]

    answer = (await client.post("/knowledge/ask", json={"question": "How many days are refunds allowed?"},
                                headers=auth(hub.meera))).json()
    assert "7 days" in answer["answer"] and answer["sources"][0]["title"] == "Refund process"

    # Items left unreviewed for 30+ days are left out of answers.
    item = (await session.scalars(select(KnowledgeItem).where(KnowledgeItem.title == "Refund process"))).one()
    item.next_review_on = clock.today() - timedelta(days=31)
    await session.commit()
    stale = (await client.post("/knowledge/ask", json={"question": "How many days are refunds allowed?"},
                               headers=auth(hub.meera))).json()
    assert stale["sources"] == []


async def test_library_filters_and_bulk(client: AsyncClient, hub) -> None:  # type: ignore[no-untyped-def]
    a = await create_item(client, hub, title="Payroll month-end checklist", kind="checklist", category_id=hub.hr_cat.id)
    await create_item(client, hub, title="Refund process", category_id=hub.support_sops.id, critical=True)
    lib = (await client.get("/knowledge/library", headers=auth(hub.meera))).json()
    assert lib["total"] == 2 and {k["kind"] for k in lib["kinds"]} == {"checklist", "sop"}
    counts = {c["path"]: c["item_count"] for c in lib["categories"]}
    assert counts["Support"] == 1 and counts["Support › Support SOPs"] == 1  # parents count their children
    by_category = (await client.get(f"/knowledge/library?category_id={hub.support_cat.id}", headers=auth(hub.meera))).json()
    assert [i["title"] for i in by_category["items"]] == ["Refund process"]
    critical = (await client.get("/knowledge/library?critical=true", headers=auth(hub.meera))).json()
    assert [i["title"] for i in critical["items"]] == ["Refund process"]

    assert (await client.post("/knowledge/bulk", json={"item_ids": [a["id"]], "action": "remind_owners"},
                              headers=auth(hub.meera))).status_code == 403
    moved = await client.post("/knowledge/bulk", json={"item_ids": [a["id"]], "action": "change_owner",
                                                       "owner_id": str(hub.anil.id)}, headers=auth(hub.admin))
    assert moved.json() == {"count": 1}


async def test_access_requests_and_owner_rules(client: AsyncClient, hub) -> None:  # type: ignore[no-untyped-def]
    item = await create_item(client, hub, title="Full team playbook", visibility="restricted", backup=hub.anil)
    url = f"/knowledge/items/{item['id']}"
    assert (await client.get(url, headers=auth(hub.dev))).status_code == 403
    request = (await client.post(f"{url}/access-requests", json={"reason": "Covering for support"}, headers=auth(hub.dev))).json()
    assert request["status"] == "pending"
    # The backup owner cannot decide access; only the owner and knowledge admins can.
    assert (await client.post(f"/knowledge/access-requests/{request['id']}/decision", json={"approve": True},
                              headers=auth(hub.anil))).status_code == 403
    await client.post(f"/knowledge/access-requests/{request['id']}/decision", json={"approve": True}, headers=auth(hub.meera))
    assert (await client.get(url, headers=auth(hub.dev))).status_code == 200
    access = (await client.get(f"{url}/access", headers=auth(hub.meera))).json()
    assert [e["role"] for e in access["entries"]] == ["Owner", "Backup owner", "Viewer"]

    orphan = await create_item(client, hub, title="Server runbook")
    await client.post(f"/knowledge/items/{orphan['id']}/owner", json={"owner_id": str(hub.anil.id)}, headers=auth(hub.admin))
    assert (await client.get(f"/knowledge/items/{orphan['id']}", headers=auth(hub.anil))).json()["owner_name"] == "Anil Rao"


async def test_data_list_import_and_row_history(client: AsyncClient, hub) -> None:  # type: ignore[no-untyped-def]
    item = await create_item(client, hub, title="Vendors", kind="list", list_columns=["Vendor", "Status"])
    url = f"/knowledge/items/{item['id']}/rows"
    csv = "Vendor,Service,Owner,Renewal,Status\nZoom,Meetings,IT,Jan 2027,Active\nDelhivery,Shipping,Ops,Nov 2026,Renew\n"
    imported = await client.post(f"{url}/import", files={"file": ("vendors.csv", csv.encode(), "text/csv")},
                                 headers=auth(hub.meera))
    assert imported.json() == {"count": 2}
    rows = (await client.get(url, headers=auth(hub.dev))).json()
    assert rows["columns"] == ["Vendor", "Service", "Owner", "Renewal", "Status"]
    renew = (await client.get(f"{url}?status=renew", headers=auth(hub.dev))).json()
    assert [r["data"]["Vendor"] for r in renew["rows"]] == ["Delhivery"]
    row_id = rows["rows"][0]["id"]
    await client.patch(f"{url}/{row_id}", json={"data": {"Status": "Renew"}}, headers=auth(hub.meera))
    assert (await client.post(url, json={"data": {"Vendor": "X"}}, headers=auth(hub.dev))).status_code == 403


async def test_categories_merge(client: AsyncClient, hub) -> None:  # type: ignore[no-untyped-def]
    item = await create_item(client, hub, title="Escalation scripts", category_id=hub.support_sops.id)
    h = auth(hub.admin)
    escalation = (await client.post("/knowledge/categories", json={"name": "Escalation", "parent_id": str(hub.support_cat.id)},
                                    headers=h)).json()
    assert (await client.post("/knowledge/categories", json={"name": "x"}, headers=auth(hub.meera))).status_code == 403
    merged = await client.post(f"/knowledge/categories/{hub.support_sops.id}/merge", json={"into_id": escalation["id"]}, headers=h)
    assert merged.json() == {"count": 1}
    page = (await client.get(f"/knowledge/items/{item['id']}", headers=h)).json()
    assert page["category_path"] == "Support › Escalation"  # items and their history follow


async def test_dashboards_and_ladder(client: AsyncClient, hub, database: Database, session: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    for i in range(3):
        await create_item(client, hub, title=f"Support item {i}", category_id=hub.support_sops.id, backup=hub.anil if i else None)
    overdue = await create_item(client, hub, title="Escalation playbook", category_id=hub.support_sops.id)
    await create_item(client, hub, title="Leave policy", category_id=hub.hr_cat.id, owner=hub.dev)
    item = (await session.scalars(select(KnowledgeItem).where(KnowledgeItem.title == "Escalation playbook"))).one()
    item.next_review_on = clock.today() - timedelta(days=15)
    await session.commit()

    leader = (await client.get("/knowledge/dashboard", headers=auth(hub.admin))).json()
    assert leader["company"]["items"] == 5 and leader["company"]["overdue"] == 1
    assert {f["name"] for f in leader["by_function"]} == {"Support", "HR"}
    assert leader["attention"][0]["text"].startswith("Support: 1 items overdue")
    assert (await client.get("/knowledge/dashboard", headers=auth(hub.dev))).status_code == 403

    fn = (await client.get(f"/knowledge/dashboard/{hub.support_cat.id}", headers=auth(hub.head))).json()
    assert fn["tile"]["items"] == 4 and fn["by_category"][0]["name"] == "Support SOPs"
    assert fn["by_owner"][0]["name"] == "Meera Kapoor" and fn["by_owner"][0]["overdue"] == 1

    async with database.session_factory() as s:
        sent = await run_ladder(s)
        await s.commit()
        assert sent == 2  # one combined message each: the owner (weekly) and the function head (+14 days)
        again = await run_ladder(s)
        await s.commit()
    assert again == 0  # never twice
    inbox = (await client.get("/me/notifications", headers=auth(hub.head))).json()["items"]
    assert any("Escalation playbook" in n["body"] for n in inbox)
    mine = (await client.get("/knowledge/my-items", headers=auth(hub.meera))).json()
    assert mine["overdue"] == 1 and mine["items"][0]["item"]["id"] == overdue["id"]
