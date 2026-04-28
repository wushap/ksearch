"""Tests for kbase.config module."""

import json
import tempfile
import os
from pathlib import Path

from kbase.config import (
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
    assert DEFAULT_CONFIG["store_dir"] == "~/.kbase/store"
    assert DEFAULT_CONFIG["index_db"] == "~/.kbase/index.db"
    assert DEFAULT_CONFIG["kbase_dir"] == "~/.kbase/kbase"
    assert DEFAULT_CONFIG["iterative_enabled"] is False
    assert DEFAULT_CONFIG["embedding_dimension"] == 768
    assert DEFAULT_CONFIG["max_iterations"] == 5
    assert DEFAULT_CONFIG["fact_threshold"] == 0.7
    assert DEFAULT_CONFIG["exploration_threshold"] == 0.4
    assert DEFAULT_CONFIG["scoring_weights"] == {
        "vector": 0.4,
        "count": 0.3,
        "coverage": 0.3,
    }


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


def test_merge_config_preserves_iterative_defaults():
    result = merge_config({}, {}, DEFAULT_CONFIG)

    assert result["iterative_enabled"] is False
    assert result["max_iterations"] == 5
    assert result["max_time_seconds"] == 180
    assert result["fact_threshold"] == 0.7
    assert result["exploration_threshold"] == 0.4


def test_merge_config_applies_iterative_cli_override():
    file_config = {"kbase_mode": "chroma"}
    cli_args = {"iterative_enabled": True, "max_iterations": 2}

    result = merge_config(cli_args, file_config, DEFAULT_CONFIG)

    assert result["iterative_enabled"] is True
    assert result["max_iterations"] == 2
    assert result["kbase_mode"] == "chroma"


def test_merge_config_preserves_embedding_dimension_override():
    file_config = {"embedding_dimension": 1024}
    cli_args = {"embedding_dimension": 768}

    result = merge_config(cli_args, file_config, DEFAULT_CONFIG)

    assert result["embedding_dimension"] == 768


def test_load_config_maps_legacy_only_kb_key():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "config.json")
        with open(config_path, "w") as f:
            json.dump({"only_kb": True}, f)

        result = load_config(config_path)

        assert result["only_kbase"] is True


def test_merge_config_preserves_only_kbase_setting():
    result = merge_config({}, {"only_kbase": True}, DEFAULT_CONFIG)

    assert result["only_kbase"] is True
