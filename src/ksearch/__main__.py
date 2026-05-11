"""CLI entry point for ksearch."""

import os
import sys

import typer
from typer.core import TyperGroup

from ksearch.cli_kbase import register_kbase_commands
from ksearch.cli_optimize import register_optimize_command
from ksearch.cli_search import register_search_command
from ksearch.cli_system import (
    register_config_command,
    register_health_command,
    register_stats_command,
)
from ksearch.debug_logging import (
    finish_debug_session,
    log_event,
    start_debug_session,
    write_context,
)


class DebugTyperGroup(TyperGroup):
    def make_context(self, info_name, args, parent=None, **extra):
        raw_argv = list(args) if args is not None else list(sys.argv[1:])
        ctx = super().make_context(info_name, args, parent=parent, **extra)
        ctx.meta["raw_argv"] = raw_argv
        return ctx


app = typer.Typer(
    name="ksearch",
    cls=DebugTyperGroup,
    help="Personal knowledge base with web search - CLI tool",
)
kbase_app = typer.Typer(name="kbase", help="kbase operations")
app.add_typer(kbase_app, name="kbase")


def _root_argv(ctx: typer.Context) -> list[str]:
    return list(ctx.meta.get("raw_argv", sys.argv[1:]))


def _root_command(argv: list[str]) -> str:
    tokens = [token for token in argv if token != "--debug"]
    if not tokens:
        return ""

    command = tokens[0]
    if command == "kbase":
        for token in tokens[1:]:
            if token.startswith("-"):
                continue
            return f"{command} {token}"
    return command


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

    argv = _root_argv(ctx)
    command = _root_command(argv)
    session = start_debug_session(
        argv=argv,
        cwd=os.getcwd(),
        command=command,
    )
    ctx.obj["debug_session"] = session
    ctx.call_on_close(
        lambda: finish_debug_session(
            success=True,
            command=session.command,
        )
    )
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
