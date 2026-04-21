"""Configuration management for kb package."""

import json
import os
from pathlib import Path


DEFAULT_CONFIG = {
    "searxng_url": "http://localhost:48888",
    "store_dir": "~/.kb/store",
    "index_db": "~/.kb/index.db",
    "max_results": 10,
    "timeout": 30,
    "format": "markdown",
    "time_range": "",
    "no_cache": False,
    "only_cache": False,
    "verbose": False,
}


def expand_path(path: str) -> str:
    """Expand ~ and environment variables in path."""
    return os.path.expanduser(os.path.expandvars(path))


def init_default_config(config_path: str) -> None:
    """Create default config file if it doesn't exist."""
    config_path = expand_path(config_path)
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)


def load_config(config_path: str = "~/.kb/config.json") -> dict:
    """Load config from file, return defaults if file doesn't exist."""
    config_path = expand_path(config_path)

    if not os.path.exists(config_path):
        return DEFAULT_CONFIG.copy()

    try:
        with open(config_path) as f:
            file_config = json.load(f)
        return file_config
    except json.JSONDecodeError:
        return DEFAULT_CONFIG.copy()


def merge_config(cli_args: dict, file_config: dict, defaults: dict) -> dict:
    """Merge configs with priority: CLI > file > defaults."""
    result = defaults.copy()

    for key, value in file_config.items():
        if key in result and value is not None:
            result[key] = value

    for key, value in cli_args.items():
        if key in result and value is not None:
            result[key] = value

    # Expand paths after merging
    for path_key in ["store_dir", "index_db"]:
        if path_key in result:
            result[path_key] = expand_path(result[path_key])

    return result