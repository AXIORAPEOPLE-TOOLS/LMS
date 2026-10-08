from httpx import AsyncClient

from testkit import UserFactory, auth


async def test_login_returns_token_and_me_works(client: AsyncClient, make_user: UserFactory) -> None:
    await make_user(email="asha@example.com", full_name="Asha Verma")
    response = await client.post("/auth/login", json={"email": "ASHA@example.com", "password": "Passw0rd!"})
    assert response.status_code == 200
    token = response.json()["access_token"]

    me = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["full_name"] == "Asha Verma"


async def test_wrong_password_is_rejected_in_plain_words(client: AsyncClient, make_user: UserFactory) -> None:
    await make_user(email="a@example.com")
    response = await client.post("/auth/login", json={"email": "a@example.com", "password": "nope"})
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "That email and password do not match."


async def test_me_requires_sign_in(client: AsyncClient) -> None:
    assert (await client.get("/me")).status_code == 401


async def test_preferences_validate_time_window(client: AsyncClient, make_user: UserFactory) -> None:
    user = await make_user()
    bad = await client.patch("/me/preferences", json={"reminder_window": ["13:00", "11:00"]}, headers=auth(user))
    assert bad.status_code == 422

    ok = await client.patch(
        "/me/preferences",
        json={"reminder_window": ["11:00", "13:00"], "reminder_channels": {"whatsapp": True}},
        headers=auth(user),
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["reminder_window"] == ["11:00", "13:00"]
    assert body["reminder_channels"] == {"in_app": True, "email": True, "whatsapp": True}


async def test_only_admins_manage_users(client: AsyncClient, make_user: UserFactory) -> None:
    learner = await make_user()
    admin = await make_user("admin")
    assert (await client.get("/users", headers=auth(learner))).status_code == 403
    directory = (await client.get("/people", headers=auth(learner))).json()
    assert {"id", "full_name", "department_id", "job_role_id"} == set(directory[0])  # no emails or roles

    created = await client.post(
        "/users",
        json={"email": "new@example.com", "full_name": "New Joiner", "password": "Welcome123"},
        headers=auth(admin),
    )
    assert created.status_code == 201
    duplicate = await client.post(
        "/users",
        json={"email": "new@example.com", "full_name": "Again", "password": "Welcome123"},
        headers=auth(admin),
    )
    assert duplicate.status_code == 409

    audit = await client.get("/audit?action=user.created", headers=auth(admin))
    assert any(row["details"]["email"] == "new@example.com" for row in audit.json())
