"""Production LRU cache package with optional per-entry TTL support."""

from lru_cache.cache import LRUCache, ListNode

# Convenience alias: demo and test code may import the cache as ``Cache``.
Cache = LRUCache

__all__ = ["Cache", "LRUCache", "ListNode"]
