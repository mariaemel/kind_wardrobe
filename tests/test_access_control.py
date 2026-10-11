import uuid

import pytest
from fastapi import APIRouter, Depends
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenType, create_token
from app.main import app
from app.models import OrganizationMember
from app.modules.accounts.dependencies import AdminUser
from app.modules.accounts.models import SystemRole
from app.modules.organizations.dependencies import require_org_permission
from app.modules.organizations.models import OrganizationStatus
from app.modules.organizations.permissions import OrgMemberRole, OrgPermission
from app.modules.organizations.service import get_membership

probe_router = APIRouter(prefix="/_test")


@probe_router.get("/organizations/{organization_id}/tasks")
async def manage_tasks_probe(
    member: OrganizationMember = Depends(require_org_permission(OrgPermission.MANAGE_VOLUNTEER_TASKS)),
) -> dict[str, str]:
    return {"role": member.role}


@probe_router.get("/admin")
async def admin_probe(_: AdminUser) -> dict[str, bool]:
    return {"ok": True}


app.include_router(probe_router)


def auth(user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(user_id, TokenType.ACCESS)}"}


@pytest.fixture
async def organization_setup(make_user, make_organization, session: AsyncSession):
    representative = await make_user()
    employee = await make_user()
    stranger = await make_user()
    organization = await make_organization(representative)
    session.add(OrganizationMember(organization_id=organization.id, user_id=employee.id, role=OrgMemberRole.EMPLOYEE))
    await session.commit()
    return organization, representative, employee, stranger


async def test_anonymous_request_is_rejected(client: AsyncClient, organization_setup) -> None:
    organization, *_ = organization_setup

    response = await client.get(f"/_test/organizations/{organization.id}/tasks")

    assert response.status_code == 401


async def test_refresh_token_is_not_accepted_as_access(client: AsyncClient, organization_setup) -> None:
    organization, representative, *_ = organization_setup
    token = create_token(representative.id, TokenType.REFRESH)

    response = await client.get(
        f"/_test/organizations/{organization.id}/tasks", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401


async def test_representative_has_access(client: AsyncClient, organization_setup) -> None:
    organization, representative, *_ = organization_setup

    response = await client.get(f"/_test/organizations/{organization.id}/tasks", headers=auth(representative.id))

    assert response.status_code == 200
    assert response.json() == {"role": "representative"}


async def test_employee_without_permission_is_forbidden(client: AsyncClient, organization_setup) -> None:
    organization, _, employee, _ = organization_setup

    response = await client.get(f"/_test/organizations/{organization.id}/tasks", headers=auth(employee.id))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


async def test_employee_with_granted_permission_has_access(
    client: AsyncClient, organization_setup, session: AsyncSession
) -> None:
    organization, _, employee, _ = organization_setup
    membership = await get_membership(session, organization.id, employee.id)
    assert membership is not None
    membership.permissions = [OrgPermission.MANAGE_VOLUNTEER_TASKS.value]
    await session.commit()

    response = await client.get(f"/_test/organizations/{organization.id}/tasks", headers=auth(employee.id))

    assert response.status_code == 200


async def test_user_from_outside_organization_is_forbidden(client: AsyncClient, organization_setup) -> None:
    organization, *_, stranger = organization_setup

    response = await client.get(f"/_test/organizations/{organization.id}/tasks", headers=auth(stranger.id))

    assert response.status_code == 403


async def test_blocked_organization_denies_management(
    client: AsyncClient, organization_setup, session: AsyncSession
) -> None:
    organization, representative, *_ = organization_setup
    organization.status = OrganizationStatus.BLOCKED
    session.add(organization)
    await session.commit()

    response = await client.get(f"/_test/organizations/{organization.id}/tasks", headers=auth(representative.id))

    assert response.status_code == 403


async def test_unknown_organization_returns_404(client: AsyncClient, organization_setup) -> None:
    _, representative, *_ = organization_setup

    response = await client.get(f"/_test/organizations/{uuid.uuid4()}/tasks", headers=auth(representative.id))

    assert response.status_code == 404


async def test_admin_endpoint_requires_admin_role(client: AsyncClient, make_user) -> None:
    user = await make_user()
    admin = await make_user(system_role=SystemRole.ADMIN)

    assert (await client.get("/_test/admin", headers=auth(user.id))).status_code == 403
    assert (await client.get("/_test/admin", headers=auth(admin.id))).status_code == 200


async def test_blocked_user_is_rejected(client: AsyncClient, make_user) -> None:
    admin = await make_user(system_role=SystemRole.ADMIN, is_active=False)

    assert (await client.get("/_test/admin", headers=auth(admin.id))).status_code == 401
