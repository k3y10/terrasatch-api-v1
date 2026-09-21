"""OAuth provider adapters for supported TerraSatch workspace services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import urlencode, urlsplit

import httpx

from terrasatch.config import Settings
from terrasatch.errors import InvalidConfiguration, ProviderUnavailable

from .provider_config import ProviderAppConfig, resolve_provider_app_config


@dataclass(frozen=True, slots=True)
class OAuthExchangeResult:
    credentials: dict[str, object]
    account_label: str | None
    account_id: str | None
    scopes: list[str]


class OAuthProviderAdapter(Protocol):
    provider_key: str

    def authorization_url(self, *, state: str) -> str: ...
    async def exchange_code(self, *, code: str) -> OAuthExchangeResult: ...
    async def refresh(self, credentials: dict[str, object]) -> dict[str, object]: ...
    async def probe(self, credentials: dict[str, object]) -> tuple[str | None, str | None]: ...
    async def revoke(self, credentials: dict[str, object]) -> None: ...


async def _request(
    transport: httpx.AsyncBaseTransport | None,
    method: str,
    url: str,
    **kwargs,
) -> httpx.Response:
    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=False,
            transport=transport,
        ) as client:
            return await client.request(method, url, **kwargs)
    except httpx.HTTPError as error:
        raise ProviderUnavailable("Provider network request failed") from error


def _json_payload(response: httpx.Response, *, provider: str) -> dict[str, object]:
    try:
        payload = response.json()
    except ValueError as error:
        raise ProviderUnavailable(f"{provider} returned an invalid response") from error
    if not isinstance(payload, dict):
        raise ProviderUnavailable(f"{provider} returned an invalid response")
    return payload


_SLACK_WEBHOOK_HOST = "hooks.slack.com"


def _validated_slack_webhook(payload: dict[str, object]) -> dict[str, object]:
    incoming = payload.get("incoming_webhook")
    if not isinstance(incoming, dict):
        raise ProviderUnavailable(
            "Slack did not return the approved incoming webhook destination"
        )
    url = incoming.get("url")
    channel_id = incoming.get("channel_id")
    if not isinstance(url, str) or not url:
        raise ProviderUnavailable(
            "Slack did not return the approved incoming webhook destination"
        )
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != _SLACK_WEBHOOK_HOST:
        raise ProviderUnavailable("Slack returned an invalid incoming webhook destination")
    if not isinstance(channel_id, str) or not channel_id:
        raise ProviderUnavailable("Slack did not return the approved channel identifier")
    return {
        key: value
        for key, value in incoming.items()
        if key in {"channel", "channel_id", "configuration_url", "url"}
    }


def _raise_arcgis_error(payload: dict[str, object], *, context: str) -> None:
    error = payload.get("error")
    if not isinstance(error, dict):
        return
    code = error.get("code")
    message = error.get("message") or error.get("error_description") or "request_failed"
    raise ProviderUnavailable(f"ArcGIS {context} failed ({code}: {message})")


def _expiry(expires_in: object) -> str | None:
    try:
        seconds = int(expires_in)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


def token_is_expiring(credentials: dict[str, object], *, within_seconds: int = 300) -> bool:
    raw = credentials.get("expires_at")
    if not isinstance(raw, str) or not raw:
        return False
    try:
        expires_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= datetime.now(UTC) + timedelta(seconds=within_seconds)


class GoogleDriveOAuthAdapter:
    provider_key = "google_drive"
    scopes = ("https://www.googleapis.com/auth/drive.file",)
    authorization_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
    token_endpoint = "https://oauth2.googleapis.com/token"
    revoke_endpoint = "https://oauth2.googleapis.com/revoke"
    about_endpoint = "https://www.googleapis.com/drive/v3/about"

    def __init__(
        self,
        app_config: ProviderAppConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.client_id = app_config.client_id
        self.client_secret = app_config.client_secret
        self.redirect_uri = app_config.redirect_uri
        self.transport = transport

    def authorization_url(self, *, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }
        return f"{self.authorization_endpoint}?{urlencode(params)}"

    async def exchange_code(self, *, code: str) -> OAuthExchangeResult:
        response = await _request(
            self.transport,
            "POST",
            self.token_endpoint,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri,
            },
        )
        if response.status_code >= 400:
            raise ProviderUnavailable("Google authorization code exchange failed")
        payload = _json_payload(response, provider="Google")
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ProviderUnavailable("Google did not return an access token")
        scope_text = str(payload.get("scope") or " ".join(self.scopes))
        credentials: dict[str, object] = {
            "provider": self.provider_key,
            "access_token": access_token,
            "token_type": str(payload.get("token_type") or "Bearer"),
            "scope": scope_text.split(),
        }
        refresh_token = payload.get("refresh_token")
        if isinstance(refresh_token, str) and refresh_token:
            credentials["refresh_token"] = refresh_token
        expires_at = _expiry(payload.get("expires_in"))
        if expires_at:
            credentials["expires_at"] = expires_at
        label, account_id = await self.probe(credentials)
        return OAuthExchangeResult(credentials, label, account_id, scope_text.split())

    async def refresh(self, credentials: dict[str, object]) -> dict[str, object]:
        refresh_token = credentials.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise ProviderUnavailable(
                "Google refresh token is unavailable; reconnect Google Drive"
            )
        response = await _request(
            self.transport,
            "POST",
            self.token_endpoint,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if response.status_code >= 400:
            raise ProviderUnavailable("Google access-token refresh failed")
        payload = _json_payload(response, provider="Google")
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ProviderUnavailable("Google did not return a refreshed access token")
        next_credentials = dict(credentials)
        next_credentials["access_token"] = access_token
        if payload.get("scope"):
            next_credentials["scope"] = str(payload["scope"]).split()
        expires_at = _expiry(payload.get("expires_in"))
        if expires_at:
            next_credentials["expires_at"] = expires_at
        return next_credentials

    async def probe(self, credentials: dict[str, object]) -> tuple[str | None, str | None]:
        access_token = credentials.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ProviderUnavailable("Google access token is unavailable")
        response = await _request(
            self.transport,
            "GET",
            self.about_endpoint,
            params={"fields": "user(displayName,emailAddress,permissionId)"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code >= 400:
            raise ProviderUnavailable("Google Drive connection check failed")
        payload = _json_payload(response, provider="Google Drive")
        user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
        label = user.get("emailAddress") or user.get("displayName")
        account_id = user.get("permissionId")
        return (
            str(label)[:255] if label else None,
            str(account_id)[:255] if account_id else None,
        )

    async def revoke(self, credentials: dict[str, object]) -> None:
        token = credentials.get("refresh_token") or credentials.get("access_token")
        if not isinstance(token, str) or not token:
            return
        response = await _request(
            self.transport,
            "POST",
            self.revoke_endpoint,
            data={"token": token},
        )
        if response.status_code not in {200, 400}:
            raise ProviderUnavailable("Google credential revocation could not be confirmed")


class GoogleCalendarOAuthAdapter(GoogleDriveOAuthAdapter):
    """Google Calendar OAuth adapter kept separate from Drive authorization."""

    provider_key = "google_calendar"
    scopes = ("https://www.googleapis.com/auth/calendar.events",)
    events_endpoint = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

    async def probe(self, credentials: dict[str, object]) -> tuple[str | None, str | None]:
        access_token = credentials.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ProviderUnavailable("Google Calendar access token is unavailable")
        response = await _request(
            self.transport,
            "GET",
            self.events_endpoint,
            params={"maxResults": "1"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code >= 400:
            raise ProviderUnavailable("Google Calendar connection check failed")
        _json_payload(response, provider="Google Calendar")
        return "Google Calendar", "primary"


class Microsoft365OAuthAdapter:
    """Microsoft Graph delegated OAuth adapter for personal OneDrive output."""

    provider_key = "microsoft_365"
    scopes = (
        "offline_access",
        "User.Read",
        "Files.ReadWrite",
    )
    authorization_endpoint = (
        "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    )
    token_endpoint = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    profile_endpoint = "https://graph.microsoft.com/v1.0/me"

    def __init__(
        self,
        app_config: ProviderAppConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.client_id = app_config.client_id
        self.client_secret = app_config.client_secret
        self.redirect_uri = app_config.redirect_uri
        self.transport = transport

    def authorization_url(self, *, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "response_mode": "query",
            "scope": " ".join(self.scopes),
            "state": state,
        }
        return f"{self.authorization_endpoint}?{urlencode(params)}"

    async def exchange_code(self, *, code: str) -> OAuthExchangeResult:
        response = await _request(
            self.transport,
            "POST",
            self.token_endpoint,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri,
                "scope": " ".join(self.scopes),
            },
        )
        if response.status_code >= 400:
            raise ProviderUnavailable("Microsoft authorization code exchange failed")
        payload = _json_payload(response, provider="Microsoft")
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        if not isinstance(access_token, str) or not access_token:
            raise ProviderUnavailable("Microsoft did not return an access token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise ProviderUnavailable(
                "Microsoft did not return a refresh token; reconnect Microsoft 365"
            )
        scope_text = str(payload.get("scope") or " ".join(self.scopes))
        credentials: dict[str, object] = {
            "provider": self.provider_key,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": str(payload.get("token_type") or "Bearer"),
            "scope": scope_text.split(),
        }
        expires_at = _expiry(payload.get("expires_in"))
        if expires_at:
            credentials["expires_at"] = expires_at
        label, account_id = await self.probe(credentials)
        return OAuthExchangeResult(
            credentials,
            label,
            account_id,
            scope_text.split(),
        )

    async def refresh(self, credentials: dict[str, object]) -> dict[str, object]:
        refresh_token = credentials.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise ProviderUnavailable(
                "Microsoft refresh token is unavailable; reconnect Microsoft 365"
            )
        response = await _request(
            self.transport,
            "POST",
            self.token_endpoint,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
                "scope": " ".join(self.scopes),
            },
        )
        if response.status_code >= 400:
            raise ProviderUnavailable("Microsoft access-token refresh failed")
        payload = _json_payload(response, provider="Microsoft")
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ProviderUnavailable("Microsoft did not return a refreshed access token")
        next_credentials = dict(credentials)
        next_credentials["access_token"] = access_token
        next_refresh = payload.get("refresh_token")
        if isinstance(next_refresh, str) and next_refresh:
            next_credentials["refresh_token"] = next_refresh
        expires_at = _expiry(payload.get("expires_in"))
        if expires_at:
            next_credentials["expires_at"] = expires_at
        if payload.get("scope"):
            next_credentials["scope"] = str(payload["scope"]).split()
        return next_credentials

    async def probe(self, credentials: dict[str, object]) -> tuple[str | None, str | None]:
        access_token = credentials.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ProviderUnavailable("Microsoft access token is unavailable")
        response = await _request(
            self.transport,
            "GET",
            self.profile_endpoint,
            params={"$select": "id,displayName,userPrincipalName,mail"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code >= 400:
            raise ProviderUnavailable("Microsoft connection check failed")
        payload = _json_payload(response, provider="Microsoft Graph")
        label = (
            payload.get("mail")
            or payload.get("userPrincipalName")
            or payload.get("displayName")
        )
        account_id = payload.get("id")
        return (
            str(label)[:255] if label else None,
            str(account_id)[:255] if account_id else None,
        )

    async def revoke(self, credentials: dict[str, object]) -> None:
        # Microsoft does not expose a delegated refresh-token revocation endpoint
        # suitable for this flow. Disconnect deletes TerraSatch's encrypted copy.
        return None


class MicrosoftCalendarOAuthAdapter(Microsoft365OAuthAdapter):
    """Microsoft delegated OAuth adapter for user and shared calendars."""

    provider_key = "microsoft_calendar"
    scopes = (
        "offline_access",
        "User.Read",
        "Calendars.ReadWrite.Shared",
    )


class SlackOAuthAdapter:
    provider_key = "slack"
    scopes = ("incoming-webhook",)
    authorization_endpoint = "https://slack.com/oauth/v2/authorize"
    token_endpoint = "https://slack.com/api/oauth.v2.access"
    auth_test_endpoint = "https://slack.com/api/auth.test"
    revoke_endpoint = "https://slack.com/api/auth.revoke"

    def __init__(
        self,
        app_config: ProviderAppConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.client_id = app_config.client_id
        self.client_secret = app_config.client_secret
        self.redirect_uri = app_config.redirect_uri
        self.transport = transport

    def authorization_url(self, *, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "scope": ",".join(self.scopes),
            "redirect_uri": self.redirect_uri,
            "state": state,
        }
        return f"{self.authorization_endpoint}?{urlencode(params)}"

    async def exchange_code(self, *, code: str) -> OAuthExchangeResult:
        response = await _request(
            self.transport,
            "POST",
            self.token_endpoint,
            data={"code": code, "redirect_uri": self.redirect_uri},
            auth=(self.client_id, self.client_secret),
        )
        if response.status_code >= 400:
            raise ProviderUnavailable("Slack authorization code exchange failed")
        payload = _json_payload(response, provider="Slack")
        if payload.get("ok") is not True:
            error = str(payload.get("error") or "oauth_failed").replace(" ", "_")[:80]
            raise ProviderUnavailable(f"Slack authorization failed ({error})")
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ProviderUnavailable("Slack did not return an access token")
        scope_text = str(payload.get("scope") or "")
        credentials: dict[str, object] = {
            "provider": self.provider_key,
            "access_token": access_token,
            "token_type": str(payload.get("token_type") or "bot"),
            "scope": [item for item in scope_text.split(",") if item],
        }
        refresh_token = payload.get("refresh_token")
        if isinstance(refresh_token, str) and refresh_token:
            credentials["refresh_token"] = refresh_token
        expires_at = _expiry(payload.get("expires_in"))
        if expires_at:
            credentials["expires_at"] = expires_at
        credentials["incoming_webhook"] = _validated_slack_webhook(payload)
        team = payload.get("team") if isinstance(payload.get("team"), dict) else {}
        label = team.get("name")
        account_id = team.get("id")
        return OAuthExchangeResult(
            credentials,
            str(label)[:255] if label else None,
            str(account_id)[:255] if account_id else None,
            [item for item in scope_text.split(",") if item],
        )

    async def refresh(self, credentials: dict[str, object]) -> dict[str, object]:
        refresh_token = credentials.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            return credentials
        response = await _request(
            self.transport,
            "POST",
            self.token_endpoint,
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            auth=(self.client_id, self.client_secret),
        )
        if response.status_code >= 400:
            raise ProviderUnavailable("Slack access-token refresh failed")
        payload = _json_payload(response, provider="Slack")
        if payload.get("ok") is not True:
            raise ProviderUnavailable("Slack access-token refresh failed")
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ProviderUnavailable("Slack did not return a refreshed access token")
        next_credentials = dict(credentials)
        next_credentials["access_token"] = access_token
        next_refresh = payload.get("refresh_token")
        if isinstance(next_refresh, str) and next_refresh:
            next_credentials["refresh_token"] = next_refresh
        expires_at = _expiry(payload.get("expires_in"))
        if expires_at:
            next_credentials["expires_at"] = expires_at
        if payload.get("scope"):
            next_credentials["scope"] = [
                item for item in str(payload["scope"]).split(",") if item
            ]
        return next_credentials

    async def probe(self, credentials: dict[str, object]) -> tuple[str | None, str | None]:
        access_token = credentials.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ProviderUnavailable("Slack access token is unavailable")
        response = await _request(
            self.transport,
            "POST",
            self.auth_test_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code >= 400:
            raise ProviderUnavailable("Slack connection check failed")
        payload = _json_payload(response, provider="Slack")
        if payload.get("ok") is not True:
            raise ProviderUnavailable("Slack connection check failed")
        label = payload.get("team") or payload.get("user")
        account_id = payload.get("team_id") or payload.get("enterprise_id")
        return (
            str(label)[:255] if label else None,
            str(account_id)[:255] if account_id else None,
        )

    async def revoke(self, credentials: dict[str, object]) -> None:
        current = credentials
        if token_is_expiring(current) and current.get("refresh_token"):
            current = await self.refresh(current)
        access_token = current.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ProviderUnavailable(
                "Slack access token is unavailable; remote revocation was not attempted"
            )
        response = await _request(
            self.transport,
            "POST",
            self.revoke_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code >= 400:
            raise ProviderUnavailable(
                "Slack credential revocation could not be confirmed"
            )
        payload = _json_payload(response, provider="Slack")
        if payload.get("ok") is not True and payload.get("error") not in {
            "token_revoked",
            "not_authed",
        }:
            raise ProviderUnavailable("Slack credential revocation could not be confirmed")


class AtlassianOAuthAdapter:
    """Shared Atlassian Cloud OAuth 2.0 (3LO) adapter."""

    provider_key = ""
    scopes: tuple[str, ...] = ()
    resource_scope_markers: frozenset[str] = frozenset()
    authorization_endpoint = "https://auth.atlassian.com/authorize"
    token_endpoint = "https://auth.atlassian.com/oauth/token"
    resources_endpoint = "https://api.atlassian.com/oauth/token/accessible-resources"

    def __init__(
        self,
        app_config: ProviderAppConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.client_id = app_config.client_id
        self.client_secret = app_config.client_secret
        self.redirect_uri = app_config.redirect_uri
        self.transport = transport

    def authorization_url(self, *, state: str) -> str:
        params = {
            "audience": "api.atlassian.com",
            "client_id": self.client_id,
            "scope": " ".join(self.scopes),
            "redirect_uri": self.redirect_uri,
            "state": state,
            "response_type": "code",
            "prompt": "consent",
        }
        return f"{self.authorization_endpoint}?{urlencode(params)}"

    async def exchange_code(self, *, code: str) -> OAuthExchangeResult:
        response = await _request(
            self.transport,
            "POST",
            self.token_endpoint,
            json={
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": self.redirect_uri,
            },
            headers={"Content-Type": "application/json"},
        )
        if response.status_code >= 400:
            raise ProviderUnavailable("Atlassian authorization code exchange failed")
        payload = _json_payload(response, provider="Atlassian")
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        if not isinstance(access_token, str) or not access_token:
            raise ProviderUnavailable("Atlassian did not return an access token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise ProviderUnavailable(
                "Atlassian did not return a refresh token; reconnect the integration"
            )
        scope_text = str(payload.get("scope") or " ".join(self.scopes))
        credentials: dict[str, object] = {
            "provider": self.provider_key,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": str(payload.get("token_type") or "Bearer"),
            "scope": scope_text.split(),
        }
        expires_at = _expiry(payload.get("expires_in"))
        if expires_at:
            credentials["expires_at"] = expires_at
        label, account_id = await self.probe(credentials)
        return OAuthExchangeResult(
            credentials,
            label,
            account_id,
            scope_text.split(),
        )

    async def refresh(self, credentials: dict[str, object]) -> dict[str, object]:
        refresh_token = credentials.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise ProviderUnavailable(
                "Atlassian refresh token is unavailable; reconnect the integration"
            )
        response = await _request(
            self.transport,
            "POST",
            self.token_endpoint,
            json={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/json"},
        )
        if response.status_code >= 400:
            raise ProviderUnavailable("Atlassian access-token refresh failed")
        payload = _json_payload(response, provider="Atlassian")
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ProviderUnavailable("Atlassian did not return a refreshed access token")
        next_credentials = dict(credentials)
        next_credentials["access_token"] = access_token
        next_refresh = payload.get("refresh_token")
        if isinstance(next_refresh, str) and next_refresh:
            next_credentials["refresh_token"] = next_refresh
        expires_at = _expiry(payload.get("expires_in"))
        if expires_at:
            next_credentials["expires_at"] = expires_at
        if payload.get("scope"):
            next_credentials["scope"] = str(payload["scope"]).split()
        return next_credentials

    async def probe(self, credentials: dict[str, object]) -> tuple[str | None, str | None]:
        access_token = credentials.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ProviderUnavailable("Atlassian access token is unavailable")
        response = await _request(
            self.transport,
            "GET",
            self.resources_endpoint,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )
        if response.status_code >= 400:
            raise ProviderUnavailable("Atlassian site access check failed")
        try:
            payload = response.json()
        except ValueError as error:
            raise ProviderUnavailable(
                "Atlassian returned an invalid site-access response"
            ) from error
        if not isinstance(payload, list):
            raise ProviderUnavailable("Atlassian returned an invalid site-access response")
        resources = [item for item in payload if isinstance(item, dict)]
        for resource in resources:
            scopes = resource.get("scopes")
            if not isinstance(scopes, list):
                continue
            if self.resource_scope_markers and not (
                self.resource_scope_markers & {str(item) for item in scopes}
            ):
                continue
            resource_id = resource.get("id")
            label = resource.get("name") or resource.get("url")
            if isinstance(resource_id, str) and resource_id:
                return (
                    str(label)[:255] if label else "Atlassian Cloud",
                    resource_id[:255],
                )
        raise ProviderUnavailable(
            "Atlassian did not return an authorized site for this integration"
        )

    async def revoke(self, credentials: dict[str, object]) -> None:
        # Atlassian 3LO does not expose a provider token-revocation endpoint for
        # this server-side flow. Disconnect deletes TerraSatch's encrypted copy.
        return None


class JiraOAuthAdapter(AtlassianOAuthAdapter):
    provider_key = "jira"
    scopes = ("offline_access", "write:jira-work")
    resource_scope_markers = frozenset({"write:jira-work"})


class ConfluenceOAuthAdapter(AtlassianOAuthAdapter):
    provider_key = "confluence"
    scopes = ("offline_access", "write:page:confluence")
    resource_scope_markers = frozenset({"write:page:confluence"})


class ArcGISOAuthAdapter:
    """ArcGIS Online OAuth adapter for server-side user authorization."""

    provider_key = "esri_arcgis"
    authorization_endpoint = "https://www.arcgis.com/sharing/rest/oauth2/authorize"
    token_endpoint = "https://www.arcgis.com/sharing/rest/oauth2/token"
    revoke_endpoint = "https://www.arcgis.com/sharing/rest/oauth2/revokeToken"
    self_endpoint = "https://www.arcgis.com/sharing/rest/community/self"

    def __init__(
        self,
        app_config: ProviderAppConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.client_id = app_config.client_id
        self.client_secret = app_config.client_secret
        self.redirect_uri = app_config.redirect_uri
        self.transport = transport

    def authorization_url(self, *, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "state": state,
        }
        return f"{self.authorization_endpoint}?{urlencode(params)}"

    async def exchange_code(self, *, code: str) -> OAuthExchangeResult:
        response = await _request(
            self.transport,
            "POST",
            self.token_endpoint,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
                "f": "json",
            },
        )
        if response.status_code >= 400:
            raise ProviderUnavailable("ArcGIS authorization code exchange failed")
        payload = _json_payload(response, provider="ArcGIS")
        _raise_arcgis_error(payload, context="authorization")
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        if not isinstance(access_token, str) or not access_token:
            raise ProviderUnavailable("ArcGIS did not return an access token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise ProviderUnavailable(
                "ArcGIS did not return a refresh token; reconnect the integration"
            )

        credentials: dict[str, object] = {
            "provider": self.provider_key,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
        }
        expires_at = _expiry(payload.get("expires_in"))
        if expires_at:
            credentials["expires_at"] = expires_at
        refresh_expires_at = _expiry(payload.get("refresh_token_expires_in"))
        if refresh_expires_at:
            credentials["refresh_token_expires_at"] = refresh_expires_at

        label, account_id = await self.probe(credentials)
        return OAuthExchangeResult(credentials, label, account_id, [])

    async def refresh(self, credentials: dict[str, object]) -> dict[str, object]:
        refresh_token = credentials.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise ProviderUnavailable("ArcGIS refresh token is unavailable; reconnect ArcGIS")

        response = await _request(
            self.transport,
            "POST",
            self.token_endpoint,
            data={
                "client_id": self.client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "f": "json",
            },
        )
        if response.status_code >= 400:
            raise ProviderUnavailable("ArcGIS access-token refresh failed")
        payload = _json_payload(response, provider="ArcGIS")
        _raise_arcgis_error(payload, context="token refresh")
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ProviderUnavailable("ArcGIS did not return a refreshed access token")

        next_credentials = dict(credentials)
        next_credentials["access_token"] = access_token
        expires_at = _expiry(payload.get("expires_in"))
        if expires_at:
            next_credentials["expires_at"] = expires_at
        return next_credentials

    async def probe(self, credentials: dict[str, object]) -> tuple[str | None, str | None]:
        access_token = credentials.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ProviderUnavailable("ArcGIS access token is unavailable")
        response = await _request(
            self.transport,
            "GET",
            self.self_endpoint,
            params={"f": "json"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code >= 400:
            raise ProviderUnavailable("ArcGIS account check failed")
        payload = _json_payload(response, provider="ArcGIS")
        _raise_arcgis_error(payload, context="account check")

        username = payload.get("username")
        full_name = payload.get("fullName")
        org_id = payload.get("orgId")
        label = full_name or username
        account_id = (
            f"{org_id}:{username}"
            if isinstance(org_id, str)
            and org_id
            and isinstance(username, str)
            and username
            else username
        )
        return (
            str(label)[:255] if label else None,
            str(account_id)[:255] if account_id else None,
        )

    async def revoke(self, credentials: dict[str, object]) -> None:
        refresh_token = credentials.get("refresh_token")
        access_token = credentials.get("access_token")
        token = refresh_token or access_token
        if not isinstance(token, str) or not token:
            return
        token_hint = "refresh_token" if refresh_token else "access_token"
        response = await _request(
            self.transport,
            "POST",
            self.revoke_endpoint,
            data={
                "auth_token": token,
                "token_type_hint": token_hint,
                "client_id": self.client_id,
                "f": "json",
            },
        )
        if response.status_code >= 400:
            raise ProviderUnavailable("ArcGIS credential revocation failed")
        payload = _json_payload(response, provider="ArcGIS")
        _raise_arcgis_error(payload, context="credential revocation")
        if payload.get("success") is not True:
            raise ProviderUnavailable("ArcGIS credential revocation could not be confirmed")


def provider_is_available(provider_key: str, settings: Settings) -> bool:
    try:
        resolve_provider_app_config(settings, provider_key, required=True)
        return settings.integration_secret_store_is_configured
    except (InvalidConfiguration, ProviderUnavailable):
        return False


def get_adapter(
    provider_key: str,
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> OAuthProviderAdapter:
    app_config = resolve_provider_app_config(
        settings,
        provider_key,
        required=True,
    )
    assert app_config is not None
    if provider_key == "google_drive":
        return GoogleDriveOAuthAdapter(app_config, transport=transport)
    if provider_key == "google_calendar":
        return GoogleCalendarOAuthAdapter(app_config, transport=transport)
    if provider_key == "microsoft_365":
        return Microsoft365OAuthAdapter(app_config, transport=transport)
    if provider_key == "microsoft_calendar":
        return MicrosoftCalendarOAuthAdapter(app_config, transport=transport)
    if provider_key == "jira":
        return JiraOAuthAdapter(app_config, transport=transport)
    if provider_key == "confluence":
        return ConfluenceOAuthAdapter(app_config, transport=transport)
    if provider_key == "slack":
        return SlackOAuthAdapter(app_config, transport=transport)
    if provider_key == "esri_arcgis":
        return ArcGISOAuthAdapter(app_config, transport=transport)
    raise ProviderUnavailable("This provider does not have an enabled OAuth adapter")
