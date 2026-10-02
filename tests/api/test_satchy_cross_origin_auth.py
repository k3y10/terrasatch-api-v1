"""Cross-origin browser authentication contract for the standalone Satchy frontend."""

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.admin.security import hash_admin_password
from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.identity.models import Account, Membership, MembershipRole, Organization, User
from terrasatch.main import create_app

SATCHY_ORIGIN = "https://satchy.terrasatch.com"
API_ORIGIN = "https://api.terrasatch.com"


@pytest.mark.asyncio
async def test_satchy_origin_can_preflight_login_and_reuse_api_session(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(
        "terrasatch.workspace.routes.create_session_factory",
        lambda settings: factory,
    )

    async def limiter(*args, **kwargs):
        pass

    monkeypatch.setattr("terrasatch.workspace.routes.enforce_public_rate_limit", limiter)

    async with factory() as session:
        account = Account(name="Satchy browser auth account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="TerraSatch",
            slug="terrasatch",
        )
        session.add(organization)
        user = User(
            email="keaton@terrasatch.com",
            display_name="Keaton",
            enabled=True,
            password_hash=hash_admin_password("Satchy-cross-origin-test-password!"),
            credential_version=1,
        )
        session.add(user)
        await session.flush()
        session.add(
            Membership(
                organization_id=organization.id,
                user_id=user.id,
                role=MembershipRole.OWNER,
                enabled=True,
            )
        )
        await session.commit()
        organization_id = organization.id

    app = create_app(
        Settings(
            environment="production",
            api_base_url=API_ORIGIN,
            admin_session_secret="satchy-cross-origin-session-secret",
            cors_origins=[SATCHY_ORIGIN],
        )
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url=API_ORIGIN,
    ) as client:
        preflight = await client.options(
            "/api/v1/workspace/login",
            headers={
                "Origin": SATCHY_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-csrf-token",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == SATCHY_ORIGIN
        assert preflight.headers["access-control-allow-credentials"] == "true"
        allowed_headers = preflight.headers["access-control-allow-headers"].casefold()
        assert "content-type" in allowed_headers
        assert "x-csrf-token" in allowed_headers

        anonymous = await client.get(
            "/api/v1/workspace/session",
            headers={"Origin": SATCHY_ORIGIN},
        )
        assert anonymous.status_code == 200
        assert anonymous.json()["user"] is None
        assert anonymous.headers["access-control-allow-origin"] == SATCHY_ORIGIN
        assert anonymous.headers["access-control-allow-credentials"] == "true"
        cookie = anonymous.headers["set-cookie"].casefold()
        assert "secure" in cookie
        assert "samesite=lax" in cookie
        assert "domain=" not in cookie

        login = await client.post(
            "/api/v1/workspace/login",
            json={
                "email": "keaton@terrasatch.com",
                "password": "Satchy-cross-origin-test-password!",
            },
            headers={
                "Origin": SATCHY_ORIGIN,
                "X-CSRF-Token": anonymous.json()["csrf_token"],
            },
        )
        assert login.status_code == 200
        assert login.headers["access-control-allow-origin"] == SATCHY_ORIGIN
        assert login.headers["access-control-allow-credentials"] == "true"

        authenticated = await client.get(
            "/api/v1/workspace/session",
            headers={"Origin": SATCHY_ORIGIN},
        )
        assert authenticated.status_code == 200
        assert authenticated.json()["user"]["email"] == "keaton@terrasatch.com"
        assert authenticated.json()["organizations"] == [
            {
                "id": str(organization_id),
                "name": "TerraSatch",
                "role": "owner",
            }
        ]

    await engine.dispose()
