"""OAuth provider adapters for Google Drive and Slack."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import urlencode

import httpx

from terrasatch.config import Settings
from terrasatch.errors import ProviderUnavailable


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

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        if not settings.google_drive_oauth_is_configured:
            raise ProviderUnavailable("Google Drive OAuth is not configured")
        self.client_id = settings.google_oauth_client_id or ""
        self.client_secret = settings.google_oauth_client_secret.get_secret_value()  # type: ignore[union-attr]
        self.redirect_uri = str(settings.google_oauth_redirect_uri)
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
            raise ProviderUnavailable("Google refresh token is unavailable; reconnect Google Drive")
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


class SlackOAuthAdapter:
    provider_key = "slack"
    scopes = ("incoming-webhook",)
    authorization_endpoint = "https://slack.com/oauth/v2/authorize"
    token_endpoint = "https://slack.com/api/oauth.v2.access"
    auth_test_endpoint = "https://slack.com/api/auth.test"
    revoke_endpoint = "https://slack.com/api/auth.revoke"

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        if not settings.slack_oauth_is_configured:
            raise ProviderUnavailable("Slack OAuth is not configured")
        self.client_id = settings.slack_oauth_client_id or ""
        self.client_secret = settings.slack_oauth_client_secret.get_secret_value()  # type: ignore[union-attr]
        self.redirect_uri = str(settings.slack_oauth_redirect_uri)
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
        incoming = payload.get("incoming_webhook")
        if isinstance(incoming, dict):
            credentials["incoming_webhook"] = {
                key: value
                for key, value in incoming.items()
                if key in {"channel", "channel_id", "configuration_url", "url"}
            }
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
        access_token = credentials.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            return
        response = await _request(
            self.transport,
            "POST",
            self.revoke_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code >= 400:
            raise ProviderUnavailable("Slack credential revocation could not be confirmed")
        payload = _json_payload(response, provider="Slack")
        if payload.get("ok") is not True and payload.get("error") not in {
            "token_revoked",
            "not_authed",
        }:
            raise ProviderUnavailable("Slack credential revocation could not be confirmed")


def provider_is_available(provider_key: str, settings: Settings) -> bool:
    if provider_key == "google_drive":
        return settings.google_drive_oauth_is_configured
    if provider_key == "slack":
        return settings.slack_oauth_is_configured
    return False


def get_adapter(
    provider_key: str,
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> OAuthProviderAdapter:
    if provider_key == "google_drive":
        return GoogleDriveOAuthAdapter(settings, transport=transport)
    if provider_key == "slack":
        return SlackOAuthAdapter(settings, transport=transport)
    raise ProviderUnavailable("This provider does not have an enabled OAuth adapter")
