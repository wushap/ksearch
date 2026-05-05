"""Focused web extraction/search package.

Keep imports lazy so search-client-only use does not require extractor deps.
"""

from importlib import import_module


_EXPORT_TO_MODULE = {
    "clean_content": "ksearch.web.cleaner",
    "ContentConverter": "ksearch.web.extractor",
    "SearXNGClient": "ksearch.web.search_client",
    "should_skip_url": "ksearch.web.url_policy",
}

__all__ = [
    "clean_content",
    "ContentConverter",
    "SearXNGClient",
    "should_skip_url",
]


def __getattr__(name: str):
    if name not in _EXPORT_TO_MODULE:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(_EXPORT_TO_MODULE[name])
    return getattr(module, name)
