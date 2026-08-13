"""Installed TerraSatch CLI entrypoint with radio-domain command registration."""

from typing import Annotated

from terrasatch.cli.main import app
from terrasatch.cli import radio as radio_cli

# ``radio.py`` uses postponed annotations so command modules stay cheap to import. Expose
# ``Annotated`` in that module's globals before Typer resolves type hints for command help/run.
radio_cli.Annotated = Annotated
radio_cli.register_radio_cli(app)

__all__ = ["app"]
