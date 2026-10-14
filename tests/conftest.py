import asyncio
import os
import tempfile
from collections.abc import AsyncIterator, Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

from dotenv import dotenv_values

_env_file = dotenv_values(".env") if os.path.exists(".env") else {}
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or _env_file.get("TEST_DATABASE_URL") or (
    "postgresql+asyncpg://kind_wardrobe:kind_wardrobe@127.0.0.1:5432/kind_wardrobe_test"
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-automated-tests-only-0123456789")
os.environ["MEDIA_ROOT"] = tempfile.mkdtemp(prefix="kind_wardrobe_media_")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import TokenType, create_token, hash_password
from app.main import app
from app.models import Base, Organization, OrganizationMember, User
from app.modules.organizations.permissions import OrgMemberRole


async def _recreate_schema() -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


async def _truncate_all() -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.exec_driver_sql(f"TRUNCATE {tables} RESTART IDENTITY CASCADE")
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def database_schema() -> None:
    asyncio.run(_recreate_schema())


@pytest.fixture(autouse=True)
async def clean_database() -> AsyncIterator[None]:
    yield
    await _truncate_all()


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as db_session:
        yield db_session


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http_client:
        yield http_client


UserFactory = Callable[..., Coroutine[Any, Any, User]]


@pytest.fixture
def make_user(session: AsyncSession) -> UserFactory:
    counter = 0

    async def factory(**overrides: Any) -> User:
        nonlocal counter
        counter += 1
        data: dict[str, Any] = {
            "email": f"user{counter}@example.com",
            "password_hash": hash_password("Password123"),
            "name": f"Пользователь {counter}",
            "personal_data_consent_at": datetime.now(UTC),
        }
        data.update(overrides)
        user = User(**data)
        session.add(user)
        await session.commit()
        return user

    return factory


@pytest.fixture
def auth_header() -> Callable[[User], dict[str, str]]:
    def factory(user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_token(user.id, TokenType.ACCESS)}"}

    return factory


@pytest.fixture
def make_organization(session: AsyncSession) -> Callable[..., Coroutine[Any, Any, Organization]]:
    async def factory(representative: User, **overrides: Any) -> Organization:
        data: dict[str, Any] = {"name": "Фонд «Добро»", "email": "fond@example.com"}
        data.update(overrides)
        organization = Organization(**data)
        organization.members.append(
            OrganizationMember(user_id=representative.id, role=OrgMemberRole.REPRESENTATIVE)
        )
        session.add(organization)
        await session.commit()
        return organization

    return factory
