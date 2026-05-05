"""Compatibility layer for search CLI registration."""

from ksearch.cli import search as _search

SearchEngine = _search.SearchEngine


class _CompatProxy:
    """Call through to the mutable legacy module symbol at runtime."""

    def __call__(self, *args, **kwargs):
        return SearchEngine(*args, **kwargs)


def register_search_command(app):
    _search.SearchEngine = _CompatProxy()
    return _search.register_search_command(app)

__all__ = ["SearchEngine", "register_search_command"]
