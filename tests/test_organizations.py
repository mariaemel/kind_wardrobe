import uuid

from httpx import AsyncClient

from app.modules.organizations.models import (
    Organization,
    OrganizationAcceptanceRules,
    OrganizationAddress,
    OrganizationMember,
)
from app.modules.organizations.permissions import OrgMemberRole, OrgPermission
from app.modules.organizations.schedule import normalize_schedule


WEEKDAY_SCHEDULE = normalize_schedule(
    {
        "monday": {"is_open": True, "from": "10:00", "to": "20:00"},
        "tuesday": {"is_open": True, "from": "10:00", "to": "20:00"},
        "wednesday": {"is_open": True, "from": "10:00", "to": "20:00"},
        "thursday": {"is_open": True, "from": "10:00", "to": "20:00"},
        "friday": {"is_open": True, "from": "10:00", "to": "20:00"},
        "saturday": {"is_open": True, "from": "11:00", "to": "18:00"},
        "sunday": {"is_open": False, "from": None, "to": None},
    }
)


async def _make_org(session, representative, **overrides) -> Organization:
    data = {
        "name": "Добрые вещи",
        "email": f"org-{uuid.uuid4().hex[:8]}@example.com",
        "phone": "+7 (343) 222-33-44",
        "city": "Екатеринбург",
        "description": "Помогаем семьям в трудной жизненной ситуации.",
        "about": "Мы работаем в Екатеринбурге более 5 лет.",
    }
    data.update(overrides)
    org = Organization(**data)
    org.members.append(
        OrganizationMember(user_id=representative.id, role=OrgMemberRole.REPRESENTATIVE)
    )
    org.addresses.append(
        OrganizationAddress(
            title="Центральный пункт приёма",
            address_line="ул. Ленина, 15",
            city="Екатеринбург",
            working_hours="Пн-Пт 10:00–20:00, Сб 11:00–18:00",
            schedule=WEEKDAY_SCHEDULE,
            latitude=56.838011,
            longitude=60.597465,
            sort_order=0,
        )
    )
    org.addresses.append(
        OrganizationAddress(
            title="Пункт на Уралмаше",
            address_line="ул. Победы, 42",
            city="Екатеринбург",
            working_hours="Вт-Сб 11:00–18:00",
            schedule=WEEKDAY_SCHEDULE,
            latitude=56.8885,
            longitude=60.6132,
            sort_order=1,
        )
    )
    org.acceptance_rules = OrganizationAcceptanceRules(
        categories=[
            {"name": "Одежда", "subcategories": ["Верхняя одежда", "Свитеры и толстовки"]},
            {"name": "Обувь", "subcategories": ["Зимняя"]},
            {"name": "Детские вещи", "subcategories": ["Игрушки"]},
        ],
        conditions=["Новое", "Отличное", "Хорошее"],
        additional_requirements="Вещи должны быть чистыми и сухими.",
        not_accepted=["Вещи с сильными загрязнениями"],
    )
    session.add(org)
    await session.commit()
    await session.refresh(org, attribute_names=["addresses", "acceptance_rules", "members"])
    return org


async def test_public_list_detail_and_map(client: AsyncClient, session, make_user) -> None:
    representative = await make_user(city="Екатеринбург")
    org = await _make_org(session, representative)

    listing = await client.get("/api/v1/organizations", params={"city": "Екатеринбург", "q": "Добрые"})
    assert listing.status_code == 200
    assert listing.json()["total"] >= 1
    card = next(item for item in listing.json()["items"] if item["id"] == str(org.id))
    assert card["points_count"] == 2
    assert "Одежда" in card["acceptance_tags"]
    assert "Екатеринбург" in card["cities"]

    detail = await client.get(f"/api/v1/organizations/{org.id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["name"] == "Добрые вещи"
    assert body["about"].startswith("Мы работаем")
    assert body["phone"] == "+7 (343) 222-33-44"
    assert len(body["addresses"]) == 2
    assert body["addresses"][0]["schedule"]["monday"]["is_open"] is True
    assert body["acceptance_rules"]["conditions"] == ["Новое", "Отличное", "Хорошее"]
    assert body["viewer_permissions"] == []

    points = await client.get("/api/v1/organizations/map-points", params={"city": "Екатеринбург"})
    assert points.status_code == 200
    assert points.json()["total"] >= 2
    assert any(item["organization_id"] == str(org.id) for item in points.json()["items"])


async def test_create_organization_from_personal_account(
    client: AsyncClient, make_user, auth_header
) -> None:
    user = await make_user(city="Екатеринбург", email="owner.create@example.com")

    status = await client.get("/api/v1/me/organization-status", headers=auth_header(user))
    assert status.status_code == 200
    assert status.json()["action"] == "create"

    created = await client.post(
        "/api/v1/organizations",
        headers=auth_header(user),
        json={"name": "Новая организация", "email": "org.new@example.com"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Новая организация"
    assert body["email"] == "org.new@example.com"
    assert OrgPermission.MANAGE_MEMBERS.value in body["viewer_permissions"]

    again = await client.post(
        "/api/v1/organizations",
        headers=auth_header(user),
        json={"name": "Вторая", "email": "org.second@example.com"},
    )
    assert again.status_code == 409

    status_after = await client.get("/api/v1/me/organization-status", headers=auth_header(user))
    assert status_after.json()["action"] == "manage"
    assert status_after.json()["organization"]["id"] == body["id"]


async def test_edit_requires_permissions(client: AsyncClient, session, make_user, auth_header) -> None:
    owner = await make_user(city="Екатеринбург")
    stranger = await make_user(city="Екатеринбург")
    employee = await make_user(city="Екатеринбург")
    org = await _make_org(session, owner)
    session.add(
        OrganizationMember(
            organization_id=org.id,
            user_id=employee.id,
            role=OrgMemberRole.EMPLOYEE,
            permissions=[OrgPermission.EDIT_CONTACTS.value],
        )
    )
    await session.commit()

    forbidden = await client.patch(
        f"/api/v1/organizations/{org.id}/general",
        headers=auth_header(stranger),
        json={"description": "Чужой текст"},
    )
    assert forbidden.status_code == 403

    employee_denied = await client.patch(
        f"/api/v1/organizations/{org.id}/general",
        headers=auth_header(employee),
        json={"description": "Нет прав на general"},
    )
    assert employee_denied.status_code == 403

    contacts = await client.patch(
        f"/api/v1/organizations/{org.id}/contacts",
        headers=auth_header(employee),
        json={"phone": "+7 (343) 111-22-33"},
    )
    assert contacts.status_code == 200
    assert contacts.json()["phone"] == "+7 (343) 111-22-33"

    updated = await client.patch(
        f"/api/v1/organizations/{org.id}/general",
        headers=auth_header(owner),
        json={"description": "Обновлённое описание"},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "Обновлённое описание"
    assert OrgPermission.EDIT_GENERAL_INFO.value in updated.json()["viewer_permissions"]

    profile = await client.patch(
        f"/api/v1/organizations/{org.id}/profile",
        headers=auth_header(owner),
        json={"about": "Расширенный блок «О нас»", "phone": "+7 (343) 999-00-11"},
    )
    assert profile.status_code == 200
    assert profile.json()["about"] == "Расширенный блок «О нас»"
    assert profile.json()["phone"] == "+7 (343) 999-00-11"

    mine = await client.get("/api/v1/me/organizations", headers=auth_header(owner))
    assert mine.status_code == 200
    assert any(item["id"] == str(org.id) for item in mine.json())


async def test_address_crud_and_acceptance_rules(
    client: AsyncClient, session, make_user, auth_header
) -> None:
    owner = await make_user(city="Екатеринбург")
    org = await _make_org(session, owner)
    address_id = org.addresses[0].id

    created = await client.post(
        f"/api/v1/organizations/{org.id}/addresses",
        headers=auth_header(owner),
        json={
            "address_line": "ул. Татищева, 88",
            "city": "Екатеринбург",
            "schedule": {
                "monday": {"is_open": True, "from": "12:00", "to": "20:00"},
                "tuesday": {"is_open": True, "from": "12:00", "to": "20:00"},
                "wednesday": {"is_open": True, "from": "12:00", "to": "20:00"},
                "thursday": {"is_open": True, "from": "12:00", "to": "20:00"},
                "friday": {"is_open": True, "from": "12:00", "to": "20:00"},
                "saturday": {"is_open": False, "from": None, "to": None},
                "sunday": {"is_open": False, "from": None, "to": None},
            },
            "latitude": 56.8458,
            "longitude": 60.5591,
        },
    )
    assert created.status_code == 201
    assert created.json()["points_count"] == 3
    new_address = next(
        item for item in created.json()["addresses"] if item["address_line"] == "ул. Татищева, 88"
    )
    assert "Пн-Пт 12:00–20:00" in new_address["working_hours"]

    patched = await client.patch(
        f"/api/v1/organizations/{org.id}/addresses/{address_id}",
        headers=auth_header(owner),
        json={
            "address_line": "ул. Ленина, 15А",
            "city": "Екатеринбург",
            "working_hours": "Пн-Пт 09:00–18:00",
            "latitude": 56.838011,
            "longitude": 60.597465,
        },
    )
    assert patched.status_code == 200
    assert any(item["address_line"] == "ул. Ленина, 15А" for item in patched.json()["addresses"])

    deleted = await client.delete(
        f"/api/v1/organizations/{org.id}/addresses/{new_address['id']}",
        headers=auth_header(owner),
    )
    assert deleted.status_code == 200
    assert deleted.json()["points_count"] == 2

    rules = await client.put(
        f"/api/v1/organizations/{org.id}/acceptance-rules",
        headers=auth_header(owner),
        json={
            "categories": [
                {
                    "name": "Одежда",
                    "subcategories": ["Верхняя одежда", "Платья и юбки"],
                },
                {"name": "Обувь", "subcategories": ["Зимняя", "Летняя"]},
            ],
            "conditions": ["Новое", "Отличное", "Хорошее"],
            "additional_requirements": "Чистые, сухие, пригодные к использованию",
            "not_accepted": ["Вещи с сильными загрязнениями"],
        },
    )
    assert rules.status_code == 200
    assert rules.json()["acceptance_rules"]["additional_requirements"].startswith("Чистые")
    assert len(rules.json()["acceptance_rules"]["categories"]) == 2


async def test_invite_accept_update_and_remove_member(
    client: AsyncClient, session, make_user, auth_header
) -> None:
    owner = await make_user(city="Екатеринбург", email="invite.owner@example.com")
    invitee = await make_user(city="Екатеринбург", email="invitee@example.com")
    other_owner = await make_user(city="Екатеринбург", email="other.owner@example.com")
    org = await _make_org(session, owner)
    await _make_org(session, other_owner, name="Чужая организация", email="other.org@example.com")

    invite = await client.post(
        f"/api/v1/organizations/{org.id}/invitations",
        headers=auth_header(owner),
        json={
            "email": invitee.email,
            "permissions": [
                OrgPermission.EDIT_GENERAL_INFO.value,
                OrgPermission.EDIT_ACCEPTANCE_RULES.value,
                OrgPermission.MANAGE_VOLUNTEER_TASKS.value,
                OrgPermission.REVIEW_VOLUNTEER_RESPONSES.value,
                OrgPermission.CONFIRM_TRANSFERS.value,
            ],
        },
    )
    assert invite.status_code == 201
    token = invite.json()["token"]
    assert invite.json()["status"] == "pending"

    pending = await client.get(
        f"/api/v1/organizations/{org.id}/invitations",
        headers=auth_header(owner),
    )
    assert pending.status_code == 200
    assert len(pending.json()["items"]) == 1

    blocked = await client.post(
        f"/api/v1/organization-invitations/{token}/accept",
        headers=auth_header(other_owner),
    )
    assert blocked.status_code == 403

    accepted = await client.post(
        f"/api/v1/organization-invitations/{token}/accept",
        headers=auth_header(invitee),
    )
    assert accepted.status_code == 200
    assert OrgPermission.CHAT.value in accepted.json()["viewer_permissions"]
    assert OrgPermission.EDIT_GENERAL_INFO.value in accepted.json()["viewer_permissions"]
    assert OrgPermission.CONFIRM_TRANSFERS.value in accepted.json()["viewer_permissions"]

    members = await client.get(
        f"/api/v1/organizations/{org.id}/members",
        headers=auth_header(owner),
    )
    assert members.status_code == 200
    employee = next(item for item in members.json()["items"] if item["email"] == invitee.email)
    assert employee["role"] == "employee"

    updated = await client.patch(
        f"/api/v1/organizations/{org.id}/members/{employee['id']}",
        headers=auth_header(owner),
        json={"permissions": [OrgPermission.CONFIRM_TRANSFERS.value]},
    )
    assert updated.status_code == 200
    assert updated.json()["permissions"] == [OrgPermission.CONFIRM_TRANSFERS.value]

    removed = await client.delete(
        f"/api/v1/organizations/{org.id}/members/{employee['id']}",
        headers=auth_header(owner),
    )
    assert removed.status_code == 204

    after = await client.get(
        f"/api/v1/organizations/{org.id}/members",
        headers=auth_header(owner),
    )
    assert all(item["email"] != invitee.email for item in after.json()["items"])

    recreate = await client.post(
        "/api/v1/organizations",
        headers=auth_header(invitee),
        json={"name": "Своя организация", "email": "own.org@example.com"},
    )
    assert recreate.status_code == 201
