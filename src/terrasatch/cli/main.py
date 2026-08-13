"""Terminal operations for TerraSatch."""

from __future__ import annotations

import asyncio
import getpass
import json
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import typer
import uvicorn
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.admin.security import generate_session_secret, hash_admin_password
from terrasatch.auth.service import issue_api_key, list_api_keys, revoke_api_key
from terrasatch.config import Environment, Settings
from terrasatch.database.session import create_session_factory
from terrasatch.errors import TerraSatchError
from terrasatch.main import create_app
from terrasatch.observability.health import check_readiness
from terrasatch.organizations.service import (
    create_organization,
    create_site,
    list_organizations,
    list_sites,
)
from terrasatch.workers.runner import run_worker

app = typer.Typer(help="Operate the TerraSatch API platform.", no_args_is_help=True)
config_app = typer.Typer(help="Inspect and validate runtime configuration.", no_args_is_help=True)
org_app = typer.Typer(help="Manage organizations.", no_args_is_help=True)
site_app = typer.Typer(help="Manage organization sites.", no_args_is_help=True)
api_key_app = typer.Typer(help="Manage server API keys.", no_args_is_help=True)
admin_app = typer.Typer(help="Configure browser administration.", no_args_is_help=True)
deployment_app = typer.Typer(help="Check a deployed TerraSatch API.", no_args_is_help=True)
app.add_typer(config_app, name="config")
app.add_typer(org_app, name="org")
app.add_typer(site_app, name="site")
app.add_typer(api_key_app, name="api-key")
app.add_typer(admin_app, name="admin")
app.add_typer(deployment_app, name="deployment")


def _load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as error:
        typer.echo(f"Configuration invalid: {error.errors()[0]['msg']}", err=True)
        raise typer.Exit(code=1) from error


def _print(data: object, *, as_json: bool) -> None:
    if as_json:
        if hasattr(data, "model_dump"):
            data = data.model_dump(mode="json")
        typer.echo(json.dumps(data, indent=2, default=str))
        return
    typer.echo(str(data))


def _redact_url(value: object) -> str:
    parsed = urlsplit(str(value))
    if not parsed.password:
        return str(value)
    username = parsed.username or ""
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit(
        (parsed.scheme, f"{username}:***@{host}", parsed.path, parsed.query, parsed.fragment)
    )


def _run_database[Result](
    operation: Callable[[AsyncSession, Settings], Awaitable[Result]],
) -> Result:
    """Execute one CLI database operation transactionally with concise domain errors."""

    async def run() -> Result:
        settings = _load_settings()
        session_factory = create_session_factory(settings)
        async with session_factory() as session:
            try:
                result = await operation(session, settings)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise

    try:
        return asyncio.run(run())
    except TerraSatchError as error:
        typer.echo(f"Error [{error.code}]: {error.message}", err=True)
        raise typer.Exit(code=1) from error


def _upsert_environment_file(values: dict[str, str], *, destination: Path) -> None:
    """Safely update untracked local configuration while retaining unrelated entries."""

    source = Path(".env.example")
    source_file = destination if destination.exists() else source
    lines = source_file.read_text().splitlines()
    remaining = dict(values)
    output: list[str] = []
    for line in lines:
        key, separator, _ = line.partition("=")
        if separator and key in remaining:
            output.append(f"{key}={remaining.pop(key)}")
        else:
            output.append(line)
    output.extend(f"{key}={value}" for key, value in remaining.items())
    destination.write_text("\n".join(output) + "\n")
    destination.chmod(0o600)


@app.command()
def init(force: bool = typer.Option(False, help="Replace an existing local .env file.")) -> None:
    """Create an ignored local environment file from the safe example."""

    source = Path(".env.example")
    destination = Path(".env")
    if not source.exists():
        typer.echo(".env.example was not found in the current directory.", err=True)
        raise typer.Exit(code=1)
    if destination.exists() and not force:
        typer.echo(".env already exists; use --force to replace it.", err=True)
        raise typer.Exit(code=1)
    shutil.copyfile(source, destination)
    destination.chmod(0o600)
    typer.echo("Created .env with owner-only permissions.")


@app.command()
def setup(force: bool = typer.Option(False, help="Replace an existing local .env file.")) -> None:
    """Interactively create local runtime configuration without committing secrets."""

    destination = Path(".env")
    if destination.exists() and not force:
        typer.echo(".env already exists; use --force to replace it.", err=True)
        raise typer.Exit(code=1)

    environment = typer.prompt("Environment", default=Environment.LOCAL.value)
    if environment not in {item.value for item in Environment}:
        typer.echo("Environment must be local, development, staging, or production.", err=True)
        raise typer.Exit(code=1)
    deployment_name = typer.prompt("Deployment name", default="local")
    api_base_url = typer.prompt("API base URL", default="http://localhost:8000")
    database_url = typer.prompt(
        "Database URL",
        default="postgresql+asyncpg://terrasatch:terrasatch@localhost:5432/terrasatch",
    )
    redis_url = typer.prompt("Redis URL", default="redis://localhost:6379/0")
    speech_provider = typer.prompt("Speech recognition provider", default="local_whisper")
    intelligence_provider = typer.prompt("Intelligence provider", default="deterministic")
    storage_provider = typer.prompt("Storage provider", default="local_filesystem")
    billing_enabled = typer.confirm("Billing enabled", default=False)
    organization = typer.prompt("Initial organization name", default="")
    site = typer.prompt("Initial site name", default="")
    industry_profile = typer.prompt("Industry profile", default="general")
    values = {
        "TERRASATCH_ENV": environment,
        "TERRASATCH_DEPLOYMENT_NAME": deployment_name,
        "TERRASATCH_API_BASE_URL": api_base_url,
        "TERRASATCH_DATABASE_URL": database_url,
        "TERRASATCH_REDIS_URL": redis_url,
        "TERRASATCH_LOG_LEVEL": "INFO",
        "TERRASATCH_LOG_FORMAT": "json",
        "TERRASATCH_CORS_ORIGINS": "http://localhost:3000,http://127.0.0.1:3000",
        "TERRASATCH_ENABLE_DOCS": "true",
        "TERRASATCH_STT_PROVIDER": speech_provider,
        "TERRASATCH_INTELLIGENCE_PROVIDER": intelligence_provider,
        "TERRASATCH_STORAGE_PROVIDER": storage_provider,
        "TERRASATCH_BILLING_ENABLED": str(billing_enabled).lower(),
        "TERRASATCH_INITIAL_ORGANIZATION": organization,
        "TERRASATCH_INITIAL_SITE": site,
        "TERRASATCH_INDUSTRY_PROFILE": industry_profile,
    }
    destination.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
    destination.chmod(0o600)
    typer.echo("Wrote .env with owner-only permissions.")
    typer.echo("Organization and site creation follows Phase 2.")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Interface to bind."),
    port: int = typer.Option(8000, min=1, max=65535, help="TCP port to bind."),
) -> None:
    """Start the TerraSatch ASGI API server."""

    settings = _load_settings()
    uvicorn.run(create_app(settings), host=host, port=port, log_config=None)


@app.command()
def worker() -> None:
    """Start the supervised background worker process."""

    asyncio.run(run_worker(_load_settings()))


@app.command()
def health(as_json: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """Check required backing services."""

    report = asyncio.run(check_readiness(_load_settings()))
    _print(report, as_json=as_json)
    if report.status != "healthy":
        raise typer.Exit(code=1)


@app.command()
def status(as_json: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """Show the current API and backing-service status."""

    settings = _load_settings()
    report = asyncio.run(check_readiness(settings))
    if as_json:
        _print(report, as_json=True)
    else:
        typer.echo("TerraSatch API\n")
        typer.echo(f"Environment       {settings.environment.value}")
        typer.echo(f"Deployment        {settings.deployment_name}")
        typer.echo(f"API               {'HEALTHY' if report.status == 'healthy' else 'UNHEALTHY'}")
        for dependency in report.dependencies:
            typer.echo(f"{dependency.name.title():<18} {dependency.status.upper()}")
    if report.status != "healthy":
        raise typer.Exit(code=1)


@app.command()
def doctor(as_json: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """Run bounded platform diagnostics and report missing optional SDR tooling."""

    report = asyncio.run(check_readiness(_load_settings()))
    tools = {tool: bool(shutil.which(tool)) for tool in ("rtl_test", "rtl_fm")}
    if as_json:
        _print({"readiness": report, "sdr_tools": tools}, as_json=True)
    else:
        typer.echo("TerraSatch Diagnostics\n")
        for dependency in report.dependencies:
            typer.echo(f"{dependency.name.title():<20} {dependency.status.upper()}")
        for tool, found in tools.items():
            typer.echo(f"{tool:<20} {'AVAILABLE' if found else 'NOT INSTALLED (optional)'}")
    if report.status != "healthy":
        raise typer.Exit(code=1)


@admin_app.command("configure")
def admin_configure(
    email: str | None = typer.Option(None, "--email", help="Browser administrator email address."),
    env_file: Annotated[
        Path,
        typer.Option("--env-file", help="Owner-only environment file to update."),
    ] = Path(".env"),
) -> None:
    """Set an owner-only local admin login configuration without printing secrets."""

    admin_email = email or typer.prompt("Administrator email").strip()
    if "@" not in admin_email or admin_email.startswith("@") or admin_email.endswith("@"):
        typer.echo("A valid administrator email is required.", err=True)
        raise typer.Exit(code=1)
    password = getpass.getpass("Administrator password (12+ characters): ")
    confirmation = getpass.getpass("Confirm administrator password: ")
    if password != confirmation:
        typer.echo("Passwords do not match.", err=True)
        raise typer.Exit(code=1)
    try:
        password_hash = hash_admin_password(password)
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    _upsert_environment_file(
        {
            "TERRASATCH_ADMIN_EMAIL": admin_email,
            "TERRASATCH_ADMIN_PASSWORD_HASH": password_hash,
            "TERRASATCH_ADMIN_SESSION_SECRET": generate_session_secret(),
        },
        destination=env_file,
    )
    typer.echo(f"Browser administration configured in {env_file} with owner-only permissions.")
    typer.echo("Restart the API, then open /admin using HTTPS in production.")


@deployment_app.command("check")
def deployment_check(
    base_url: Annotated[
        str | None,
        typer.Option("--base-url", help="Public API base URL."),
    ] = None,
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Check an externally reachable readiness endpoint without exposing secrets."""

    settings = _load_settings()
    url = str(base_url or settings.api_base_url).rstrip("/") + "/health/ready"
    parsed_url = urlsplit(url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        typer.echo("--base-url must be an absolute http or https URL.", err=True)
        raise typer.Exit(code=1)

    async def check() -> dict[str, object]:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                response = await client.get(url)
        except httpx.HTTPError as error:
            return {"url": url, "reachable": False, "error": type(error).__name__}
        try:
            body: object = response.json()
        except ValueError:
            body = None
        return {
            "url": url,
            "reachable": response.status_code == 200,
            "http_status": response.status_code,
            "body": body,
        }

    result = asyncio.run(check())
    _print(result, as_json=as_json)
    if not result["reachable"]:
        raise typer.Exit(code=1)


@org_app.command("create")
def org_create(
    name: str = typer.Argument(..., min=1, help="Organization display name."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Create a new organization in the bootstrap account."""

    async def operation(session: AsyncSession, _settings: Settings):
        return await create_organization(session, name=name)

    organization = _run_database(operation)
    data = {"id": str(organization.id), "name": organization.name, "slug": organization.slug}
    output = data if as_json else f"Created organization {organization.name} ({organization.id})"
    _print(output, as_json=as_json)


@org_app.command("list")
def org_list(as_json: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """List organizations available to local administrative operations."""

    async def operation(session: AsyncSession, _settings: Settings):
        return await list_organizations(session)

    organizations = _run_database(operation)
    data = [
        {"id": str(organization.id), "name": organization.name, "slug": organization.slug}
        for organization in organizations
    ]
    if as_json:
        _print(data, as_json=True)
        return
    output = "No organizations found." if not data else "\n".join(
        f"{item['id']}  {item['name']}" for item in data
    )
    typer.echo(output)


@site_app.command("create")
def site_create(
    name: str = typer.Argument(..., min=1, help="Site display name."),
    organization: str | None = typer.Option(
        None,
        "--organization",
        help="Organization ID, slug, or name.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Create a site within the selected organization."""

    async def operation(session: AsyncSession, _settings: Settings):
        return await create_site(session, name=name, organization_selector=organization)

    site = _run_database(operation)
    data = {
        "id": str(site.id),
        "organization_id": str(site.organization_id),
        "name": site.name,
        "slug": site.slug,
    }
    _print(data if as_json else f"Created site {site.name} ({site.id})", as_json=as_json)


@site_app.command("list")
def site_list(
    organization: str | None = typer.Option(
        None,
        "--organization",
        help="Organization ID, slug, or name.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """List sites only inside the selected organization."""

    async def operation(session: AsyncSession, _settings: Settings):
        return await list_sites(session, organization_selector=organization)

    selected_organization, sites = _run_database(operation)
    data = {
        "organization_id": str(selected_organization.id),
        "sites": [{"id": str(site.id), "name": site.name, "slug": site.slug} for site in sites],
    }
    if as_json:
        _print(data, as_json=True)
        return
    typer.echo(
        f"No sites found for {selected_organization.name}."
        if not sites
        else "\n".join(f"{site.id}  {site.name}" for site in sites)
    )


@api_key_app.command("create")
def api_key_create(
    name: str = typer.Option(..., "--name", min=1, help="Credential label."),
    scope: Annotated[
        list[str] | None,
        typer.Option("--scope", help="Repeatable API scope."),
    ] = None,
    organization: str | None = typer.Option(
        None,
        "--organization",
        help="Organization ID, slug, or name.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Issue a tenant-scoped server credential and reveal its token once."""

    async def operation(session: AsyncSession, settings: Settings):
        return await issue_api_key(
            session,
            settings=settings,
            name=name,
            scopes=scope or ["admin"],
            organization_selector=organization,
        )

    api_key, generated = _run_database(operation)
    data = {
        "id": str(api_key.id),
        "organization_id": str(api_key.organization_id),
        "key_prefix": api_key.key_prefix,
        "scopes": api_key.scopes,
        "token": generated.token,
    }
    if as_json:
        _print(data, as_json=True)
        return
    typer.echo(f"API key created: {generated.token}")
    typer.echo("Store this token now. It cannot be retrieved again.")


@api_key_app.command("list")
def api_key_list(
    organization: str | None = typer.Option(
        None,
        "--organization",
        help="Organization ID, slug, or name.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """List tenant-scoped credential metadata without secret values."""

    async def operation(session: AsyncSession, _settings: Settings):
        return await list_api_keys(session, organization_selector=organization)

    keys = _run_database(operation)
    data = [
        {
            "id": str(key.id),
            "name": key.name,
            "key_prefix": key.key_prefix,
            "scopes": key.scopes,
            "revoked_at": key.revoked_at,
        }
        for key in keys
    ]
    if as_json:
        _print(data, as_json=True)
        return
    output = "No API keys found." if not data else "\n".join(
        f"{item['id']}  {item['name']}" for item in data
    )
    typer.echo(output)


@api_key_app.command("revoke")
def api_key_revoke(
    api_key_id: Annotated[UUID, typer.Argument(help="API key UUID.")],
    organization: str | None = typer.Option(
        None,
        "--organization",
        help="Organization ID, slug, or name.",
    ),
) -> None:
    """Revoke a tenant-scoped service credential."""

    async def operation(session: AsyncSession, _settings: Settings):
        return await revoke_api_key(
            session,
            api_key_id=api_key_id,
            organization_selector=organization,
        )

    api_key = _run_database(operation)
    typer.echo(f"Revoked API key {api_key.key_prefix}.")


@config_app.command("validate")
def config_validate() -> None:
    """Validate configuration without displaying secret values."""

    settings = _load_settings()
    typer.echo(f"Configuration valid for {settings.environment.value}.")


@config_app.command("show")
def config_show(as_json: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """Display non-secret runtime configuration."""

    settings = _load_settings()
    data = {
        "environment": settings.environment.value,
        "deployment_name": settings.deployment_name,
        "api_base_url": str(settings.api_base_url),
        "database_url": _redact_url(settings.database_url),
        "redis_url": _redact_url(settings.redis_url),
        "cors_origins": settings.cors_origins,
        "enable_docs": settings.enable_docs,
        "log_level": settings.log_level,
    }
    output = data if as_json else "\n".join(f"{key}: {value}" for key, value in data.items())
    _print(output, as_json=as_json)


if __name__ == "__main__":
    app()