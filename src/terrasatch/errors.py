"""Domain errors that map to stable public API error responses."""

from __future__ import annotations


class TerraSatchError(Exception):
    """Base class for expected domain failures."""

    code = "terrasatch_error"
    status_code = 400

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidConfiguration(TerraSatchError):
    code = "invalid_configuration"


class ProviderUnavailable(TerraSatchError):
    code = "provider_unavailable"
    status_code = 503


class AuthenticationFailed(TerraSatchError):
    code = "authentication_failed"
    status_code = 401


class TenantAccessDenied(TerraSatchError):
    code = "tenant_access_denied"
    status_code = 403