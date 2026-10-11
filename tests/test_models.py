import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Organization, OrganizationMember, User
from app.modules.accounts.models import SystemRole
from app.modules.organizations.permissions import OrgMemberRole, OrgPermission


async def test_user_defaults(make_user, session: AsyncSession) -> None:
    user = await make_user()
    await session.refresh(user)

    assert user.system_role == SystemRole.USER
    assert user.is_active is True
    assert user.is_admin is False
    assert user.created_at is not None


async def test_email_must_be_unique(make_user) -> None:
    await make_user(email="same@example.com")

    with pytest.raises(IntegrityError):
        await make_user(email="same@example.com")


async def test_representative_is_linked_to_organization(make_user, make_organization, session: AsyncSession) -> None:
    representative = await make_user()
    organization = await make_organization(representative)

    membership = (
        await session.execute(select(OrganizationMember).where(OrganizationMember.organization_id == organization.id))
    ).scalar_one()

    assert membership.user_id == representative.id
    assert membership.role == OrgMemberRole.REPRESENTATIVE
    assert membership.has_permission(OrgPermission.MANAGE_MEMBERS)


async def test_one_account_can_belong_to_several_organizations(
    make_user, make_organization, session: AsyncSession
) -> None:
    user = await make_user()
    other_representative = await make_user()
    await make_organization(user, name="Своя организация")
    foreign = await make_organization(other_representative, name="Чужая организация")
    session.add(
        OrganizationMember(
            organization_id=foreign.id,
            user_id=user.id,
            role=OrgMemberRole.EMPLOYEE,
            permissions=[OrgPermission.CONFIRM_TRANSFERS.value],
        )
    )
    await session.commit()

    memberships = (
        await session.execute(select(OrganizationMember).where(OrganizationMember.user_id == user.id))
    ).scalars().all()

    assert {m.role for m in memberships} == {OrgMemberRole.REPRESENTATIVE, OrgMemberRole.EMPLOYEE}


async def test_user_cannot_be_member_of_same_organization_twice(
    make_user, make_organization, session: AsyncSession
) -> None:
    representative = await make_user()
    organization = await make_organization(representative)
    session.add(
        OrganizationMember(organization_id=organization.id, user_id=representative.id, role=OrgMemberRole.EMPLOYEE)
    )

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_removing_employee_keeps_personal_account(
    make_user, make_organization, session: AsyncSession
) -> None:
    representative = await make_user()
    employee = await make_user()
    organization = await make_organization(representative)
    membership = OrganizationMember(organization_id=organization.id, user_id=employee.id, role=OrgMemberRole.EMPLOYEE)
    session.add(membership)
    await session.commit()

    await session.delete(membership)
    await session.commit()

    assert await session.get(User, employee.id) is not None
    assert await session.get(Organization, organization.id) is not None
