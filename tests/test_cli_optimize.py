"""Tests for optimize CLI command."""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

runner = CliRunner()


def test_optimize_command_registered():
    """Test that optimize command is registered on the app."""
    import typer
    from ksearch.cli.optimize import register_optimize_command

    app = typer.Typer()
    register_optimize_command(app)

    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0


def test_optimize_health_check_failure():
    """Test that optimize reports when Ollama is unavailable."""
    import typer
    from ksearch.cli.optimize import register_optimize_command

    app = typer.Typer()
    register_optimize_command(app)

    with patch("ksearch.cli.optimize.OllamaChatClient") as MockClient:
        instance = MockClient.return_value
        instance.health_check.return_value = {"ollama": False, "model_available": False, "error": "connection refused"}
        result = runner.invoke(app, ["test query"])

    assert result.exit_code == 1
