import io
import uuid

from httpx import AsyncClient
from PIL import Image


def _png(name: str = "photo.png") -> tuple[str, bytes, str]:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), (100, 110, 120)).save(buffer, format="PNG")
    return name, buffer.getvalue(), "image/png"


async def test_public_profile_and_listings(client: AsyncClient, make_user, auth_header) -> None:
    owner = await make_user(name="Анна", city="Екатеринбург", about="Отдаю вещи")
    other = await make_user(name="Иван", city="Серов")
    headers = auth_header(owner)

    created = await client.post(
        "/api/v1/listings",
        headers=headers,
        data={
            "title": "Свитер",
            "description": "Тёплый свитер",
            "category": "Одежда",
            "subcategory": "Свитеры и толстовки",
            "condition": "Отличное",
            "transfer_type": "Бесплатно",
            "delivery_method": "Встреча",
        },
        files=[("photos", _png())],
    )
    assert created.status_code == 201
    listing_id = created.json()["id"]

    unpublished = await client.post(
        "/api/v1/listings",
        headers=headers,
        data={
            "title": "Скрытая вещь",
            "description": "Не для каталога",
            "category": "Другое",
            "condition": "Новое",
            "transfer_type": "Бесплатно",
            "delivery_method": "Встреча",
        },
        files=[("photos", _png("hidden.png"))],
    )
    assert unpublished.status_code == 201
    await client.post(
        f"/api/v1/listings/{unpublished.json()['id']}/unpublish",
        headers=headers,
    )

    profile = await client.get(f"/api/v1/users/{owner.id}")
    assert profile.status_code == 200
    body = profile.json()
    assert body["id"] == str(owner.id)
    assert body["name"] == "Анна"
    assert body["city"] == "Екатеринбург"
    assert body["about"] == "Отдаю вещи"
    assert "email" not in body
    assert "system_role" not in body

    listings = await client.get(f"/api/v1/users/{owner.id}/listings")
    assert listings.status_code == 200
    payload = listings.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == listing_id
    assert payload["items"][0]["title"] == "Свитер"

    empty = await client.get(f"/api/v1/users/{other.id}/listings")
    assert empty.status_code == 200
    assert empty.json()["total"] == 0

    missing = await client.get(f"/api/v1/users/{uuid.uuid4()}")
    assert missing.status_code == 404
