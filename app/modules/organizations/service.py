import secrets
import uuid
from datetime import UTC, datetime

from fastapi import UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.media import delete_media_file, save_image
from app.modules.accounts.cities import validate_city
from app.modules.accounts.models import User
from app.modules.organizations.models import (
    InvitationStatus,
    Organization,
    OrganizationAcceptanceRules,
    OrganizationAddress,
    OrganizationInvitation,
    OrganizationMember,
    OrganizationStatus,
)
from app.modules.organizations.permissions import (
    OrgMemberRole,
    OrgPermission,
    permission_labels,
    validate_grantable,
)
from app.modules.organizations.schedule import format_working_hours, normalize_schedule
from app.modules.organizations.schemas import (
    AcceptanceRulesUpdateRequest,
    AddressUpsertRequest,
    InvitationCreateRequest,
    OrganizationContactsUpdateRequest,
    OrganizationCreateRequest,
    OrganizationGeneralUpdateRequest,
    OrganizationProfileUpdateRequest,
)


def _presence_cities(org: Organization) -> list[str]:
    cities = []
    for address in org.addresses:
        if address.city and address.city not in cities:
            cities.append(address.city)
    if org.city and org.city not in cities:
        cities.insert(0, org.city)
    return cities


def _acceptance_tags(org: Organization) -> list[str]:
    rules = org.acceptance_rules
    if rules is None or not rules.categories:
        return []
    tags: list[str] = []
    for item in rules.categories:
        if isinstance(item, dict) and item.get("name"):
            tags.append(str(item["name"]))
        elif isinstance(item, str):
            tags.append(item)
    return tags


def _rules_payload(org: Organization) -> dict:
    rules = org.acceptance_rules
    if rules is None:
        return {
            "categories": [],
            "conditions": [],
            "additional_requirements": None,
            "not_accepted": [],
        }
    categories = []
    for item in rules.categories or []:
        if isinstance(item, dict):
            categories.append(
                {
                    "name": item.get("name", ""),
                    "subcategories": list(item.get("subcategories") or []),
                }
            )
    return {
        "categories": categories,
        "conditions": list(rules.conditions or []),
        "additional_requirements": rules.additional_requirements,
        "not_accepted": list(rules.not_accepted or []),
    }


def _address_payload(address: OrganizationAddress) -> dict:
    return {
        "id": address.id,
        "title": address.title,
        "address_line": address.address_line,
        "city": address.city,
        "working_hours": address.working_hours,
        "schedule": address.schedule or {},
        "latitude": address.latitude,
        "longitude": address.longitude,
        "sort_order": address.sort_order,
    }


def to_card(org: Organization) -> dict:
    cities = _presence_cities(org)
    return {
        "id": org.id,
        "name": org.name,
        "city": cities[0] if cities else org.city,
        "cities": cities,
        "logo_url": org.logo_url,
        "description": org.description,
        "acceptance_tags": _acceptance_tags(org),
        "points_count": len(org.addresses),
    }


def to_detail(
    org: Organization,
    viewer_permissions: list[str] | None = None,
    viewer_role: str | None = None,
) -> dict:
    return {
        "id": org.id,
        "name": org.name,
        "city": org.city,
        "cities": _presence_cities(org),
        "logo_url": org.logo_url,
        "description": org.description,
        "about": org.about,
        "email": org.email,
        "phone": org.phone,
        "website": org.website,
        "social_links": list(org.social_links or []),
        "acceptance_tags": _acceptance_tags(org),
        "points_count": len(org.addresses),
        "acceptance_rules": _rules_payload(org),
        "addresses": [_address_payload(item) for item in org.addresses],
        "viewer_permissions": viewer_permissions or [],
        "viewer_role": viewer_role,
        "created_at": org.created_at,
        "updated_at": org.updated_at,
    }


async def get_organization(session: AsyncSession, organization_id: uuid.UUID) -> Organization | None:
    return await session.get(Organization, organization_id)


async def get_membership(
    session: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID
) -> OrganizationMember | None:
    result = await session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def _user_membership(session: AsyncSession, user_id: uuid.UUID) -> OrganizationMember | None:
    result = await session.execute(
        select(OrganizationMember)
        .options(selectinload(OrganizationMember.organization))
        .where(OrganizationMember.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _assert_can_create_organization(session: AsyncSession, user: User) -> None:
    membership = await _user_membership(session, user.id)
    if membership is not None:
        raise ConflictError("Пользователь уже связан с организацией")


async def _assert_can_join_organization(session: AsyncSession, user: User) -> None:
    membership = await _user_membership(session, user.id)
    if membership is not None:
        raise ConflictError("Пользователь уже связан с организацией")


async def _load_public_org(session: AsyncSession, organization_id: uuid.UUID) -> Organization:
    result = await session.execute(
        select(Organization)
        .options(
            selectinload(Organization.addresses),
            selectinload(Organization.acceptance_rules),
        )
        .where(
            Organization.id == organization_id,
            Organization.status == OrganizationStatus.ACTIVE,
        )
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise NotFoundError("Организация не найдена")
    return org


async def _sync_org_city(session: AsyncSession, org: Organization) -> None:
    await session.refresh(org, attribute_names=["addresses"])
    cities: list[str] = []
    for address in org.addresses:
        if address.city and address.city not in cities:
            cities.append(address.city)
    if cities:
        org.city = cities[0]
        session.add(org)


async def list_organizations(
    session: AsyncSession,
    *,
    q: str | None = None,
    city: list[str] | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Organization], int]:
    clauses = [Organization.status == OrganizationStatus.ACTIVE]
    if q:
        pattern = f"%{q.strip()}%"
        clauses.append(
            or_(
                Organization.name.ilike(pattern),
                Organization.description.ilike(pattern),
                Organization.about.ilike(pattern),
            )
        )
    if city:
        address_exists = (
            select(OrganizationAddress.id)
            .where(
                OrganizationAddress.organization_id == Organization.id,
                OrganizationAddress.city.in_(city),
            )
            .exists()
        )
        clauses.append(or_(Organization.city.in_(city), address_exists))

    total = await session.scalar(select(func.count()).select_from(Organization).where(*clauses))
    result = await session.execute(
        select(Organization)
        .options(
            selectinload(Organization.addresses),
            selectinload(Organization.acceptance_rules),
        )
        .where(*clauses)
        .order_by(Organization.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().unique().all()), int(total or 0)


async def list_map_points(
    session: AsyncSession,
    *,
    q: str | None = None,
    city: list[str] | None = None,
) -> list[dict]:
    orgs, _ = await list_organizations(session, q=q, city=city, page=1, page_size=1000)
    points: list[dict] = []
    for org in orgs:
        for address in org.addresses:
            if city and address.city not in city:
                continue
            points.append(
                {
                    "id": address.id,
                    "organization_id": org.id,
                    "organization_name": org.name,
                    "organization_logo_url": org.logo_url,
                    "title": address.title or address.address_line,
                    "address_line": address.address_line,
                    "city": address.city,
                    "working_hours": address.working_hours,
                    "latitude": address.latitude,
                    "longitude": address.longitude,
                }
            )
    return points


async def get_public_organization(
    session: AsyncSession, organization_id: uuid.UUID, viewer: User | None
) -> dict:
    org = await _load_public_org(session, organization_id)
    permissions: list[str] = []
    role = None
    if viewer is not None:
        membership = await get_membership(session, org.id, viewer.id)
        if membership is not None:
            permissions = sorted(permission.value for permission in membership.effective_permissions)
            role = membership.role.value
    return to_detail(org, permissions, role)


async def membership_status(session: AsyncSession, user: User) -> dict:
    membership = await _user_membership(session, user.id)
    if membership is None or membership.organization is None or not membership.organization.is_active:
        return {"has_organization": False, "action": "create", "organization": None}
    org = membership.organization
    return {
        "has_organization": True,
        "action": "manage",
        "organization": {
            "id": org.id,
            "name": org.name,
            "city": org.city,
            "logo_url": org.logo_url,
            "role": membership.role.value,
            "permissions": sorted(p.value for p in membership.effective_permissions),
            "action": "manage",
        },
    }


async def list_my_organizations(session: AsyncSession, user: User) -> list[dict]:
    status = await membership_status(session, user)
    if not status["has_organization"]:
        return []
    return [status["organization"]]


async def create_organization(
    session: AsyncSession, user: User, payload: OrganizationCreateRequest
) -> dict:
    await _assert_can_create_organization(session, user)
    org = Organization(name=payload.name, email=str(payload.email).lower())
    org.members.append(OrganizationMember(user_id=user.id, role=OrgMemberRole.REPRESENTATIVE))
    session.add(org)
    await session.commit()
    return await get_public_organization(session, org.id, user)


async def _require_permission(
    session: AsyncSession, organization_id: uuid.UUID, user: User, permission: OrgPermission
) -> Organization:
    org = await _load_public_org(session, organization_id)
    membership = await get_membership(session, organization_id, user.id)
    if membership is None or not membership.has_permission(permission):
        raise PermissionDeniedError("Недостаточно прав для выполнения действия")
    return org


async def update_general(
    session: AsyncSession,
    organization_id: uuid.UUID,
    user: User,
    payload: OrganizationGeneralUpdateRequest,
) -> dict:
    org = await _require_permission(session, organization_id, user, OrgPermission.EDIT_GENERAL_INFO)
    data = payload.model_dump(exclude_unset=True)
    if "city" in data:
        data["city"] = _validated_city(data["city"])
    for field, value in data.items():
        setattr(org, field, value)
    session.add(org)
    await session.commit()
    return await get_public_organization(session, org.id, user)


async def update_contacts(
    session: AsyncSession,
    organization_id: uuid.UUID,
    user: User,
    payload: OrganizationContactsUpdateRequest,
) -> dict:
    org = await _require_permission(session, organization_id, user, OrgPermission.EDIT_CONTACTS)
    data = payload.model_dump(exclude_unset=True)
    if "email" in data and data["email"] is not None:
        data["email"] = str(data["email"]).lower()
    for field, value in data.items():
        setattr(org, field, value)
    session.add(org)
    await session.commit()
    return await get_public_organization(session, org.id, user)


async def update_profile_page(
    session: AsyncSession,
    organization_id: uuid.UUID,
    user: User,
    payload: OrganizationProfileUpdateRequest,
) -> dict:
    org = await _load_public_org(session, organization_id)
    membership = await get_membership(session, organization_id, user.id)
    if membership is None:
        raise PermissionDeniedError("Недостаточно прав для выполнения действия")

    data = payload.model_dump(exclude_unset=True)
    general_fields = {"name", "description", "about", "website", "social_links"}
    contact_fields = {"phone", "email"}
    touching_general = bool(general_fields & data.keys())
    touching_contacts = bool(contact_fields & data.keys())
    if touching_general and not membership.has_permission(OrgPermission.EDIT_GENERAL_INFO):
        raise PermissionDeniedError("Недостаточно прав для редактирования основной информации")
    if touching_contacts and not membership.has_permission(OrgPermission.EDIT_CONTACTS):
        raise PermissionDeniedError("Недостаточно прав для редактирования контактов")
    if "email" in data and data["email"] is not None:
        data["email"] = str(data["email"]).lower()
    for field, value in data.items():
        setattr(org, field, value)
    session.add(org)
    await session.commit()
    return await get_public_organization(session, org.id, user)


async def update_logo(
    session: AsyncSession, organization_id: uuid.UUID, user: User, upload: UploadFile
) -> dict:
    org = await _require_permission(session, organization_id, user, OrgPermission.EDIT_GENERAL_INFO)
    previous = org.logo_url
    org.logo_url = await save_image(upload, folder=f"organizations/{org.id}")
    session.add(org)
    await session.commit()
    delete_media_file(previous)
    return await get_public_organization(session, org.id, user)


def _validated_city(value: str | None) -> str | None:
    try:
        return validate_city(value)
    except ValueError as exc:
        raise AppError(str(exc)) from exc


def _build_address(organization_id: uuid.UUID, item: AddressUpsertRequest, sort_order: int) -> OrganizationAddress:
    schedule = item.schedule.to_storage() if item.schedule is not None else normalize_schedule(None)
    working_hours = item.working_hours or format_working_hours(schedule)
    city = _validated_city(item.city) or item.city
    return OrganizationAddress(
        organization_id=organization_id,
        title=item.title or item.address_line,
        address_line=item.address_line,
        city=city,
        working_hours=working_hours,
        schedule=schedule,
        latitude=item.latitude,
        longitude=item.longitude,
        sort_order=item.sort_order if item.sort_order else sort_order,
    )


async def replace_addresses(
    session: AsyncSession,
    organization_id: uuid.UUID,
    user: User,
    addresses: list[AddressUpsertRequest],
) -> dict:
    org = await _require_permission(session, organization_id, user, OrgPermission.EDIT_ADDRESSES)
    org = await _load_public_org(session, org.id)
    for existing in list(org.addresses):
        await session.delete(existing)
    await session.flush()
    for index, item in enumerate(addresses):
        session.add(_build_address(org.id, item, index))
    await session.commit()
    org = await _load_public_org(session, org.id)
    await _sync_org_city(session, org)
    await session.commit()
    return await get_public_organization(session, org.id, user)


async def create_address(
    session: AsyncSession, organization_id: uuid.UUID, user: User, payload: AddressUpsertRequest
) -> dict:
    org = await _require_permission(session, organization_id, user, OrgPermission.EDIT_ADDRESSES)
    org = await _load_public_org(session, org.id)
    session.add(_build_address(org.id, payload, len(org.addresses)))
    await session.commit()
    org = await _load_public_org(session, org.id)
    await _sync_org_city(session, org)
    await session.commit()
    return await get_public_organization(session, org.id, user)


async def update_address(
    session: AsyncSession,
    organization_id: uuid.UUID,
    address_id: uuid.UUID,
    user: User,
    payload: AddressUpsertRequest,
) -> dict:
    await _require_permission(session, organization_id, user, OrgPermission.EDIT_ADDRESSES)
    address = await session.get(OrganizationAddress, address_id)
    if address is None or address.organization_id != organization_id:
        raise NotFoundError("Пункт приёма не найден")
    built = _build_address(organization_id, payload, payload.sort_order)
    address.title = built.title
    address.address_line = built.address_line
    address.city = built.city
    address.working_hours = built.working_hours
    address.schedule = built.schedule
    address.latitude = built.latitude
    address.longitude = built.longitude
    address.sort_order = built.sort_order
    session.add(address)
    await session.commit()
    org = await _load_public_org(session, organization_id)
    await _sync_org_city(session, org)
    await session.commit()
    return await get_public_organization(session, organization_id, user)


async def delete_address(
    session: AsyncSession, organization_id: uuid.UUID, address_id: uuid.UUID, user: User
) -> dict:
    await _require_permission(session, organization_id, user, OrgPermission.EDIT_ADDRESSES)
    address = await session.get(OrganizationAddress, address_id)
    if address is None or address.organization_id != organization_id:
        raise NotFoundError("Пункт приёма не найден")
    await session.delete(address)
    await session.commit()
    org = await _load_public_org(session, organization_id)
    await _sync_org_city(session, org)
    await session.commit()
    return await get_public_organization(session, organization_id, user)


async def update_acceptance_rules(
    session: AsyncSession,
    organization_id: uuid.UUID,
    user: User,
    payload: AcceptanceRulesUpdateRequest,
) -> dict:
    org = await _require_permission(session, organization_id, user, OrgPermission.EDIT_ACCEPTANCE_RULES)
    org = await _load_public_org(session, org.id)
    rules = org.acceptance_rules
    if rules is None:
        rules = OrganizationAcceptanceRules(organization_id=org.id)
        session.add(rules)
    rules.categories = [category.model_dump() for category in payload.categories]
    rules.conditions = payload.conditions
    rules.additional_requirements = payload.additional_requirements
    rules.not_accepted = payload.not_accepted
    session.add(rules)
    await session.commit()
    return await get_public_organization(session, org.id, user)


async def list_members(session: AsyncSession, organization_id: uuid.UUID, user: User) -> list[dict]:
    await _require_permission(session, organization_id, user, OrgPermission.MANAGE_MEMBERS)
    result = await session.execute(
        select(OrganizationMember)
        .options(selectinload(OrganizationMember.user))
        .where(OrganizationMember.organization_id == organization_id)
        .order_by(OrganizationMember.created_at.asc())
    )
    items = []
    for membership in result.scalars().all():
        if membership.role is OrgMemberRole.REPRESENTATIVE:
            permissions = sorted(p.value for p in membership.effective_permissions)
        else:
            permissions = sorted(membership.permissions or [])
        items.append(
            {
                "id": membership.id,
                "user_id": membership.user_id,
                "name": membership.user.name if membership.user else "",
                "email": membership.user.email if membership.user else "",
                "role": membership.role.value,
                "permissions": permissions,
                "permission_labels": permission_labels(permissions),
            }
        )
    return items


async def create_invitation(
    session: AsyncSession, organization_id: uuid.UUID, user: User, payload: InvitationCreateRequest
) -> dict:
    await _require_permission(session, organization_id, user, OrgPermission.MANAGE_MEMBERS)
    email = str(payload.email).lower()
    permissions = sorted(p.value for p in validate_grantable(payload.permissions))
    existing_user = await session.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        membership = await _user_membership(session, existing_user.id)
        if membership is not None:
            raise ConflictError("Пользователь уже связан с организацией")
    pending = await session.scalar(
        select(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == organization_id,
            OrganizationInvitation.email == email,
            OrganizationInvitation.status == InvitationStatus.PENDING,
        )
    )
    if pending is not None:
        raise ConflictError("Приглашение для этого email уже отправлено")
    invitation = OrganizationInvitation(
        organization_id=organization_id,
        email=email,
        invited_by_id=user.id,
        permissions=permissions,
        token=secrets.token_urlsafe(24),
        status=InvitationStatus.PENDING,
    )
    session.add(invitation)
    await session.commit()
    await session.refresh(invitation)
    return {
        "id": invitation.id,
        "email": invitation.email,
        "permissions": invitation.permissions,
        "permission_labels": permission_labels(invitation.permissions),
        "status": invitation.status.value,
        "token": invitation.token,
        "created_at": invitation.created_at,
    }


async def list_invitations(session: AsyncSession, organization_id: uuid.UUID, user: User) -> list[dict]:
    await _require_permission(session, organization_id, user, OrgPermission.MANAGE_MEMBERS)
    result = await session.execute(
        select(OrganizationInvitation)
        .where(
            OrganizationInvitation.organization_id == organization_id,
            OrganizationInvitation.status == InvitationStatus.PENDING,
        )
        .order_by(OrganizationInvitation.created_at.desc())
    )
    return [
        {
            "id": item.id,
            "email": item.email,
            "permissions": item.permissions,
            "permission_labels": permission_labels(item.permissions),
            "status": item.status.value,
            "token": item.token,
            "created_at": item.created_at,
        }
        for item in result.scalars().all()
    ]


async def revoke_invitation(
    session: AsyncSession, organization_id: uuid.UUID, invitation_id: uuid.UUID, user: User
) -> None:
    await _require_permission(session, organization_id, user, OrgPermission.MANAGE_MEMBERS)
    invitation = await session.get(OrganizationInvitation, invitation_id)
    if invitation is None or invitation.organization_id != organization_id:
        raise NotFoundError("Приглашение не найдено")
    invitation.status = InvitationStatus.REVOKED
    session.add(invitation)
    await session.commit()


async def accept_invitation(session: AsyncSession, token: str, user: User) -> dict:
    result = await session.execute(
        select(OrganizationInvitation).where(
            OrganizationInvitation.token == token,
            OrganizationInvitation.status == InvitationStatus.PENDING,
        )
    )
    invitation = result.scalar_one_or_none()
    if invitation is None:
        raise NotFoundError("Приглашение не найдено или уже использовано")
    if invitation.email.lower() != user.email.lower():
        raise PermissionDeniedError("Приглашение предназначено для другого email")
    await _assert_can_join_organization(session, user)
    session.add(
        OrganizationMember(
            organization_id=invitation.organization_id,
            user_id=user.id,
            role=OrgMemberRole.EMPLOYEE,
            permissions=list(invitation.permissions),
        )
    )
    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_at = datetime.now(UTC)
    session.add(invitation)
    await session.commit()
    return await get_public_organization(session, invitation.organization_id, user)


async def update_member_permissions(
    session: AsyncSession,
    organization_id: uuid.UUID,
    member_id: uuid.UUID,
    user: User,
    permissions: list[str],
) -> dict:
    await _require_permission(session, organization_id, user, OrgPermission.MANAGE_MEMBERS)
    membership = await session.get(OrganizationMember, member_id)
    if membership is None or membership.organization_id != organization_id:
        raise NotFoundError("Сотрудник не найден")
    if membership.role is OrgMemberRole.REPRESENTATIVE:
        raise ConflictError("Нельзя изменить права представителя организации")
    membership.permissions = sorted(p.value for p in validate_grantable(permissions))
    session.add(membership)
    await session.commit()
    items = await list_members(session, organization_id, user)
    return next(item for item in items if item["id"] == member_id)


async def remove_member(
    session: AsyncSession, organization_id: uuid.UUID, member_id: uuid.UUID, user: User
) -> None:
    await _require_permission(session, organization_id, user, OrgPermission.MANAGE_MEMBERS)
    membership = await session.get(OrganizationMember, member_id)
    if membership is None or membership.organization_id != organization_id:
        raise NotFoundError("Сотрудник не найден")
    if membership.role is OrgMemberRole.REPRESENTATIVE:
        raise ConflictError("Нельзя удалить представителя организации")
    await session.delete(membership)
    await session.commit()
