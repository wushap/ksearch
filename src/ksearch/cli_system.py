"""Compatibility layer for system/admin CLI registration."""

from ksearch.cli import system as _system

CacheManager = _system.CacheManager
EmbeddingGenerator = _system.EmbeddingGenerator
KnowledgeBase = _system.KnowledgeBase


class _CompatProxy:
    """Call through to the mutable legacy module symbol at runtime."""

    def __init__(self, symbol_name: str):
        self.symbol_name = symbol_name

    def __call__(self, *args, **kwargs):
        return globals()[self.symbol_name](*args, **kwargs)


def register_stats_command(app):
    _system.CacheManager = _CompatProxy("CacheManager")
    _system.KnowledgeBase = _CompatProxy("KnowledgeBase")
    return _system.register_stats_command(app)


def register_config_command(app):
    return _system.register_config_command(app)


def register_health_command(app):
    _system.EmbeddingGenerator = _CompatProxy("EmbeddingGenerator")
    return _system.register_health_command(app)

__all__ = [
    "CacheManager",
    "EmbeddingGenerator",
    "KnowledgeBase",
    "register_config_command",
    "register_health_command",
    "register_stats_command",
]
