from httpx import AsyncClient


async def test_health_reports_database_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


async def test_unknown_route_returns_unified_error(client: AsyncClient) -> None:
    response = await client.get("/api/v1/unknown")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"
