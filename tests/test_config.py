"""Tests for kb.config module."""

import json
import tempfile
import os
from pathlib import Path

from kb.config import (
    DEFAULT_CONFIG,
    load_config,
    merge_config,
    init_default_config,
)


def test_default_config_structure():
    assert "searxng_url" in DEFAULT_CONFIG
    assert "store_dir" in DEFAULT_CONFIG
    assert DEFAULT_CONFIG["max_results"] == 10
    assert DEFAULT_CONFIG["format"] == "markdown"


def test_init_default_config():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "config.json")
        init_default_config(config_path)

        assert os.path.exists(config_path)
        with open(config_path) as f:
            config = json.load(f)
        assert config == DEFAULT_CONFIG


def test_load_config_existing_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "config.json")
        custom_config = {"searxng_url": "http://custom:8888", "max_results": 5}
        with open(config_path, "w") as f:
            json.dump(custom_config, f)

        result = load_config(config_path)
        assert result["searxng_url"] == "http://custom:8888"
        assert result["max_results"] == 5


def test_load_config_missing_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "nonexistent.json")
        result = load_config(config_path)
        assert result == DEFAULT_CONFIG


def test_merge_config_cli_overrides_file():
    file_config = {"searxng_url": "http://file:8888", "max_results": 5}
    cli_args = {"max_results": 20}

    result = merge_config(cli_args, file_config, DEFAULT_CONFIG)
    assert result["searxng_url"] == "http://file:8888"
    assert result["max_results"] == 20


def test_merge_config_file_overrides_default():
    file_config = {"timeout": 60}
    cli_args = {}

    result = merge_config(cli_args, file_config, DEFAULT_CONFIG)
    assert result["timeout"] == 60
    assert result["max_results"] == 10  # from default