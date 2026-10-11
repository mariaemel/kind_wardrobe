from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import NotAuthenticatedError, PermissionDeniedError
from app.core.security import InvalidTokenError, TokenType, decode_token
from app.modules.accounts.models import User

bearer_scheme = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None:
        raise NotAuthenticatedError
    try:
        user_id = decode_token(credentials.credentials, TokenType.ACCESS)
    except InvalidTokenError as exc:
        raise NotAuthenticatedError("Недействительный или просроченный токен") from exc

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise NotAuthenticatedError("Пользователь не найден или заблокирован")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise PermissionDeniedError("Действие доступно только администратору")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
