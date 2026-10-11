from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictError, NotAuthenticatedError, TooManyRequestsError
from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_token_pair,
    decode_token_payload,
    hash_password,
    verify_password,
)
from app.modules.accounts.models import AuthLockout, RefreshToken, User
from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.organizations.permissions import OrgMemberRole


def _representative_display_name(organization_name: str) -> str:
    prefix = "Представитель "
    max_org_len = 100 - len(prefix)
    return f"{prefix}{organization_name[:max_org_len]}"


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def _ensure_email_available(session: AsyncSession, email: str) -> None:
    if await get_user_by_email(session, email) is not None:
        raise ConflictError("Пользователь с таким email уже зарегистрирован")


async def _get_or_create_lockout(session: AsyncSession, identifier: str) -> AuthLockout:
    result = await session.execute(select(AuthLockout).where(AuthLockout.identifier == identifier))
    lockout = result.scalar_one_or_none()
    if lockout is None:
        lockout = AuthLockout(identifier=identifier)
        session.add(lockout)
        await session.flush()
    return lockout


async def _assert_not_locked(session: AsyncSession, identifier: str) -> AuthLockout:
    lockout = await _get_or_create_lockout(session, identifier)
    now = datetime.now(UTC)
    if lockout.locked_until is not None and lockout.locked_until > now:
        raise TooManyRequestsError(
            f"Слишком много неудачных попыток входа. Повторите через {settings.login_lockout_minutes} минут"
        )
    if lockout.locked_until is not None and lockout.locked_until <= now:
        lockout.failed_attempts = 0
        lockout.locked_until = None
    return lockout


async def _register_failed_attempt(session: AsyncSession, lockout: AuthLockout) -> None:
    lockout.failed_attempts += 1
    if lockout.failed_attempts >= settings.login_max_attempts:
        lockout.locked_until = datetime.now(UTC) + timedelta(minutes=settings.login_lockout_minutes)
        lockout.failed_attempts = 0
    await session.commit()


async def _clear_lockout(session: AsyncSession, lockout: AuthLockout) -> None:
    lockout.failed_attempts = 0
    lockout.locked_until = None


async def _issue_tokens(session: AsyncSession, user: User) -> tuple[str, str]:
    access_token, refresh_token, refresh_jti, expires_at = create_token_pair(user.id)
    session.add(RefreshToken(user_id=user.id, jti=refresh_jti, expires_at=expires_at))
    await session.commit()
    return access_token, refresh_token


async def register_user(session: AsyncSession, *, name: str, email: str, password: str) -> tuple[User, str, str]:
    await _ensure_email_available(session, email)
    user = User(
        email=email,
        password_hash=hash_password(password),
        name=name,
        personal_data_consent_at=datetime.now(UTC),
    )
    session.add(user)
    await session.flush()
    access_token, refresh_token = await _issue_tokens(session, user)
    await session.refresh(user)
    return user, access_token, refresh_token


async def register_organization(
    session: AsyncSession, *, name: str, email: str, password: str
) -> tuple[User, Organization, str, str]:
    await _ensure_email_available(session, email)
    user = User(
        email=email,
        password_hash=hash_password(password),
        name=_representative_display_name(name),
        personal_data_consent_at=datetime.now(UTC),
    )
    organization = Organization(name=name, email=email)
    organization.members.append(OrganizationMember(user=user, role=OrgMemberRole.REPRESENTATIVE))
    session.add_all([user, organization])
    await session.flush()
    access_token, refresh_token = await _issue_tokens(session, user)
    await session.refresh(user)
    await session.refresh(organization)
    return user, organization, access_token, refresh_token


async def login(session: AsyncSession, *, email: str, password: str) -> tuple[User, str, str]:
    lockout = await _assert_not_locked(session, email)
    user = await get_user_by_email(session, email)

    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        await _register_failed_attempt(session, lockout)
        raise NotAuthenticatedError("Неверный email или пароль")

    await _clear_lockout(session, lockout)
    user.last_login_at = datetime.now(UTC)
    access_token, refresh_token = await _issue_tokens(session, user)
    await session.refresh(user)
    return user, access_token, refresh_token


async def refresh_tokens(session: AsyncSession, refresh_token: str) -> tuple[User, str, str]:
    try:
        payload = decode_token_payload(refresh_token, TokenType.REFRESH)
    except InvalidTokenError as exc:
        raise NotAuthenticatedError("Недействительный или просроченный токен") from exc

    jti = payload["jti"]
    user_id = payload["sub"]
    result = await session.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    stored = result.scalar_one_or_none()
    if stored is None or not stored.is_active or str(stored.user_id) != user_id:
        raise NotAuthenticatedError("Недействительный или просроченный токен")

    user = await session.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise NotAuthenticatedError("Пользователь не найден или заблокирован")

    stored.revoked_at = datetime.now(UTC)
    access_token, new_refresh_token = await _issue_tokens(session, user)
    await session.refresh(user)
    return user, access_token, new_refresh_token


async def logout(session: AsyncSession, refresh_token: str) -> None:
    try:
        payload = decode_token_payload(refresh_token, TokenType.REFRESH)
    except InvalidTokenError:
        return

    result = await session.execute(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
    stored = result.scalar_one_or_none()
    if stored is not None and stored.revoked_at is None:
        stored.revoked_at = datetime.now(UTC)
        await session.commit()
