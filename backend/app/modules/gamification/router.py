import asyncio
import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.database import get_database
from app.core.deps import AdminUser, CurrentUser, SessionDep
from app.modules.gamification.schemas import BadgesOut, BoardOut, ChallengeIn, ChallengeOut, ComplianceBoardOut, ProfileOut
from app.modules.gamification.service import GamificationService
from app.modules.identity.models import User

router = APIRouter(tags=["gamification"])

LIVE_INTERVAL_SECONDS = 4  # boards update within 5 seconds


@router.get("/me/profile", response_model=ProfileOut)
async def profile(session: SessionDep, user: CurrentUser) -> object:
    return await GamificationService(session).profile(user)


@router.get("/me/badges", response_model=BadgesOut)
async def badges(session: SessionDep, user: CurrentUser) -> object:
    return await GamificationService(session).badges(user)


@router.get("/challenges", response_model=list[ChallengeOut])
async def challenges(session: SessionDep, user: CurrentUser) -> object:
    return await GamificationService(session).challenges_for(user)


@router.post("/challenges/{challenge_id}/join", response_model=ChallengeOut)
async def join(challenge_id: UUID, session: SessionDep, user: CurrentUser) -> object:
    return await GamificationService(session).join(challenge_id, user)


@router.post("/admin/challenges", response_model=ChallengeOut, status_code=201)
async def create_challenge(data: ChallengeIn, session: SessionDep, admin: AdminUser) -> object:
    service = GamificationService(session)
    challenge = await service.create_challenge(data, admin)
    return await service._challenge_out(challenge, admin)


@router.get("/leaderboards/compliance", response_model=ComplianceBoardOut)
async def compliance(session: SessionDep, _: CurrentUser, period: str = "quarter") -> object:
    return await GamificationService(session).compliance_by_department(period)


@router.get("/leaderboards/{board}", response_model=BoardOut)
async def board(
    board: str,
    session: SessionDep,
    user: CurrentUser,
    scope: str = "company",
    period: str = "quarter",
    skill_id: UUID | None = None,
) -> object:
    return await GamificationService(session).board(board, user, scope=scope, period=period, skill_id=skill_id)


@router.get("/leaderboards/{board}/stream")
async def board_stream(
    board: str,
    request: Request,
    user: CurrentUser,
    scope: str = "company",
    period: str = "quarter",
    skill_id: UUID | None = None,
) -> StreamingResponse:
    """Server-sent events: pushes the board whenever it changes. The UI falls back to polling."""
    viewer_id = user.id

    async def events() -> AsyncIterator[str]:
        last = ""
        while not await request.is_disconnected():
            try:
                async with get_database().session_factory() as session:
                    viewer = await session.get(User, viewer_id)
                    if viewer is None:
                        return
                    data = await GamificationService(session).board(board, viewer, scope=scope, period=period, skill_id=skill_id)
                if data.version != last:
                    last = data.version
                    yield f"event: board\ndata: {data.model_dump_json()}\n\n"
                else:
                    yield ": keep-alive\n\n"
            except Exception:  # degrade quietly; the client keeps the last board
                yield f"event: degraded\ndata: {json.dumps({'retry_seconds': 15})}\n\n"
                await asyncio.sleep(15)
            await asyncio.sleep(LIVE_INTERVAL_SECONDS)

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
