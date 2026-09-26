"""Runnable demo for the LRU Cache with optional TTL support.

Run with:  python demo.py
Requires:  Python 3.10+ (no third-party dependencies).
"""

import time

from lru_cache import Cache

LINE = "=" * 62


def header(title: str) -> None:
    print()
    print(LINE)
    print(title)
    print(LINE)


def show(description: str, result) -> None:
    print(f"  {description:<42} -> {result}")


def section_1_core_lru() -> None:
    header("SECTION 1 | Core LRU Behavior (capacity = 2)")
    cache = Cache(2)

    show('put("A", 10)', cache.put("A", 10))
    show('put("B", 20)', cache.put("B", 20))
    show('get("A")          [A becomes MRU]', cache.get("A"))
    show('put("C", 30)      [cache full: evicts "B"]', cache.put("C", 30))
    show('get("B")          [B was evicted]', cache.get("B"))
    show('get("C")', cache.get("C"))
    show('get("A")', cache.get("A"))


def section_2_ttl_expiration() -> None:
    header("SECTION 2 | TTL Expiration (lazy, ttl = 1.5s)")
    cache = Cache(2)

    start = time.monotonic()
    cache.put("session", "token-xyz", ttl=1.5)
    show('put("session", "token-xyz", ttl=1.5)', "ok")

    value = cache.get("session")
    elapsed = time.monotonic() - start
    show(f'get("session")     [{elapsed:.2f}s elapsed, not expired]', value)

    print("  ... sleeping 1.6 seconds ...")
    time.sleep(1.6)

    elapsed = time.monotonic() - start
    value = cache.get("session")
    show(f'get("session")     [{elapsed:.2f}s elapsed, expired]', value)


def section_3_capacity_invariant() -> None:
    header("SECTION 3 | Bonus: Update Does Not Evict")
    cache = Cache(2)
    cache.put("A", 1)
    cache.put("B", 2)

    cache.put("A", 100)  # update existing key, cache stays at size 2
    show('put("A", 100)     [update, size stays 2]', "ok")
    show('get("B")          [B still present, nothing evicted]', cache.get("B"))
    show('get("A")          [value updated in place]', cache.get("A"))


def main() -> None:
    print(LINE)
    print("  LRU CACHE DEMO  |  O(1) get/put  +  TTL expiration")
    print(LINE)

    section_1_core_lru()
    section_2_ttl_expiration()
    section_3_capacity_invariant()

    header("DONE | All sections completed successfully")


if __name__ == "__main__":
    main()
