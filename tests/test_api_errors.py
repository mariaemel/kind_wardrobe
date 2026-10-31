from httpx import AsyncClient


async def test_validation_error_has_unified_shape(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "",
            "email": "not-an-email",
            "password": "short",
            "personal_data_consent": False,
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == "Проверьте корректность данных"
    assert isinstance(body["error"]["details"], list)
    assert body["error"]["details"]
    for item in body["error"]["details"]:
        assert "field" in item
        assert "message" in item
        assert not item["field"].startswith("body.")


async def test_register_rejects_short_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Анна",
            "email": "shortpass@example.com",
            "password": "1234567",
            "personal_data_consent": True,
        },
    )

    assert response.status_code == 422
    messages = [item["message"] for item in response.json()["error"]["details"]]
    assert any("8" in message for message in messages)


async def test_profile_patch_requires_fields(client: AsyncClient, make_user, auth_header) -> None:
    user = await make_user()
    response = await client.patch("/api/v1/profile/me", headers=auth_header(user), json={})

    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert any("хотя бы одно поле" in item["message"] for item in details)


async def test_auth_me_matches_profile_shape(client: AsyncClient, make_user, auth_header) -> None:
    user = await make_user(city="Серов", about="Тест")
    headers = auth_header(user)

    auth_me = await client.get("/api/v1/auth/me", headers=headers)
    profile_me = await client.get("/api/v1/profile/me", headers=headers)

    assert auth_me.status_code == 200
    assert profile_me.status_code == 200
    assert set(auth_me.json().keys()) == set(profile_me.json().keys())
    assert auth_me.json()["id"] == profile_me.json()["id"]
    assert "items_saved" in auth_me.json()
    assert "system_role" in auth_me.json()
