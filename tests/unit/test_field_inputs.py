"""Garmin inReach and native mobile field input regression coverage."""

from __future__ import annotations

from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.errors import AuthenticationFailed
from terrasatch.field_inputs.schemas import GarminIpcPayload, MobileObservationRequest
from terrasatch.field_inputs.service import (
    authenticate_garmin_connection,
    ingest_garmin_payload,
    ingest_mobile_observation,
)
from terrasatch.identity.models import Account, Organization, Site, User
from terrasatch.integrations.crypto import encrypt_payload
from terrasatch.integrations.models import (
    IntegrationConnection,
    IntegrationCredential,
    IntegrationStatus,
)


def _settings() -> Settings:
    return Settings(
        intelligence_provider="deterministic",
        integration_encryption_key=SecretStr(Fernet.generate_key().decode("ascii")),
    )


@pytest.mark.asyncio
async def test_garmin_event_feeds_canonical_pipeline_and_retries_are_idempotent() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as database:
        await database.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = _settings()

    async with factory() as session:
        account = Account(name="Garmin field account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Garmin field org",
            slug=f"garmin-field-{uuid4().hex[:8]}",
        )
        session.add(organization)
        await session.flush()
        site = Site(
            organization_id=organization.id,
            name="Wasatch field site",
            slug=f"wasatch-{uuid4().hex[:8]}",
        )
        session.add(site)
        await session.flush()

        connection = IntegrationConnection(
            organization_id=organization.id,
            provider="garmin",
            scope_type="organization",
            display_name="Garmin inReach",
            status=IntegrationStatus.CONNECTED.value,
            configuration={
                "site_id": str(site.id),
                "allowed_imeis": ["100000000000001"],
            },
            enabled=True,
        )
        session.add(connection)
        await session.flush()

        payload = GarminIpcPayload.model_validate(
            {
                "Version": "4.0",
                "Events": [
                    {
                        "imei": "100000000000001",
                        "messageCode": 3,
                        "freeText": "Shooting cracks below Cardiff Bowl.",
                        "timeStamp": 1789992000000,
                        "transportMode": "Satellite",
                        "point": {
                            "latitude": 40.588,
                            "longitude": -111.655,
                            "altitude": 2920,
                            "gpsFix": 2,
                            "course": 45,
                            "speed": 2,
                        },
                        "status": {
                            "autonomous": 1,
                            "lowBattery": 0,
                            "intervalChange": 0,
                            "resetDetected": 0,
                        },
                    }
                ],
            }
        )

        first = await ingest_garmin_payload(
            session,
            settings,
            connection=connection,
            payload=payload,
        )
        await session.commit()
        assert len(first.transmissions) == 1
        assert first.duplicates == 0
        transmission = first.transmissions[0]
        assert transmission.source_type == "garmin_inreach"
        assert transmission.source_message_id.startswith(
            "garmin:100000000000001:1789992000000:3:"
        )
        assert transmission.rf_metadata["source_type"] == "garmin_inreach"
        assert transmission.rf_metadata["garmin"]["transport_mode"] == "Satellite"
        for event in first.events:
            assert event.latitude == 40.588
            assert event.longitude == -111.655
            assert event.data["source_point"]["provider"] == "garmin_inreach"

        second = await ingest_garmin_payload(
            session,
            settings,
            connection=connection,
            payload=payload,
        )
        await session.commit()
        assert second.duplicates == 1
        assert second.transmissions[0].id == transmission.id

    await engine.dispose()


@pytest.mark.asyncio
async def test_garmin_static_token_is_encrypted_and_constant_time_checked() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as database:
        await database.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = _settings()

    async with factory() as session:
        account = Account(name="Garmin auth account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Garmin auth org",
            slug=f"garmin-auth-{uuid4().hex[:8]}",
        )
        session.add(organization)
        await session.flush()
        connection = IntegrationConnection(
            organization_id=organization.id,
            provider="garmin",
            scope_type="organization",
            display_name="Garmin inReach",
            status=IntegrationStatus.CONNECTED.value,
            configuration={"site_id": str(uuid4()), "allowed_imeis": []},
            enabled=True,
        )
        session.add(connection)
        await session.flush()
        encrypted = encrypt_payload(
            settings,
            {"static_token": "garmin-shared-secret"},
        )
        assert "garmin-shared-secret" not in encrypted
        session.add(
            IntegrationCredential(
                organization_id=organization.id,
                connection_id=connection.id,
                key_id=settings.integration_encryption_key_id,
                encrypted_payload=encrypted,
            )
        )
        await session.flush()

        await authenticate_garmin_connection(
            session,
            settings,
            connection=connection,
            provided_token="garmin-shared-secret",
        )
        with pytest.raises(AuthenticationFailed):
            await authenticate_garmin_connection(
                session,
                settings,
                connection=connection,
                provided_token="wrong-secret",
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_mobile_observation_feeds_same_pipeline_with_location_and_idempotency() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as database:
        await database.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = _settings()

    async with factory() as session:
        account = Account(name="Mobile field account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Mobile field org",
            slug=f"mobile-field-{uuid4().hex[:8]}",
        )
        user = User(
            email=f"{uuid4().hex}@example.com",
            display_name="Field User",
            enabled=True,
        )
        session.add_all([organization, user])
        await session.flush()
        site = Site(
            organization_id=organization.id,
            name="Mobile field site",
            slug=f"mobile-site-{uuid4().hex[:8]}",
        )
        session.add(site)
        await session.flush()

        payload = MobileObservationRequest(
            site_id=site.id,
            client_message_id="phone-observation-001",
            text="Recent avalanche debris across the skin track.",
            latitude=40.59,
            longitude=-111.66,
            altitude_m=2875,
            accuracy_m=8,
            source_kind="photo_note",
            media_ids=["photo-local-001"],
        )

        first = await ingest_mobile_observation(
            session,
            settings,
            organization_id=organization.id,
            user_id=user.id,
            payload=payload,
        )
        await session.commit()
        transmission, _transcript, events, duplicate = first
        assert duplicate is False
        assert transmission.source_type == "terrasatch_mobile"
        assert transmission.source_message_id == (
            f"mobile:{user.id}:phone-observation-001"
        )
        assert transmission.rf_metadata["mobile"]["source_kind"] == "photo_note"
        assert transmission.rf_metadata["mobile"]["media_ids"] == ["photo-local-001"]
        for event in events:
            assert event.latitude == 40.59
            assert event.longitude == -111.66
            assert event.data["source_point"]["provider"] == "terrasatch_mobile"

        second = await ingest_mobile_observation(
            session,
            settings,
            organization_id=organization.id,
            user_id=user.id,
            payload=payload,
        )
        await session.commit()
        assert second[3] is True
        assert second[0].id == transmission.id

    await engine.dispose()


def test_garmin_schema_rejects_untrusted_device_identifiers() -> None:
    with pytest.raises(ValueError):
        GarminIpcPayload.model_validate(
            {
                "Version": "4.0",
                "Events": [
                    {
                        "imei": "not-an-imei",
                        "messageCode": 3,
                        "freeText": "Test",
                    }
                ],
            }
        )
