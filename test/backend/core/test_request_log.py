"""Every API call is logged in one line: method, path, status, time, user id and request id."""

import logging
from typing import Any

from httpx import AsyncClient

from testkit import UserFactory, auth


async def test_each_call_is_logged_with_user_and_time(client: AsyncClient, make_user: UserFactory, caplog: Any) -> None:
    user = await make_user()
    with caplog.at_level(logging.INFO, logger="api"):
        response = await client.get("/me", headers={**auth(user), "X-Request-ID": "abc123"})
    line = next(r for r in caplog.records if r.name == "api")
    text = line.getMessage()
    assert response.status_code == 200
    assert text.startswith("GET /api/me -> 200 in ") and f"user={user.id}" in text and "rid=abc123" in text
    assert line.levelno == logging.INFO


async def test_errors_are_warnings_and_secrets_in_the_query_are_hidden(client: AsyncClient, caplog: Any) -> None:
    with caplog.at_level(logging.INFO, logger="api"):
        await client.get("/me?token=supersecret&page=2")
    line = next(r for r in caplog.records if r.name == "api")
    assert line.levelno == logging.WARNING and "-> 401" in line.getMessage()
    assert "supersecret" not in line.getMessage() and "token=***" in line.getMessage() and "page=2" in line.getMessage()


async def test_health_polls_stay_quiet(client: AsyncClient, caplog: Any) -> None:
    with caplog.at_level(logging.INFO, logger="api"):
        await client.get("/health")
    assert not [r for r in caplog.records if r.name == "api"]
