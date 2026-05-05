"""CLI command registration package for ksearch."""

from ksearch.cli.kbase import register_kbase_commands
from ksearch.cli.search import register_search_command
from ksearch.cli.system import (
    register_config_command,
    register_health_command,
    register_stats_command,
)

__all__ = [
    "register_config_command",
    "register_health_command",
    "register_kbase_commands",
    "register_search_command",
    "register_stats_command",
]
