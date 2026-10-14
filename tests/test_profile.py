import io
from pathlib import Path

from httpx import AsyncClient
from PIL import Image

from app.core.config import get_settings
from app.modules.accounts.cities import ALLOWED_CITIES


def _png_bytes(color: tuple[int, int, int] = (20, 180, 80)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buffer, format="PNG")
    return buffer.getvalue()


async def test_list_cities(client: AsyncClient) -> None:
    response = await client.get("/api/v1/cities")

    assert response.status_code == 200
    cities = response.json()["cities"]
    assert cities == [
        "Екатеринбург",
        "Нижний Тагил",
        "Каменск-Уральский",
        "Первоуральск",
        "Серов",
        "Новоуральск",
        "Верхняя Пышма",
    ]
    assert set(cities) == ALLOWED_CITIES


async def test_get_profile_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/profile/me")
    assert response.status_code == 401


async def test_get_and_update_profile(client: AsyncClient, make_user, auth_header) -> None:
    user = await make_user()

    me = await client.get("/api/v1/profile/me", headers=auth_header(user))
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == user.email
    assert body["name"] == user.name
    assert body["city"] is None
    assert body["items_saved"] == 0

    updated = await client.patch(
        "/api/v1/profile/me",
        headers=auth_header(user),
        json={
            "name": " Анна ",
            "city": "Екатеринбург",
            "about": " Люблю обмениваться вещами ",
        },
    )
    assert updated.status_code == 200
    data = updated.json()
    assert data["name"] == "Анна"
    assert data["city"] == "Екатеринбург"
    assert data["about"] == "Люблю обмениваться вещами"


async def test_update_profile_rejects_unknown_city(client: AsyncClient, make_user, auth_header) -> None:
    user = await make_user()

    response = await client.patch(
        "/api/v1/profile/me",
        headers=auth_header(user),
        json={"city": "Москва"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_upload_and_delete_avatar(client: AsyncClient, make_user, auth_header) -> None:
    user = await make_user()
    png = _png_bytes()

    upload = await client.post(
        "/api/v1/profile/me/avatar",
        headers=auth_header(user),
        files={"file": ("avatar.png", png, "image/png")},
    )
    assert upload.status_code == 200
    avatar_url = upload.json()["avatar_url"]
    assert avatar_url.startswith("/media/avatars/")

    media_path = Path(get_settings().media_root) / avatar_url.removeprefix("/media/")
    assert media_path.is_file()

    fetched = await client.get(avatar_url)
    assert fetched.status_code == 200
    assert fetched.content[:8] == png[:8]

    deleted = await client.delete("/api/v1/profile/me/avatar", headers=auth_header(user))
    assert deleted.status_code == 200
    assert deleted.json()["avatar_url"] is None
    assert not media_path.exists()


async def test_upload_avatar_rejects_non_image(client: AsyncClient, make_user, auth_header) -> None:
    user = await make_user()

    response = await client.post(
        "/api/v1/profile/me/avatar",
        headers=auth_header(user),
        files={"file": ("note.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_image"


async def test_user_cannot_use_another_users_token_fields(
    client: AsyncClient, make_user, auth_header
) -> None:
    owner = await make_user(name="Владелец")
    stranger = await make_user(name="Чужой")

    response = await client.patch(
        "/api/v1/profile/me",
        headers=auth_header(stranger),
        json={"name": "Попытка чужого имени"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(stranger.id)
    assert response.json()["name"] == "Попытка чужого имени"

    owner_profile = await client.get("/api/v1/profile/me", headers=auth_header(owner))
    assert owner_profile.json()["name"] == "Владелец"
