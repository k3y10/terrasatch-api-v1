"""Installed TerraSatch CLI entrypoint with radio and edge command registration."""

from typing import Annotated

from terrasatch.cli import edge as edge_cli
from terrasatch.cli import radio as radio_cli
from terrasatch.cli.main import app

# ``radio.py`` uses postponed annotations so command modules stay cheap to import. Expose
# ``Annotated`` in that module's globals before Typer resolves type hints for command help/run.
radio_cli.Annotated = Annotated
radio_cli.register_radio_cli(app)
edge_cli.register_edge_cli(app)

__all__ = ["app"]
