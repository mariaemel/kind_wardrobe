import io

from httpx import AsyncClient
from PIL import Image

from app.modules.listings.catalog import CATEGORIES, ListingStatus


def _png(name: str = "photo.png") -> tuple[str, bytes, str]:
    buffer = io.BytesIO()
    Image.new("RGB", (48, 48), (120, 80, 40)).save(buffer, format="PNG")
    return name, buffer.getvalue(), "image/png"


async def _create_listing(client: AsyncClient, headers: dict, **overrides) -> dict:
    data = {
        "title": "Куртка демисезонная",
        "description": "Тёплая куртка в хорошем состоянии",
        "category": "Одежда",
        "subcategory": "Верхняя одежда",
        "condition": "Хорошее",
        "transfer_type": "Бесплатно",
        "delivery_method": "Встреча",
    }
    data.update(overrides)
    files = [("photos", _png("1.png")), ("photos", _png("2.png"))]
    response = await client.post("/api/v1/listings", data=data, files=files, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def test_categories_match_tz(client: AsyncClient) -> None:
    response = await client.get("/api/v1/listings/categories")
    assert response.status_code == 200
    payload = {item["name"]: item["subcategories"] for item in response.json()["categories"]}
    assert payload == CATEGORIES
    assert "Дом и быт" in payload
    assert "Электроника" in payload
    assert payload["Другое"] == []


async def test_create_requires_city(client: AsyncClient, make_user, auth_header) -> None:
    user = await make_user()
    response = await client.post(
        "/api/v1/listings",
        headers=auth_header(user),
        data={
            "title": "Вещь",
            "description": "Описание",
            "category": "Другое",
            "condition": "Новое",
            "transfer_type": "Бесплатно",
            "delivery_method": "Встреча",
        },
        files=[("photos", _png())],
    )
    assert response.status_code == 400
    assert "город" in response.json()["error"]["message"].lower()


async def test_create_list_filter_and_owner_rights(client: AsyncClient, make_user, auth_header) -> None:
    owner = await make_user(city="Екатеринбург")
    stranger = await make_user(city="Серов")
    owner_headers = auth_header(owner)

    created = await _create_listing(client, owner_headers)
    assert created["status"] == "Опубликовано"
    assert created["city"] == "Екатеринбург"
    assert len(created["photos"]) == 2
    assert created["delivery_method"] == "Встреча"

    catalog = await client.get("/api/v1/listings", params={"city": "Екатеринбург", "q": "Куртка"})
    assert catalog.status_code == 200
    assert catalog.json()["total"] == 1
    assert catalog.json()["items"][0]["transfer_type"] == "Бесплатно"

    filtered = await client.get(
        "/api/v1/listings",
        params=[
            ("condition", "Хорошее"),
            ("category", "Одежда"),
            ("subcategory", "Верхняя одежда"),
            ("transfer_type", "Бесплатно"),
        ],
    )
    assert filtered.json()["total"] == 1

    mine = await client.get("/api/v1/listings/mine", headers=owner_headers)
    assert mine.json()["total"] == 1

    forbidden = await client.patch(
        f"/api/v1/listings/{created['id']}",
        headers=auth_header(stranger),
        json={"title": "Чужой заголовок"},
    )
    assert forbidden.status_code == 403

    updated = await client.patch(
        f"/api/v1/listings/{created['id']}",
        headers=owner_headers,
        json={"title": "Куртка обновлённая"},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Куртка обновлённая"

    unpublished = await client.post(f"/api/v1/listings/{created['id']}/unpublish", headers=owner_headers)
    assert unpublished.json()["status"] == "Снято с публикации"

    hidden = await client.get("/api/v1/listings")
    assert hidden.json()["total"] == 0

    owner_sees = await client.get(f"/api/v1/listings/{created['id']}", headers=owner_headers)
    assert owner_sees.status_code == 200

    stranger_hidden = await client.get(f"/api/v1/listings/{created['id']}", headers=auth_header(stranger))
    assert stranger_hidden.status_code == 404

    published = await client.post(f"/api/v1/listings/{created['id']}/publish", headers=owner_headers)
    assert published.json()["status"] == "Опубликовано"


async def test_exchange_requires_wishes(client: AsyncClient, make_user, auth_header) -> None:
    user = await make_user(city="Нижний Тагил")
    response = await client.post(
        "/api/v1/listings",
        headers=auth_header(user),
        data={
            "title": "Кроссовки",
            "description": "Размер 42",
            "category": "Обувь",
            "subcategory": "Спортивная",
            "condition": "Отличное",
            "transfer_type": "Обмен",
            "delivery_method": "Самовывоз",
        },
        files=[("photos", _png())],
    )
    assert response.status_code == 422


async def test_create_exchange_listing(client: AsyncClient, make_user, auth_header) -> None:
    user = await make_user(city="Первоуральск")
    listing = await _create_listing(
        client,
        auth_header(user),
        title="Плед",
        description="Тёплый плед",
        category="Дом и быт",
        subcategory="Текстиль",
        condition="Новое",
        transfer_type="Обмен",
        exchange_wishes="На книги",
        delivery_method="По договоренности",
    )
    assert listing["transfer_type"] == "Обмен"
    assert listing["exchange_wishes"] == "На книги"
    assert listing["subcategory"] == "Текстиль"


async def test_my_listings_status_filter(client: AsyncClient, make_user, auth_header) -> None:
    user = await make_user(city="Верхняя Пышма")
    headers = auth_header(user)
    listing = await _create_listing(client, headers)
    await client.post(f"/api/v1/listings/{listing['id']}/unpublish", headers=headers)

    published = await client.get(
        "/api/v1/listings/mine",
        headers=headers,
        params={"status": ListingStatus.PUBLISHED.value},
    )
    assert published.json()["total"] == 0

    unpublished = await client.get(
        "/api/v1/listings/mine",
        headers=headers,
        params={"status": ListingStatus.UNPUBLISHED.value},
    )
    assert unpublished.json()["total"] == 1
