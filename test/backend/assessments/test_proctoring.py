"""Mandatory proctored tests: consent, flags, a person decides, appeals, certificates (L-06, A-09)."""

import base64

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from testkit import UserFactory, auth, make_test


async def _take(client: AsyncClient, test_id: str, headers: dict, *, flags: list[str] = ()) -> dict:  # type: ignore[assignment]
    attempt = (await client.post(f"/tests/{test_id}/attempts", json={"consent": True}, headers=headers)).json()
    for question in attempt["questions"]:
        await client.put(f"/attempts/{attempt['id']}/answer", json={"question_id": question["id"], "option_index": 1},
                         headers=headers)
    for i, kind in enumerate(flags):
        r = await client.post(f"/attempts/{attempt['id']}/proctor-events", json={"kind": kind, "at_seconds": 60 * (i + 1)},
                              headers=headers)
        assert r.status_code == 204
    return (await client.post(f"/attempts/{attempt['id']}/submit", headers=headers)).json()


async def test_camera_test_needs_consent_or_in_person(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    test = await make_test(session, title="POSH awareness test", proctoring="camera", pass_mark=80, is_mandatory=True)
    learner = await make_user()
    refused = await client.post(f"/tests/{test.id}/attempts", json={"consent": False}, headers=auth(learner))
    assert refused.status_code == 422 and "in-person" in refused.json()["error"]["message"]
    booking = await client.post(f"/tests/{test.id}/in-person", json={"preferred_dates": "Mon or Tue"}, headers=auth(learner))
    assert booking.status_code == 201 and booking.json()["status"] == "requested"


async def test_clean_pass_issues_certificate(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    test = await make_test(session, title="POSH awareness test", proctoring="camera", pass_mark=80, validity_months=12)
    learner = await make_user(full_name="Asha Verma")
    result = await _take(client, str(test.id), auth(learner))
    assert result["status"] == "valid" and result["passed"] is True and result["certificate_id"]
    certs = (await client.get("/me/certificates", headers=auth(learner))).json()
    assert certs[0]["title"] == "POSH awareness" and certs[0]["status"] == "valid"
    verified = (await client.get(f"/certificates/verify/{certs[0]['code']}")).json()
    assert verified["holder"] == "Asha Verma" and verified["status"] == "valid"
    pdf = await client.get(f"/certificates/{certs[0]['id']}/pdf", headers=auth(learner))
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


async def test_flags_go_to_a_reviewer_and_nothing_fails_automatically(
    client: AsyncClient, session: AsyncSession, make_user: UserFactory
) -> None:
    test = await make_test(session, title="POSH awareness test", proctoring="camera", pass_mark=80)
    learner = await make_user(employee_code="E021")
    reviewer = await make_user("reviewer")
    second_reviewer = await make_user("reviewer")

    picture = base64.b64encode(b"\xff\xd8\xff fake jpeg").decode()
    attempt = (await client.post(f"/tests/{test.id}/attempts", json={"consent": True}, headers=auth(learner))).json()
    for question in attempt["questions"]:
        await client.put(f"/attempts/{attempt['id']}/answer", json={"question_id": question["id"], "option_index": 1},
                         headers=auth(learner))
    await client.post(f"/attempts/{attempt['id']}/proctor-events",
                      json={"kind": "second_face", "at_seconds": 252, "image_base64": picture}, headers=auth(learner))
    for at in (570, 575, 580):  # tab switched 3x -> one flag with count 3
        await client.post(f"/attempts/{attempt['id']}/proctor-events", json={"kind": "tab_switch", "at_seconds": at},
                          headers=auth(learner))
    result = (await client.post(f"/attempts/{attempt['id']}/submit", headers=auth(learner))).json()
    assert result["status"] == "under_review" and "Nothing is failed automatically" in result["message"]
    assert (await client.get("/me/certificates", headers=auth(learner))).json() == []

    # Learners cannot see the queue.
    assert (await client.get("/proctoring/queue", headers=auth(learner))).status_code == 403
    queue = (await client.get("/proctoring/queue", headers=auth(reviewer))).json()
    assert queue[0]["flags"] == 2 and queue[0]["severity"] == "high" and queue[0]["employee_code"] == "E021"
    case = (await client.get(f"/proctoring/attempts/{attempt['id']}", headers=auth(reviewer))).json()
    tab = next(f for f in case["flags"] if f["kind"] == "tab_switch")
    assert tab["count"] == 3
    face = next(f for f in case["flags"] if f["kind"] == "second_face")
    image = await client.get(f"/proctoring/events/{face['id']}/image", headers=auth(reviewer))
    assert image.status_code == 200 and image.headers["cache-control"] == "no-store"

    no_note = await client.post(f"/proctoring/attempts/{attempt['id']}/decision", json={"decision": "invalid", "note": ""},
                                headers=auth(reviewer))
    assert no_note.status_code == 422  # a note is required
    await client.post(f"/proctoring/attempts/{attempt['id']}/decision",
                      json={"decision": "invalid", "note": "Another person answered questions."}, headers=auth(reviewer))

    # The learner can appeal; a different reviewer decides.
    appeal = await client.post(f"/attempts/{attempt['id']}/appeal", json={"note": "My sister walked in behind me briefly."},
                               headers=auth(learner))
    assert appeal.status_code == 204
    same = await client.post(f"/proctoring/attempts/{attempt['id']}/decision",
                             json={"decision": "valid", "note": "ok fine"}, headers=auth(reviewer))
    assert same.status_code == 403
    await client.post(f"/proctoring/attempts/{attempt['id']}/decision",
                      json={"decision": "valid", "note": "Brief, not answering."}, headers=auth(second_reviewer))
    certs = (await client.get("/me/certificates", headers=auth(learner))).json()
    assert len(certs) == 1

    audit = (await client.get("/audit?entity_type=test_attempt", headers=auth(await make_user("admin")))).json()
    actions = {row["action"] for row in audit}
    assert {"proctoring.consent", "proctoring.evidence_viewed", "proctoring.decision", "proctoring.appeal"} <= actions


async def test_failing_mandatory_test_gives_plain_message(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    test = await make_test(session, title="DPDP test", pass_mark=80, questions=5)
    learner = await make_user()
    attempt = (await client.post(f"/tests/{test.id}/attempts", json={}, headers=auth(learner))).json()
    result = (await client.post(f"/attempts/{attempt['id']}/submit", headers=auth(learner))).json()
    assert result["passed"] is False and "The pass mark is 80%" in result["message"]
