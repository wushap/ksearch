"""CLI entry point for ksearch."""

import typer

from ksearch.cli_kbase import register_kbase_commands
from ksearch.cli_search import register_search_command
from ksearch.cli_system import (
    register_config_command,
    register_health_command,
    register_stats_command,
)


app = typer.Typer(name="ksearch", help="Personal knowledge base with web search - CLI tool")
kbase_app = typer.Typer(name="kbase", help="kbase operations")
app.add_typer(kbase_app, name="kbase")

register_search_command(app)
register_stats_command(app)
register_config_command(app)
register_health_command(app)
register_kbase_commands(kbase_app)


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
