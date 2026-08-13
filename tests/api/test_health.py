from datetime import UTC, datetime
from re import search

import httpx
import pytest
from fastapi import FastAPI

from terrasatch.admin.security import generate_session_secret, hash_admin_password
from terrasatch.api.schemas import DependencyStatus, HealthResponse
from terrasatch.config import Settings
from terrasatch.errors import InvalidConfiguration
from terrasatch.main import create_app


def make_settings() -> Settings:
    return Settings(
        environment="local",
        deployment_name="test",
        api_base_url="http://testserver",
        cors_origins=["https://client.example"],
    )


@pytest.mark.asyncio
async def test_liveness_includes_request_id_and_configured_cors() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/health/live",
            headers={"Origin": "https://client.example", "X-Request-ID": "test-request"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.headers["x-request-id"] == "test-request"
    assert response.headers["access-control-allow-origin"] == "https://client.example"


@pytest.mark.asyncio
async def test_readiness_returns_503_when_dependency_report_is_unhealthy(monkeypatch) -> None:
    application = create_app(make_settings())

    async def unhealthy_readiness(_settings: Settings) -> HealthResponse:
        return HealthResponse(
            status="unhealthy",
            environment="local",
            deployment="test",
            version="0.1.0",
            timestamp=datetime.now(UTC),
            dependencies=[DependencyStatus(name="database", status="unhealthy")],
        )

    monkeypatch.setattr("terrasatch.main.check_readiness", unhealthy_readiness)
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json()["dependencies"][0]["name"] == "database"


@pytest.mark.asyncio
async def test_domain_errors_use_the_public_error_schema() -> None:
    application: FastAPI = create_app(make_settings())

    @application.get("/test/error")
    async def raise_configuration_error() -> None:
        raise InvalidConfiguration("Channel profile is invalid", details={"field": "profile"})

    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/test/error", headers={"X-Request-ID": "schema-test"})

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "invalid_configuration",
            "message": "Channel profile is invalid",
            "request_id": "schema-test",
            "details": {"field": "profile"},
        }
    }


@pytest.mark.asyncio
async def test_protected_endpoint_rejects_missing_bearer_token() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Bearer token required"


@pytest.mark.asyncio
async def test_public_reference_lists_implemented_routes_and_common_errors() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/reference")

    assert response.status_code == 200
    assert any(item["path"] == "/health/ready" for item in response.json()["endpoints"])
    assert any(
        item["method"] == "POST" and item["path"] == "/api/v1/sites"
        for item in response.json()["endpoints"]
    )
    assert any(item["http_status"] == 503 for item in response.json()["common_errors"])


@pytest.mark.asyncio
async def test_admin_quality_requires_a_bearer_token() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/admin/quality")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_configured_admin_can_log_in_with_a_csrf_protected_form() -> None:
    application = create_app(
        Settings(
            environment="local",
            deployment_name="test",
            api_base_url="http://testserver",
            admin_email="admin@example.com",
            admin_password_hash=hash_admin_password("a-secure-admin-password"),
            admin_session_secret=generate_session_secret(),
        )
    )
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        login_form = await client.get("/admin/login")
        csrf_token = search(r'name=csrf_token value="([^"]+)"', login_form.text)
        response = await client.post(
            "/admin/login",
            data={
                "email": "admin@example.com",
                "password": "a-secure-admin-password",
                "csrf_token": csrf_token.group(1) if csrf_token else "",
            },
        )

    assert login_form.status_code == 200
    assert csrf_token is not None
    assert response.status_code == 303
    assert response.headers["location"] == "/admin"