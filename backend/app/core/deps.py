"""FastAPI dependencies shared by every router."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.security import decode_access_token
from app.modules.identity.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(request: Request, session: SessionDep, token: Annotated[str | None, Depends(oauth2_scheme)]) -> User:
    if not token:
        raise AuthenticationError("Please sign in.")
    user = await session.get(User, decode_access_token(token))
    if user is None or not user.is_active:
        raise AuthenticationError("Your account is not active.")
    request.state.user_id = str(user.id)  # for the API call log (id only, no personal data)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: str) -> Callable[..., Coroutine[Any, Any, User]]:
    """Allow the request only if the user holds at least one of `roles`."""

    async def _checker(user: CurrentUser) -> User:
        if not user.has_role(*roles):
            raise PermissionDeniedError("You do not have access to this page.")
        return user

    return _checker


AdminUser = Annotated[User, Depends(require_roles("admin"))]
ManagerUser = Annotated[User, Depends(require_roles("manager", "admin"))]
KnowledgeAdminUser = Annotated[User, Depends(require_roles("knowledge_admin", "admin"))]
