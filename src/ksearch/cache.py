"""Compatibility facade for cache persistence components."""

from ksearch.cache_layer.repository import TIME_RANGE_SQL, VALID_TIME_RANGES, normalize_engine_names
from ksearch.cache_layer.service import CacheManager
from ksearch.cache_layer.store import hash_url

__all__ = [
    "TIME_RANGE_SQL",
    "VALID_TIME_RANGES",
    "CacheManager",
    "hash_url",
    "normalize_engine_names",
]
