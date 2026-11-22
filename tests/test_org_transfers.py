import io
import uuid

from httpx import AsyncClient
from PIL import Image

from app.modules.organizations.models import (
    Organization,
    OrganizationAcceptanceRules,
    OrganizationAddress,
    OrganizationMember,
)
from app.modules.organizations.permissions import OrgMemberRole, OrgPermission


def _png(name: str = "photo.png") -> tuple[str, bytes, str]:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), (100, 80, 60)).save(buffer, format="PNG")
    return name, buffer.getvalue(), "image/png"


async def _create_listing(client: AsyncClient, headers: dict, **overrides) -> dict:
    data = {
        "title": "Детские книги",
        "description": "Набор книг в хорошем состоянии",
        "category": "Детские вещи",
        "subcategory": "Детские книги",
        "condition": "Хорошее",
        "transfer_type": "Бесплатно",
        "delivery_method": "Встреча",
    }
    data.update(overrides)
    response = await client.post(
        "/api/v1/listings",
        headers=headers,
        data=data,
        files=[("photos", _png())],
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _make_org(session, representative, **overrides) -> Organization:
    data = {
        "name": "Добрые вещи",
        "email": f"org-{uuid.uuid4().hex[:8]}@example.com",
        "phone": "+7 (343) 222-33-44",
        "city": "Екатеринбург",
        "description": "Помогаем вещам находить новых хозяев",
    }
    data.update(overrides)
    org = Organization(**data)
    org.members.append(
        OrganizationMember(user_id=representative.id, role=OrgMemberRole.REPRESENTATIVE)
    )
    org.addresses.append(
        OrganizationAddress(
            title="Центральный",
            address_line="ул. Ленина, 15",
            city="Екатеринбург",
            working_hours="Пн-Пт 12:00–20:00",
            schedule={},
            latitude=56.838011,
            longitude=60.597465,
            sort_order=0,
        )
    )
    org.acceptance_rules = OrganizationAcceptanceRules(
        categories=[
            {"name": "Детские вещи", "subcategories": ["Детские книги", "Игрушки"]},
            {"name": "Одежда", "subcategories": ["Верхняя одежда"]},
        ],
        conditions=["Новое", "Отличное", "Хорошее"],
        additional_requirements="Чистые и сухие",
        not_accepted=["Сильно загрязнённые вещи"],
    )
    session.add(org)
    await session.commit()
    await session.refresh(org, attribute_names=["addresses", "acceptance_rules", "members"])
    return org


async def test_user_to_organization_transfer_flow(
    client: AsyncClient, session, make_user, auth_header
) -> None:
    donor = await make_user(city="Екатеринбург", name="Мария")
    representative = await make_user(city="Екатеринбург", name="Представитель")
    staff = await make_user(city="Екатеринбург", name="Сотрудник")
    donor_headers = auth_header(donor)
    rep_headers = auth_header(representative)
    staff_headers = auth_header(staff)

    org = await _make_org(session, representative)
    session.add(
        OrganizationMember(
            organization_id=org.id,
            user_id=staff.id,
            role=OrgMemberRole.EMPLOYEE,
            permissions=[OrgPermission.CHAT.value],
        )
    )
    await session.commit()
    address_id = org.addresses[0].id

    listing = await _create_listing(client, donor_headers)
    unsuitable = await _create_listing(
        client,
        donor_headers,
        title="Смартфон",
        category="Электроника",
        subcategory="Телефоны и аксессуары",
        condition="Новое",
    )

    suitable_orgs = await client.get(
        f"/api/v1/listings/{listing['id']}/suitable-organizations",
        headers=donor_headers,
    )
    assert suitable_orgs.status_code == 200
    assert any(item["id"] == str(org.id) for item in suitable_orgs.json()["items"])

    suitable_listings = await client.get(
        f"/api/v1/organizations/{org.id}/suitable-listings",
        headers=donor_headers,
    )
    assert suitable_listings.status_code == 200
    listing_ids = {item["id"] for item in suitable_listings.json()["items"]}
    assert listing["id"] in listing_ids
    assert unsuitable["id"] not in listing_ids

    created = await client.post(
        f"/api/v1/organizations/{org.id}/transfers",
        headers=donor_headers,
        json={"listing_id": listing["id"], "address_id": str(address_id)},
    )
    assert created.status_code == 201, created.text
    chat = created.json()
    assert chat["organization"]["name"] == "Добрые вещи"
    assert chat["transfer"]["kind"] == "organization"
    assert chat["transfer"]["address"]["address_line"] == "ул. Ленина, 15"
    assert chat["listing"]["status"] == "В процессе передачи"
    chat_id = chat["id"]

    before = await client.get("/api/v1/auth/me", headers=donor_headers)
    assert before.json()["items_transferred"] == 0
    assert before.json()["items_received"] == 0

    donor_confirm = await client.post(
        f"/api/v1/me/chats/{chat_id}/transfer/confirm",
        headers=donor_headers,
    )
    assert donor_confirm.status_code == 200
    assert donor_confirm.json()["owner_confirmed"] is True
    assert donor_confirm.json()["organization_confirmed"] is False
    assert donor_confirm.json()["status"] == "waiting_second_confirmation"

    history_mid = await client.get("/api/v1/me/transfer-history", headers=donor_headers)
    assert history_mid.json()["total"] == 0

    staff_denied = await client.post(
        f"/api/v1/me/chats/{chat_id}/transfer/confirm",
        headers=staff_headers,
    )
    assert staff_denied.status_code == 403

    org_confirm = await client.post(
        f"/api/v1/me/chats/{chat_id}/transfer/confirm",
        headers=rep_headers,
    )
    assert org_confirm.status_code == 200
    assert org_confirm.json()["status"] == "completed"
    assert org_confirm.json()["organization_confirmed"] is True
    assert org_confirm.json()["listing_status"] == "Передано"

    history = await client.get(
        "/api/v1/me/transfer-history",
        headers=donor_headers,
        params={"filter": "to_organizations"},
    )
    assert history.status_code == 200
    assert history.json()["total"] == 1
    item = history.json()["items"][0]
    assert item["status_label"] == "Передано организации"
    assert item["counterpart_name"] == "Добрые вещи"

    me = await client.get("/api/v1/auth/me", headers=donor_headers)
    assert me.json()["items_transferred"] == 1
    assert me.json()["items_received"] == 0
    assert me.json()["items_saved"] == 1

    org_transfers = await client.get(
        f"/api/v1/organizations/{org.id}/transfers",
        headers=rep_headers,
    )
    assert org_transfers.status_code == 200
    assert org_transfers.json()["total"] == 1
    assert org_transfers.json()["items"][0]["status_label"] == "Передача завершена"

    chats = await client.get("/api/v1/me/chats", headers=donor_headers)
    assert chats.json()["items"][0]["other_organization"]["name"] == "Добрые вещи"
    assert chats.json()["items"][0]["display_name"] == "Добрые вещи"
