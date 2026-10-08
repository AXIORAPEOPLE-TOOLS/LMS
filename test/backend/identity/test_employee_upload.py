from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.skills.models import JobRole
from testkit import UserFactory, auth

CSV = (
    "Full name,Email,Job title,Department,Employee ID\n"
    "Riya Sharma,riya@example.com,Admissions Counsellor,Admissions,E101\n"
    "Karan Mehta,karan@example.com,Admissions Exec,Admissions,E102\n"
    "Neha T,neha@example.com,CS Lead,Support,E103\n"
    "No Email,,Admissions Counsellor,Admissions,E104\n"
)


async def _roles(session: AsyncSession) -> dict[str, JobRole]:
    roles = {
        name: JobRole(code=code, name=name)
        for code, name in [
            ("ADM-C", "Admissions Counsellor"),
            ("CS-TL", "Customer Support Team Lead"),
            ("ENG", "Software Engineer"),
        ]
    }
    session.add_all(roles.values())
    await session.commit()
    return roles


async def test_upload_preview_suggests_roles_and_flags_errors(
    client: AsyncClient, session: AsyncSession, make_user: UserFactory
) -> None:
    roles = await _roles(session)
    admin = await make_user("admin")
    response = await client.post(
        "/users/upload/preview",
        files={"file": ("people.csv", CSV.encode(), "text/csv")},
        headers=auth(admin),
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["ready"], body["needs_role"], body["errors"]) == (1, 2, 1)
    by_email = {r["email"]: r for r in body["rows"]}
    assert by_email["karan@example.com"]["suggested_role_name"] == "Admissions Counsellor"
    assert by_email["neha@example.com"]["suggested_role_name"] == "Customer Support Team Lead"
    assert by_email["riya@example.com"]["job_role_id"] == str(roles["Admissions Counsellor"].id)


async def test_upload_commit_creates_people_and_departments(
    client: AsyncClient, session: AsyncSession, make_user: UserFactory
) -> None:
    roles = await _roles(session)
    admin = await make_user("admin")
    rows = [
        {"full_name": "Riya Sharma", "email": "riya@example.com", "job_role_id": str(roles["Admissions Counsellor"].id),
         "department": "Admissions"},
        {"full_name": "Already There", "email": admin.email, "job_role_id": str(roles["Software Engineer"].id)},
    ]
    response = await client.post("/users/upload/commit", json={"rows": rows}, headers=auth(admin))
    assert response.json() == {"created": 1, "skipped": 1}
    departments = (await client.get("/departments", headers=auth(admin))).json()
    assert [d["name"] for d in departments] == ["Admissions"]


async def test_upload_rejects_unknown_file_type(client: AsyncClient, make_user: UserFactory) -> None:
    admin = await make_user("admin")
    response = await client.post(
        "/users/upload/preview", files={"file": ("people.pdf", b"%PDF", "application/pdf")}, headers=auth(admin)
    )
    assert response.status_code == 422
