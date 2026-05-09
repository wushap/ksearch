"""Configuration management for ksearch package."""

import copy
import json
import os


DEFAULT_CONFIG = {
    "searxng_url": "http://localhost:48888",
    "store_dir": "~/.ksearch/store",
    "index_db": "~/.ksearch/index.db",
    "max_results": 10,
    "timeout": 30,
    "format": "markdown",
    "time_range": "",
    "no_cache": False,
    "only_cache": False,
    "only_kbase": False,
    "verbose": False,
    # Knowledge base settings
    "kbase_mode": "",  # "chroma", "qdrant", or "" (disabled)
    "kbase_dir": "~/.ksearch/kbase",
    "kbase_top_k": 5,
    "qdrant_url": "http://localhost:6333",
    # Embedding settings
    "embedding_mode": "ollama",
    "embedding_model": "nomic-embed-text",
    "embedding_dimension": 768,
    "ollama_url": "http://localhost:11434",
    # Iterative search settings
    "iterative_enabled": False,
    "max_iterations": 5,
    "max_time_seconds": 180,
    "fact_threshold": 0.7,
    "exploration_threshold": 0.4,
    "scoring_weights": {"vector": 0.4, "count": 0.3, "coverage": 0.3},
    # Hybrid search settings
    "hybrid_search": True,
    "rerank_enabled": True,
    "rerank_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "bm25_top_k": 20,
    "vector_top_k": 20,
    "rrf_k": 60,
    # Content optimization settings
    "optimization_enabled": False,
    "optimization_model": "gemma4:e2b",
    "optimization_max_iterations": 3,
    "optimization_confidence_threshold": 0.8,
    "optimization_max_time_seconds": 120,
    "optimization_temperature": 0.3,
}

LEGACY_KEY_ALIASES = {
    "kb_mode": "kbase_mode",
    "kb_dir": "kbase_dir",
    "kb_top_k": "kbase_top_k",
    "only_kb": "only_kbase",
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


def load_config(config_path: str = "~/.ksearch/config.json") -> dict:
    """Load config from file, return defaults if file doesn't exist."""
    config_path = expand_path(config_path)

    if not os.path.exists(config_path):
        return copy.deepcopy(DEFAULT_CONFIG)

    try:
        with open(config_path) as f:
            file_config = json.load(f)
        for legacy_key, current_key in LEGACY_KEY_ALIASES.items():
            if legacy_key in file_config and current_key not in file_config:
                file_config[current_key] = file_config[legacy_key]
        return file_config
    except json.JSONDecodeError:
        return copy.deepcopy(DEFAULT_CONFIG)


def merge_config(cli_args: dict, file_config: dict, defaults: dict) -> dict:
    """Merge configs with priority: CLI > file > defaults."""
    result = copy.deepcopy(defaults)

    for key, value in file_config.items():
        if key in result and value is not None:
            result[key] = value

    for key, value in cli_args.items():
        if key in result and value is not None:
            result[key] = value

    # Expand paths after merging
    for path_key in ["store_dir", "index_db", "kbase_dir"]:
        if path_key in result:
            result[path_key] = expand_path(result[path_key])

    return result
