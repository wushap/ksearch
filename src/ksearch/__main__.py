"""CLI entry point for ksearch."""

import os
import sys

import typer

from ksearch.cli_kbase import register_kbase_commands
from ksearch.cli_optimize import register_optimize_command
from ksearch.cli_search import register_search_command
from ksearch.cli_system import (
    register_config_command,
    register_health_command,
    register_stats_command,
)
from ksearch.debug_logging import log_event, start_debug_session, write_context


app = typer.Typer(name="ksearch", help="Personal knowledge base with web search - CLI tool")
kbase_app = typer.Typer(name="kbase", help="kbase operations")
app.add_typer(kbase_app, name="kbase")


def _root_argv(ctx: typer.Context, debug: bool) -> list[str]:
    argv = list(sys.argv[1:])
    subcommand = ctx.invoked_subcommand or ""
    if not subcommand or subcommand in argv:
        return argv

    rebuilt = [subcommand]
    if debug:
        rebuilt.insert(0, "--debug")
    return rebuilt


@app.callback()
def root_callback(
    ctx: typer.Context,
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Write debug logs under ~/.ksearch/debug/cli-<time>/",
    ),
):
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug
    if not debug:
        return

    argv = _root_argv(ctx, debug)
    session = start_debug_session(
        argv=argv,
        cwd=os.getcwd(),
        command=ctx.invoked_subcommand or "",
    )
    ctx.obj["debug_session"] = session
    write_context({"python_version": sys.version, "debug_dir": str(session.debug_dir)})
    log_event("ksearch.__main__", "cli_bootstrap", {"argv": argv})

register_search_command(app)
register_stats_command(app)
register_config_command(app)
register_health_command(app)
register_kbase_commands(kbase_app)
register_optimize_command(app)


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
