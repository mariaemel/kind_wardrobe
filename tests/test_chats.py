import io

from httpx import AsyncClient
from PIL import Image


def _png(name: str = "photo.png") -> tuple[str, bytes, str]:
    buffer = io.BytesIO()
    Image.new("RGB", (48, 48), (90, 120, 80)).save(buffer, format="PNG")
    return name, buffer.getvalue(), "image/png"


async def _create_listing(client: AsyncClient, headers: dict) -> dict:
    response = await client.post(
        "/api/v1/listings",
        headers=headers,
        data={
            "title": "Вязаный свитер молочного цвета",
            "description": "Тёплый свитер, размер S–M",
            "category": "Одежда",
            "subcategory": "Свитеры и толстовки",
            "condition": "Отличное",
            "transfer_type": "Обмен",
            "exchange_wishes": "Свитер или кардиган",
            "delivery_method": "Встреча",
        },
        files=[("photos", _png())],
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_chat_transfer_flow(client: AsyncClient, make_user, auth_header) -> None:
    owner = await make_user(name="Анна", city="Екатеринбург")
    participant = await make_user(name="Екатерина", city="Екатеринбург")
    stranger = await make_user(name="Анатолий", city="Серов")
    owner_headers = auth_header(owner)
    participant_headers = auth_header(participant)

    listing = await _create_listing(client, owner_headers)

    forbidden_own = await client.post(
        f"/api/v1/listings/{listing['id']}/chat", headers=owner_headers
    )
    assert forbidden_own.status_code == 409

    opened = await client.post(
        f"/api/v1/listings/{listing['id']}/chat", headers=participant_headers
    )
    assert opened.status_code == 201
    chat = opened.json()
    assert chat["owner"]["name"] == "Анна"
    assert chat["participant"]["name"] == "Екатерина"
    assert chat["listing"]["title"].startswith("Вязаный свитер")
    assert chat["can_start_transfer"] is False
    assert chat["transfer"] is None

    again = await client.post(
        f"/api/v1/listings/{listing['id']}/chat", headers=participant_headers
    )
    assert again.status_code == 200
    assert again.json()["id"] == chat["id"]

    stranger_denied = await client.get(
        f"/api/v1/me/chats/{chat['id']}", headers=auth_header(stranger)
    )
    assert stranger_denied.status_code == 403

    sent = await client.post(
        f"/api/v1/me/chats/{chat['id']}/messages",
        headers=participant_headers,
        json={"text": "Здравствуйте! Свитер ещё актуален?"},
    )
    assert sent.status_code == 201
    assert sent.json()["type"] == "text"

    owner_reply = await client.post(
        f"/api/v1/me/chats/{chat['id']}/messages",
        headers=owner_headers,
        json={"text": "Да, актуален."},
    )
    assert owner_reply.status_code == 201

    owner_chat = await client.get(f"/api/v1/me/chats/{chat['id']}", headers=owner_headers)
    assert owner_chat.status_code == 200
    assert owner_chat.json()["can_start_transfer"] is True

    participant_start = await client.post(
        f"/api/v1/me/chats/{chat['id']}/transfer/start", headers=participant_headers
    )
    assert participant_start.status_code == 403

    started = await client.post(
        f"/api/v1/me/chats/{chat['id']}/transfer/start", headers=owner_headers
    )
    assert started.status_code == 200
    transfer = started.json()
    assert transfer["status"] == "confirmation_pending"
    assert transfer["listing_status"] == "В процессе передачи"
    assert transfer["can_confirm"] is True

    catalog = await client.get("/api/v1/listings")
    assert catalog.json()["total"] == 0

    owner_confirm = await client.post(
        f"/api/v1/me/chats/{chat['id']}/transfer/confirm", headers=owner_headers
    )
    assert owner_confirm.status_code == 200
    assert owner_confirm.json()["status"] == "waiting_second_confirmation"
    assert owner_confirm.json()["owner_confirmed"] is True
    assert owner_confirm.json()["recipient_confirmed"] is False
    assert owner_confirm.json()["can_confirm"] is False

    recipient_view = await client.get(
        f"/api/v1/me/chats/{chat['id']}/transfer", headers=participant_headers
    )
    assert recipient_view.json()["can_confirm"] is True

    completed = await client.post(
        f"/api/v1/me/chats/{chat['id']}/transfer/confirm", headers=participant_headers
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["listing_status"] == "Передано"
    assert completed.json()["owner_confirmed"] is True
    assert completed.json()["recipient_confirmed"] is True

    messages = await client.get(
        f"/api/v1/me/chats/{chat['id']}/messages", headers=owner_headers
    )
    assert messages.status_code == 200
    assert any(item["type"] == "system" for item in messages.json()["items"])

    owner_history = await client.get("/api/v1/me/transfer-history", headers=owner_headers)
    assert owner_history.status_code == 200
    assert owner_history.json()["total"] == 1
    assert owner_history.json()["items"][0]["role"] == "owner"

    recipient_history = await client.get(
        "/api/v1/me/transfer-history", headers=participant_headers
    )
    assert recipient_history.json()["total"] == 1
    assert recipient_history.json()["items"][0]["role"] == "recipient"

    me = await client.get("/api/v1/auth/me", headers=owner_headers)
    assert me.json()["items_saved"] == 1

    chats = await client.get("/api/v1/me/chats", headers=owner_headers)
    assert chats.json()["total"] == 1
    assert chats.json()["items"][0]["other_user"]["name"] == "Екатерина"
    assert chats.json()["items"][0]["display_name"] == "Екатерина"
    assert chats.json()["items"][0]["has_unread"] in {True, False}


async def test_chat_unread_mark(client: AsyncClient, make_user, auth_header) -> None:
    owner = await make_user(name="Владелец", city="Екатеринбург")
    participant = await make_user(name="Участник", city="Екатеринбург")
    owner_headers = auth_header(owner)
    participant_headers = auth_header(participant)

    listing = await _create_listing(client, owner_headers)
    opened = await client.post(
        f"/api/v1/listings/{listing['id']}/chat", headers=participant_headers
    )
    chat_id = opened.json()["id"]

    await client.post(
        f"/api/v1/me/chats/{chat_id}/messages",
        headers=participant_headers,
        json={"text": "Здравствуйте!"},
    )

    owner_chats = await client.get("/api/v1/me/chats", headers=owner_headers)
    assert owner_chats.status_code == 200
    item = owner_chats.json()["items"][0]
    assert item["has_unread"] is True
    assert item["unread_count"] >= 1
    assert owner_chats.json()["unread_total"] >= 1

    await client.get(f"/api/v1/me/chats/{chat_id}/messages", headers=owner_headers)
    after_read = await client.get("/api/v1/me/chats", headers=owner_headers)
    assert after_read.json()["items"][0]["has_unread"] is False
    assert after_read.json()["items"][0]["unread_count"] == 0
    assert after_read.json()["unread_total"] == 0


async def test_cannot_chat_unpublished(client: AsyncClient, make_user, auth_header) -> None:
    owner = await make_user(city="Первоуральск")
    other = await make_user(city="Первоуральск")
    listing = await _create_listing(client, auth_header(owner))
    await client.post(f"/api/v1/listings/{listing['id']}/unpublish", headers=auth_header(owner))
    response = await client.post(
        f"/api/v1/listings/{listing['id']}/chat", headers=auth_header(other)
    )
    assert response.status_code == 409
