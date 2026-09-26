"""Production LRU cache with optional per-entry TTL.

Implements an O(1) average get/put cache backed by a dict for key lookup
and a custom doubly linked list (built from scratch) for recency order.
Expiry is lazy: entries are checked and evicted on access via get/put.
"""

from __future__ import annotations

import time
from typing import Any, Optional


class ListNode:
    """A node in the cache's doubly linked list.

    Sentinel nodes (dummy head and tail) hold no key/value data.

    Attributes:
        key: The cache key this node holds (``None`` for sentinels).
        value: The cached value (``None`` for sentinels).
        expires_at: Monotonic timestamp after which the entry is stale,
            or ``None`` when the entry never expires.
        prev: The neighbouring node toward the MRU side.
        next: The neighbouring node toward the LRU side.
    """

    __slots__ = ("key", "value", "expires_at", "prev", "next")

    def __init__(
        self,
        key: Any = None,
        value: Any = None,
        expires_at: Optional[float] = None,
    ) -> None:
        self.key = key
        self.value = value
        self.expires_at = expires_at
        self.prev: Optional[ListNode] = None
        self.next: Optional[ListNode] = None


class LRUCache:
    """A fixed-capacity least-recently-used cache with optional TTL.

    Ordering invariants (MRU at the dummy head, LRU at the dummy tail):

        head <-> most recently used <-> ... <-> least recently used <-> tail

    Args:
        capacity: Maximum number of live entries. Must be a positive integer.

    Raises:
        ValueError: If ``capacity`` is not a positive integer.
    """

    def __init__(self, capacity: int) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool):
            raise ValueError(
                f"capacity must be a positive integer, got {capacity!r}"
            )
        if capacity <= 0:
            raise ValueError(f"capacity must be a positive integer, got {capacity!r}")

        self._capacity: int = capacity
        self._nodes: dict[Any, ListNode] = {}

        # Sentinels: head is the MRU side, tail is the LRU side.
        self._head: ListNode = ListNode()
        self._tail: ListNode = ListNode()
        self._head.next = self._tail
        self._tail.prev = self._head

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def get(self, key: Any) -> Any:
        """Return the value for ``key``, or ``-1`` if absent or expired.

        A successful lookup moves the entry to the MRU position (right
        after the dummy head). An expired entry is removed from the list
        and dict, freeing capacity for future inserts.

        Args:
            key: The key to look up.

        Returns:
            The cached value, or ``-1`` on miss/expiry.
        """
        node = self._nodes.get(key)
        if node is None:
            return -1

        if self._is_expired(node):
            self._evict_node(node)
            return -1

        self._move_to_front(node)
        return node.value

    def put(self, key: Any, value: Any, ttl: Optional[float] = None) -> None:
        """Insert or update ``key`` with ``value`` and mark it most recent.

        Updating an existing key replaces its value/ttl and promotes it to
        the MRU position. Inserting a new key beyond capacity evicts the
        LRU entry first. Expired entries encountered during the lookup are
        removed lazily.

        Args:
            key: The key to insert or update.
            value: The value to store.
            ttl: Time-to-live in seconds. ``None`` means the entry never
                expires; zero or negative values are rejected.

        Raises:
            ValueError: If ``ttl`` is not ``None`` and is <= 0.
        """
        if ttl is not None and ttl <= 0:
            raise ValueError(f"ttl must be a positive number of seconds, got {ttl!r}")

        expires_at = None if ttl is None else time.monotonic() + ttl

        node = self._nodes.get(key)
        if node is not None:
            if self._is_expired(node):
                # The stored entry is stale: treat the put as a fresh insert.
                self._evict_node(node)
                node = None
            else:
                node.value = value
                node.expires_at = expires_at
                self._move_to_front(node)
                return

        if len(self._nodes) >= self._capacity:
            self._evict_lru()

        new_node = ListNode(key, value, expires_at)
        self._nodes[key] = new_node
        self._add_front(new_node)

    # ------------------------------------------------------------------ #
    # Linked-list helpers (O(1) primitives)
    # ------------------------------------------------------------------ #

    def _add_front(self, node: ListNode) -> None:
        """Insert ``node`` right after the dummy head (MRU position)."""
        first = self._head.next
        assert first is not None  # Sentinels are never unlinked.
        node.prev = self._head
        node.next = first
        first.prev = node
        self._head.next = node

    def _remove(self, node: ListNode) -> None:
        """Unlink ``node`` from the list and clear its pointers."""
        prev, nxt = node.prev, node.next
        assert prev is not None and nxt is not None
        prev.next = nxt
        nxt.prev = prev
        node.prev = None
        node.next = None

    def _move_to_front(self, node: ListNode) -> None:
        """Promote ``node`` to the MRU position."""
        self._remove(node)
        self._add_front(node)

    def _evict_lru(self) -> None:
        """Remove the least recently used entry (node before the tail)."""
        lru = self._tail.prev
        assert lru is not None and lru is not self._head, "evict on empty cache"
        self._evict_node(lru)

    def _evict_node(self, node: ListNode) -> None:
        """Remove ``node`` from both the linked list and the key dict."""
        self._remove(node)
        del self._nodes[node.key]

    # ------------------------------------------------------------------ #
    # Expiry helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _is_expired(node: ListNode) -> bool:
        """Return ``True`` when ``node`` has a past expiry timestamp."""
        return node.expires_at is not None and time.monotonic() >= node.expires_at
