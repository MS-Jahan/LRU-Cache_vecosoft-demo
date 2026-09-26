# Implementation Decisions — LRU Cache Demo

Date: 2026-09-26
Source spec: [2026-09-26-init.md](2026-09-26-init.md)

Record of design decisions made while building the LRU cache repository, where
the spec left room for judgment.

---

## 1. Data Structures

| Decision | Detail |
|---|---|
| Hash map | Plain `dict` (`Any -> ListNode`) for O(1) key lookup. |
| Linked list | Custom doubly linked list built from scratch — no `OrderedDict`, no `functools.lru_cache`, per spec. |
| Sentinels | Dummy `head` (MRU side) and dummy `tail` (LRU side); removals never need None-checks at edges. |
| Node storage | `ListNode` uses `__slots__` (`key`, `value`, `expires_at`, `prev`, `next`) — lower memory per node, matches production style. |
| Class names | `ListNode` + `LRUCache` per spec; `Cache = LRUCache` alias exported from `lru_cache/__init__.py` since the spec's demo uses `Cache(2)`. |

## 2. API & Behavior Choices

- **`get` returns `-1` on miss and on expiry** — spec mandates this sentinel.
  Consequence (documented in tests, `TestSentinelValue`): storing `-1` as a
  value is indistinguishable from a miss. Accepted; contract comes from spec.
- **`put` signature** is `put(key, value, ttl: Optional[float] = None)` — the
  spec named the parameter `ttl`, kept as-is.
- **`ttl <= 0` raises `ValueError`** — a zero/negative TTL is a caller bug, not
  "instantly expired". `ttl=None` means never expires.
- **Capacity validation** rejects `capacity <= 0` with `ValueError` per spec;
  also rejects non-int (e.g. `2.5`, `True`) since a float capacity is a caller
  bug.
- **Eviction happens only after a *new* key insert at capacity**; updating an
  existing key never evicts (spec behavior, covered by demo section 3 and
  `TestUpdate`).

## 3. TTL Strategy

- **Lazy expiration only** — expiry checked inside `get`/`put` via
  `time.monotonic()`. No background sweeper thread. Trade-offs (CPU vs memory
  retention) analyzed in `README.md`.
- **`time.monotonic()` over `time.time()`** — immune to wall-clock jumps (NTP
  corrections), correct domain for measuring elapsed time.
- **Put over an expired entry** is treated as a fresh insert: the stale node is
  evicted first, so the new value gets a clean slot and correct TTL.

## 4. Testing Choices

- **Deterministic TTL tests** — a `FakeClock` fixture monkeypatches
  `time.monotonic`; no real sleeps in the suite. Full suite runs in ~0.03 s.
- **Public API only** — no test touches internal list pointers; suite would
  pass against any contract-conformant implementation.
- **Coverage**: capacity validation (parametrized), eviction correctness and
  order, update-in-place (size invariant verified behaviorally), access
  refresh, TTL expiry / capacity reclaim / re-arm, re-insertion after eviction,
  hit/miss, `-1` sentinel ambiguity. 21 collected tests, all passing.

## 5. Tooling & Verification

- **Python 3.10+** target; verified on 3.11 in Docker (`python:3.11-slim`).
- **Verification** performed inside Docker per project convention:
  `pytest` → 21 passed; `python demo.py` → all three sections print expected
  values and exit 0.
- **`requirements.txt`** lists only `pytest>=7.0` — runtime has zero
  dependencies (stdlib only).

## 6. Documentation

- `README.md` covers overview, architecture with ASCII diagrams, O(1) proof,
  TTL trade-off table, venv setup (Linux + Windows), Docker test section, API
  reference.
- This file follows the `docs/` naming convention `YYYY-MM-DD-slug.md`.
