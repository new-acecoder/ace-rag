from fastapi.testclient import TestClient

from app.api import health
from app.core.errors import ServiceUnavailableError
from app.main import create_app


def test_liveness_health() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": None}


def test_postgres_health_uses_uniform_service_error(monkeypatch) -> None:
    async def unavailable(_: object) -> None:
        raise ServiceUnavailableError("PostgreSQL")

    monkeypatch.setattr(health, "check_postgres", unavailable)
    client = TestClient(create_app())

    response = client.get("/api/v1/health/postgres")

    assert response.status_code == 503
    assert response.json() == {
        "code": "SERVICE_UNAVAILABLE",
        "message": "PostgreSQL 服务不可用",
    }


def test_unknown_api_route_uses_uniform_error() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/not-found")

    assert response.status_code == 404
    assert response.json() == {
        "code": "ROUTE_NOT_FOUND",
        "message": "接口不存在",
    }
