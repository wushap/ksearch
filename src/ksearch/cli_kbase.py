"""Compatibility layer for kbase CLI registration."""

from ksearch.cli import kbase as _kbase

KnowledgeBase = _kbase.KnowledgeBase


class _CompatProxy:
    """Call through to the mutable legacy module symbol at runtime."""

    def __call__(self, *args, **kwargs):
        return KnowledgeBase(*args, **kwargs)


def register_kbase_commands(kbase_app):
    _kbase.KnowledgeBase = _CompatProxy()
    return _kbase.register_kbase_commands(kbase_app)

__all__ = ["KnowledgeBase", "register_kbase_commands"]
