"""Add in three clicks (K-02), knowledge page (K-03), versions/revisions/reviews (K-08)."""

from datetime import timedelta

from httpx import AsyncClient

from app.shared import clock
from conftest_helpers import create_item
from testkit import auth

REFUND = (
    "1. Check the order date. Refunds are allowed within 7 days of delivery.\n"
    "2. Confirm the reason and ask for a photo for damaged items.\n"
    "3. Approve up to ₹2,000 yourself; above that, ask the team lead.\n"
)


async def test_add_in_three_clicks_with_suggestions(client: AsyncClient, hub) -> None:  # type: ignore[no-untyped-def]
    h = auth(hub.meera)
    await create_item(client, hub, title="Escalation playbook", category_id=hub.support_sops.id, owner=hub.meera,
                      backup=hub.anil, body="When a customer is upset about delivery or refunds, escalate to the team lead.")
    upload = (await client.post("/knowledge/uploads", files={"file": ("Refund_SOP_v3.txt", REFUND.encode(), "text/plain")},
                                headers=h)).json()
    assert upload["has_text"] is True
    s = (await client.post("/knowledge/suggest", json={"upload_id": upload["id"]}, headers=h)).json()
    assert s["title"] == "Refund" and s["kind"] == "sop" and s["category_path"] == "Support › Support SOPs"
    assert (s["owner_name"], s["backup_owner_name"]) == ("Meera Kapoor", "Anil Rao")
    assert s["visibility"] == "team" and s["visibility_label"] == "Support team (Team)"
    assert s["review_label"].startswith("In 12 months")

    created = await client.post("/knowledge/items", json={
        "title": "Refund process", "kind": s["kind"], "category_id": s["category_id"], "owner_id": s["owner_id"],
        "backup_owner_id": s["backup_owner_id"], "visibility": "team", "team_department_id": str(hub.support.id),
        "upload_id": upload["id"]}, headers=h)
    assert created.status_code == 201
    item = created.json()
    assert item["version"] == "1.0" and item["status"] == "verified" and "Refunds are allowed" in item["body"]
    assert item["attachments"][0]["name"] == "Refund_SOP_v3.txt"
    assert item["my_role"] == "owner" and item["can_change_access"] is True

    # Adding the same thing again: "Similar item found, add as a new version instead?"
    again = (await client.post("/knowledge/suggest", json={"title": "Refund process"}, headers=h)).json()
    assert again["similar_item_title"] == "Refund process" and again["similar_item_version"] == "1.0"


async def test_team_items_are_private_to_the_team(client: AsyncClient, hub) -> None:  # type: ignore[no-untyped-def]
    item = await create_item(client, hub, title="Refund process", visibility="team", team=hub.support)
    assert (await client.get(f"/knowledge/items/{item['id']}", headers=auth(hub.anil))).status_code == 200
    denied = await client.get(f"/knowledge/items/{item['id']}", headers=auth(hub.dev))
    assert denied.status_code == 403 and "ask the owner" in denied.json()["error"]["message"]
    library = (await client.get("/knowledge/library", headers=auth(hub.dev))).json()
    assert library["total"] == 0


async def test_versions_compare_restore_and_editor_changes(client: AsyncClient, hub) -> None:  # type: ignore[no-untyped-def]
    item = await create_item(client, hub, title="Refund process", body=REFUND, backup=hub.anil)
    url = f"/knowledge/items/{item['id']}"
    owner = auth(hub.meera)

    v11 = (await client.put(url, json={"body": REFUND.replace("₹2,000", "₹5,000"),
                                        "change_note": "Refund limit raised after the finance review."}, headers=owner)).json()
    assert v11["version"] == "1.1"
    diff = (await client.get(f"{url}/compare?from_version=1.0&to_version=1.1", headers=owner)).json()
    changed = [line for line in diff["lines"] if line["op"] != "same"]
    assert [(c["op"], "₹5,000" in c["text"]) for c in changed] == [("remove", False), ("add", True)]
    assert diff["change_note"] == "Refund limit raised after the finance review."

    # The backup can edit, but the owner publishes: the change waits for approval.
    await client.put(url, json={"body": REFUND + "4. Tell the customer the date.\n", "change_note": "Added step 4"},
                     headers=auth(hub.anil))
    page = (await client.get(url, headers=owner)).json()
    assert page["version"] == "1.1" and page["pending_change"] is True
    mine = (await client.get("/knowledge/my-items", headers=owner)).json()
    waiting = next(i for i in mine["items"] if i["reason"] == "waiting_for_me")
    assert waiting["detail"] == "Waiting for my approval" and "change by Anil Rao" in waiting["item"]["title"]
    await client.post(f"/knowledge/revisions/{waiting['revision_id']}/decision", json={"approve": True}, headers=owner)
    assert (await client.get(url, headers=owner)).json()["version"] == "1.2"

    restored = (await client.post(f"{url}/restore/1.0", headers=owner)).json()
    assert restored["version"] == "1.3" and "₹2,000" in restored["body"]  # nothing is ever overwritten
    history = (await client.get(f"{url}/history", headers=owner)).json()
    labels = [h["label"] for h in history if h["kind"] == "version"]
    assert labels == ["Version 1.3", "Version 1.2", "Version 1.1", "Version 1.0"]
    approved = next(h for h in history if h["label"] == "Version 1.2")
    assert approved["approved_by_name"] == "Meera Kapoor"

    # Viewers cannot edit.
    assert (await client.put(url, json={"body": "x"}, headers=auth(hub.dev))).status_code == 403


async def test_verify_snooze_and_hand_over(client: AsyncClient, hub) -> None:  # type: ignore[no-untyped-def]
    item = await create_item(client, hub, title="Travel policy", category_id=hub.support_cat.id)
    url = f"/knowledge/items/{item['id']}"
    h = auth(hub.meera)
    await client.patch(f"{url}/settings", json={"next_review_on": str(clock.today() - timedelta(days=12))}, headers=h)
    assert (await client.get(url, headers=h)).json()["status"] == "overdue"

    first = (await client.post(f"{url}/snooze", json={"reason": "Waiting for finance"}, headers=h)).json()
    assert first["snooze_count"] == 1
    await client.post(f"{url}/snooze", json={"reason": "Still waiting"}, headers=h)
    third = await client.post(f"{url}/snooze", json={"reason": "Again"}, headers=h)
    assert third.status_code == 409  # twice only
    head_inbox = (await client.get("/me/notifications", headers=auth(hub.head))).json()["items"]
    assert any("snoozed 2 times" in n["title"] for n in head_inbox)  # then the function head is told

    verified = (await client.post(f"{url}/verify", json={}, headers=h)).json()
    assert verified["status"] == "verified" and verified["snooze_count"] == 0

    handed = (await client.post(f"{url}/hand-over", json={"new_owner_id": str(hub.anil.id)}, headers=h)).json()
    assert handed["owner_name"] == "Anil Rao"
    assert (await client.post(f"{url}/verify", json={}, headers=h)).status_code == 403  # Meera is no longer owner


async def test_turn_into_course_needs_learning_admin(client: AsyncClient, hub, make_user) -> None:  # type: ignore[no-untyped-def]
    item = await create_item(client, hub, title="Refund process", body=REFUND * 3)
    assert (await client.post(f"/knowledge/items/{item['id']}/course", headers=auth(hub.meera))).status_code == 403
    lms_admin = await make_user("admin")
    response = await client.post(f"/knowledge/items/{item['id']}/course", headers=auth(lms_admin))
    assert response.status_code == 200
    page = (await client.get(f"/knowledge/items/{item['id']}", headers=auth(lms_admin))).json()
    assert page["linked_course_id"] == response.json()["course_id"]
