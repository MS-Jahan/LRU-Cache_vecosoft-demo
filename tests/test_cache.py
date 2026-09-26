"""Test suite for the LRU cache.

All tests exercise the public API only: ``LRUCache(capacity)``, ``get(key)``
and ``put(key, value, ttl=None)``.  Nothing here depends on how the cache is
implemented internally (dict + list, OrderedDict, linked list, ...).

TTL behavior is tested deterministically by monkeypatching ``time.monotonic``
with a controllable fake clock, so no test needs to sleep.
"""

import sys
import time
from typing import Callable, Dict

import pytest

from lru_cache.cache import LRUCache

MISS = -1  # The sentinel value ``get`` returns on a miss, per the public contract.


class FakeClock:
    """Controllable stand-in for ``time.monotonic``."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now: float = start

    def advance(self, seconds: float) -> None:
        """Move the fake clock forward by ``seconds``."""
        self.now += seconds

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    """Install a fake monotonic clock used by the implementation under test.

    Patches ``time.monotonic`` (covering ``import time`` style usage) and, as a
    defensive measure, any module-level ``monotonic`` re-export inside the
    cache module (covering ``from time import monotonic`` style usage).  This
    keeps TTL tests deterministic without sleeping.
    """
    fake = FakeClock()
    monkeypatch.setattr(time, "monotonic", fake)
    cache_module = sys.modules.get("lru_cache.cache")
    if cache_module is not None and hasattr(cache_module, "monotonic"):
        monkeypatch.setattr(cache_module, "monotonic", fake)
    return fake


class TestCapacity:
    """Constructor validation and basic capacity acceptance."""

    @pytest.mark.parametrize("bad_capacity", [0, -1, -5])
    def test_rejects_non_positive_capacity(self, bad_capacity: int) -> None:
        """Capacity must be strictly positive; otherwise ValueError is raised."""
        with pytest.raises(ValueError):
            LRUCache(bad_capacity)

    def test_accepts_minimum_capacity(self) -> None:
        """A capacity of 1 is valid and holds exactly one item."""
        cache: LRUCache = LRUCache(1)
        cache.put("a", 1)
        assert cache.get("a") == 1


class TestEviction:
    """LRU eviction on overflow, including eviction order."""

    def test_lru_item_evicted_on_overflow(self) -> None:
        """Filling a capacity-2 cache and inserting once more evicts the LRU key."""
        cache: LRUCache = LRUCache(2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)  # Overflow: "a" is least recently used.

        assert cache.get("a") == MISS
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_eviction_order_follows_recency_under_insertions(self) -> None:
        """get() refreshes recency, so a later insertion evicts B, not A."""
        cache: LRUCache = LRUCache(2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.get("a")  # "a" becomes MRU; "b" is now LRU.
        cache.put("c", 3)

        assert cache.get("b") == MISS
        assert cache.get("a") == 1
        assert cache.get("c") == 3

    def test_size_never_exceeds_capacity(self) -> None:
        """Under continuous insertions, only the oldest key at any time is lost."""
        cache: LRUCache = LRUCache(3)
        for i in range(10):
            cache.put(f"k{i}", i)

        for i in range(0, 7):  # k0..k6 were evicted, oldest first.
            assert cache.get(f"k{i}") == MISS
        for i in range(7, 10):
            assert cache.get(f"k{i}") == i


class TestUpdate:
    """put() on an existing key updates in place."""

    def test_update_replaces_value(self) -> None:
        """Re-putting an existing key replaces its stored value."""
        cache: LRUCache = LRUCache(2)
        cache.put("a", 1)
        cache.put("a", 99)
        assert cache.get("a") == 99

    def test_update_does_not_grow_size(self) -> None:
        """An update must not consume an extra slot.

        Verified behaviorally: at full capacity, updating an existing key and
        then inserting a new one must evict the (other) LRU key, not the just
        updated key.
        """
        cache: LRUCache = LRUCache(2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("b", 22)  # Update in place; size must stay 2.
        cache.put("c", 3)   # Evicts "a".

        assert cache.get("a") == MISS
        assert cache.get("b") == 22
        assert cache.get("c") == 3

    def test_update_marks_key_as_mru(self) -> None:
        """Updating an existing key refreshes its recency."""
        cache: LRUCache = LRUCache(2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("b", 22)  # "b" becomes MRU; "a" is now LRU.
        cache.put("c", 3)

        assert cache.get("a") == MISS
        assert cache.get("b") == 22
        assert cache.get("c") == 3


class TestAccessRefresh:
    """get() refreshes recency, moving items away from the eviction boundary."""

    def test_get_moves_item_away_from_eviction_boundary(self) -> None:
        """A read item survives an insertion that evicts a never-read neighbor."""
        cache: LRUCache = LRUCache(3)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        cache.get("a")  # Refresh "a"; eviction order is now b, c, a.
        cache.put("d", 4)

        assert cache.get("a") == 1
        assert cache.get("b") == MISS
        assert cache.get("c") == 3
        assert cache.get("d") == 4


class TestTTL:
    """TTL expiry semantics, all driven by the fake monotonic clock."""

    def test_unexpired_ttl_item_returns_value(self, clock: FakeClock) -> None:
        """An item whose TTL has not yet elapsed is still readable."""
        cache: LRUCache = LRUCache(2)
        cache.put("a", 1, ttl=10.0)
        clock.advance(9.999)
        assert cache.get("a") == 1

    def test_expired_item_returns_minus_one(self, clock: FakeClock) -> None:
        """Once the TTL elapses, get() reports a miss."""
        cache: LRUCache = LRUCache(2)
        cache.put("a", 1, ttl=5.0)
        clock.advance(5.0)
        assert cache.get("a") == MISS

    def test_expired_item_frees_capacity(self, clock: FakeClock) -> None:
        """An expired item no longer occupies a slot.

        After "a" expires, inserting "c" must fit without evicting the live
        item "b".
        """
        cache: LRUCache = LRUCache(2)
        cache.put("a", 1, ttl=5.0)
        cache.put("b", 2)
        clock.advance(10.0)  # "a" is now expired.
        cache.put("c", 3)

        assert cache.get("a") == MISS
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_ttl_update_rearms_expiry(self, clock: FakeClock) -> None:
        """Re-putting an existing key with a new TTL restarts its countdown."""
        cache: LRUCache = LRUCache(2)
        cache.put("a", 1, ttl=5.0)
        clock.advance(3.0)
        cache.put("a", 10, ttl=5.0)  # Re-armed: expires 5s from now, not in 2s.
        clock.advance(3.0)  # 6s since first put, but only 3s since re-arm.
        assert cache.get("a") == 10

        clock.advance(3.0)  # 6s since re-arm: now expired.
        assert cache.get("a") == MISS


class TestReinsertion:
    """Evicted keys can be re-inserted and behave like fresh entries."""

    def test_reinsert_after_eviction_works(self) -> None:
        """A key evicted earlier can be stored again with a fresh value."""
        cache: LRUCache = LRUCache(2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)  # Evicts "a".
        assert cache.get("a") == MISS

        cache.put("a", 42)  # Re-insert; evicts "b" (the LRU key now).
        assert cache.get("a") == 42
        assert cache.get("b") == MISS
        assert cache.get("c") == 3

    def test_reinserted_key_with_ttl_expires_fresh(self, clock: FakeClock) -> None:
        """A re-inserted key's TTL is independent of its earlier life."""
        cache: LRUCache = LRUCache(2)
        cache.put("a", 1, ttl=5.0)
        cache.put("b", 2)
        cache.put("c", 3)  # Evicts "a".
        clock.advance(2.0)
        cache.put("a", 10, ttl=5.0)  # Fresh TTL window starts now.
        clock.advance(4.0)  # 6s since the first put, 4s since the re-insert.
        assert cache.get("a") == 10


class TestHitsMisses:
    """Basic hit/miss behavior of get()."""

    def test_get_on_missing_key_returns_minus_one(self) -> None:
        """An unknown key yields the -1 miss sentinel."""
        cache: LRUCache = LRUCache(2)
        assert cache.get("missing") == MISS

    def test_get_returns_stored_value(self) -> None:
        """A stored key yields the exact stored value."""
        cache: LRUCache = LRUCache(2)
        cache.put("answer", 42)
        assert cache.get("answer") == 42

    def test_miss_get_does_not_disturb_recency(self) -> None:
        """A miss must not evict anything nor reorder survivors."""
        cache: LRUCache = LRUCache(2)
        cache.put("a", 1)
        cache.put("b", 2)
        assert cache.get("nope") == MISS
        cache.put("c", 3)  # Still "a" that gets evicted.

        assert cache.get("a") == MISS
        assert cache.get("b") == 2
        assert cache.get("c") == 3


class TestSentinelValue:
    """The documented ambiguity around storing -1 itself."""

    def test_storing_minus_one_is_indistinguishable_from_a_miss(self) -> None:
        """The public contract uses -1 as the miss sentinel.

        There is no way to distinguish a stored -1 from a miss through the
        public API: ``put("x", -1)`` followed by ``get("x")`` returns -1
        whether the item is present or not.  This test documents that
        behavior; it intentionally does NOT assert which internal branch
        produced the -1, only that the observable result is -1 in both the
        hit and the miss case.
        """
        cache: LRUCache = LRUCache(2)
        cache.put("x", -1)
        assert cache.get("x") == MISS  # Present, but reads back as -1 anyway.
        assert cache.get("y") == MISS  # Genuinely absent: same observable result.
