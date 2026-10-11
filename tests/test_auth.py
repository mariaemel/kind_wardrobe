import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import TokenType, create_token
from app.models import AuthLockout, Organization, OrganizationMember, RefreshToken, User
from app.modules.organizations.permissions import OrgMemberRole, OrgPermission


async def test_register_user_success(client: AsyncClient, session: AsyncSession) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "name": " Анна ",
            "email": "Anna@Example.com",
            "password": "Password123",
            "personal_data_consent": True,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "anna@example.com"
    assert body["user"]["name"] == "Анна"
    assert body["tokens"]["token_type"] == "bearer"
    assert body["tokens"]["access_token"]
    assert body["tokens"]["refresh_token"]

    user = (await session.execute(select(User).where(User.email == "anna@example.com"))).scalar_one()
    assert user.personal_data_consent_at is not None
    tokens = (await session.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))).scalars().all()
    assert len(tokens) == 1


async def test_register_user_requires_consent(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Анна",
            "email": "anna2@example.com",
            "password": "Password123",
            "personal_data_consent": False,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_register_user_duplicate_email(client: AsyncClient) -> None:
    payload = {
        "name": "Анна",
        "email": "dup@example.com",
        "password": "Password123",
        "personal_data_consent": True,
    }
    assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 201
    response = await client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_register_organization_creates_representative_link(
    client: AsyncClient, session: AsyncSession
) -> None:
    response = await client.post(
        "/api/v1/auth/register/organization",
        json={
            "name": "Фонд «Помощь»",
            "email": "fond@example.com",
            "password": "Password123",
            "personal_data_consent": True,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["organization"]["name"] == "Фонд «Помощь»"
    assert body["organization"]["email"] == "fond@example.com"
    assert body["user"]["email"] == "fond@example.com"
    assert body["user"]["name"].startswith("Представитель ")

    user = (await session.execute(select(User).where(User.email == "fond@example.com"))).scalar_one()
    organization = (
        await session.execute(select(Organization).where(Organization.id == uuid.UUID(body["organization"]["id"])))
    ).scalar_one()
    membership = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization.id,
                OrganizationMember.user_id == user.id,
            )
        )
    ).scalar_one()

    assert membership.role == OrgMemberRole.REPRESENTATIVE
    assert membership.has_permission(OrgPermission.MANAGE_MEMBERS)


async def test_login_and_me(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Борис",
            "email": "boris@example.com",
            "password": "Password123",
            "personal_data_consent": True,
        },
    )

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "Boris@example.com", "password": "Password123"},
    )
    assert login.status_code == 200
    tokens = login.json()["tokens"]

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "boris@example.com"


async def test_login_wrong_password(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Борис",
            "email": "boris2@example.com",
            "password": "Password123",
            "personal_data_consent": True,
        },
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "boris2@example.com", "password": "WrongPassword"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Неверный email или пароль"


async def test_login_lockout_after_max_attempts(client: AsyncClient, session: AsyncSession) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Кира",
            "email": "kira@example.com",
            "password": "Password123",
            "personal_data_consent": True,
        },
    )

    for _ in range(settings.login_max_attempts):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "kira@example.com", "password": "WrongPassword"},
        )
        assert response.status_code == 401

    locked = await client.post(
        "/api/v1/auth/login",
        json={"email": "kira@example.com", "password": "Password123"},
    )
    assert locked.status_code == 429
    assert locked.json()["error"]["code"] == "too_many_requests"

    lockout = (
        await session.execute(select(AuthLockout).where(AuthLockout.identifier == "kira@example.com"))
    ).scalar_one()
    assert lockout.locked_until is not None
    assert lockout.locked_until > datetime.now(UTC)


async def test_refresh_rotates_token(client: AsyncClient, session: AsyncSession) -> None:
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Дима",
            "email": "dima@example.com",
            "password": "Password123",
            "personal_data_consent": True,
        },
    )
    old_refresh = register.json()["tokens"]["refresh_token"]

    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert refreshed.status_code == 200
    new_refresh = refreshed.json()["tokens"]["refresh_token"]
    assert new_refresh != old_refresh

    reuse = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert reuse.status_code == 401

    tokens = (await session.execute(select(RefreshToken))).scalars().all()
    assert sum(1 for token in tokens if token.revoked_at is None) == 1


async def test_logout_revokes_refresh_token(client: AsyncClient) -> None:
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Елена",
            "email": "elena@example.com",
            "password": "Password123",
            "personal_data_consent": True,
        },
    )
    refresh_token = register.json()["tokens"]["refresh_token"]

    logout = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert logout.status_code == 204

    refresh = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh.status_code == 401


async def test_access_token_cannot_be_used_as_refresh(client: AsyncClient) -> None:
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Фёдор",
            "email": "fedor@example.com",
            "password": "Password123",
            "personal_data_consent": True,
        },
    )
    access_token = register.json()["tokens"]["access_token"]

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert response.status_code == 401


async def test_blocked_user_cannot_login(client: AsyncClient, make_user) -> None:
    user = await make_user(email="blocked@example.com", is_active=False)

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "blocked@example.com", "password": "Password123"},
    )
    assert response.status_code == 401

    token = create_token(user.id, TokenType.ACCESS)
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 401


async def test_me_requires_authorization(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_organization_login_works_with_personal_account(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register/organization",
        json={
            "name": "Склад",
            "email": "sklad@example.com",
            "password": "Password123",
            "personal_data_consent": True,
        },
    )

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "sklad@example.com", "password": "Password123"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["email"] == "sklad@example.com"
