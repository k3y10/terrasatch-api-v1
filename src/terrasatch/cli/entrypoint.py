"""Installed TerraSatch CLI entrypoint with optional domain command registration."""

from terrasatch.cli.main import app
from terrasatch.cli.radio import register_radio_cli

register_radio_cli(app)

__all__ = ["app"]
