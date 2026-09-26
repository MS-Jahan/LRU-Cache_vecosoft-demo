# LRU Cache — Production-Grade Python Implementation

A thread-clean, dependency-free implementation of an **LRU (Least Recently Used) cache** with guaranteed **O(1) average time** for both `get` and `put`, plus an optional **Time-To-Live (TTL)** expiration feature implemented via lazy expiration.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture & Data Structures](#architecture--data-structures)
3. [Complexity Analysis](#complexity-analysis)
4. [Bonus Feature: TTL Expiration](#bonus-feature-ttl-expiration)
5. [Setup & Execution](#setup--execution)
6. [Running Tests in Docker (Optional)](#running-tests-in-docker-optional)
7. [Project Structure](#project-structure)
8. [API Reference](#api-reference)

---

## System Overview

An LRU cache is a fixed-capacity key-value store that evicts the **least recently used** entry when it is full and a new entry must be inserted. "Used" means either written (`put`) or read (`get`); every successful operation promotes the touched key to the **most recently used** (MRU) position.

The core policy assumption is temporal locality: *if a key was accessed recently, it is likely to be accessed again soon*. When memory is bounded, discarding the oldest-accessed data preserves the working set that is statistically most likely to be reused.

### Real-World Use Cases

| Domain | How LRU is applied |
|---|---|
| **OS page replacement** | The Linux kernel's page cache and swap logic (e.g., approximate LRU via active/inactive LRU lists) evicts pages least likely to be re-referenced, keeping the process working set resident. |
| **CDNs / reverse proxies** | Nginx, Varnish, and commercial CDNs keep hot media objects at the edge. Under cache pressure, the least recently requested object is evicted first, maximizing hit ratio for popular content. |
| **Database query caching** | MySQL's query cache (historically) and in-process caches such as Redis (with `allkeys-lru` eviction) or Memcached store recently issued query results, absorbing repeated reads without touching disk. |
| **Application-level memoization** | Connection pools, session stores, and deserialized-object caches use LRU to bound memory while keeping hot objects in process. |

---

## Architecture & Data Structures

A naive LRU built on a plain list pays O(n) per operation (linear search + shift). A naive build on a min-heap by access time pays O(log n). The classic solution combines two structures so that **every required step is constant time**:

| Structure | Responsibility | Why it is needed |
|---|---|---|
| **Hash map** (`dict`) | `key → node` lookup | O(1) average membership test and retrieval; no traversal to find an entry. |
| **Doubly linked list** | Recency ordering | O(1) unlink/insert of any node given a direct reference — no traversal, and a node's neighbors are known from the node itself. |

A **doubly** linked list is required because a node must be removed given only the node pointer. A singly linked list can unlink in O(1) only if the *previous* node is already known, which would force an O(n) search.

### Layout Diagram

```
        dummy HEAD (MRU side)                      dummy TAIL (LRU side)
        ┌────────┐   next   ┌────────┐   next   ┌────────┐   next   ┌────────┐
        │ head ■■│─────────▶│ Node C │─────────▶│ Node A │─────────▶│ ■■ tail│
        │ (guard)│◀─────────│ val 30 │◀─────────│ val 10 │◀─────────│ (guard)│
        └────────┘   prev   └────────┘   prev   └────────┘   prev   └────────┘
                        ▲                        ▲
                        │                        │
   dict: { "C": ────────┘         "A": ─────────┘        (key → node pointer)
           "B": ✗  (evicted) }

   Direction of recency:   head ─────────────────────────────▶ tail
                          MRU (freshest access)            LRU (next eviction)
```

Key properties of the layout:

* **Dummy (sentinel) `head` and `tail` nodes** eliminate all edge-case `None` checks: the list is never truly empty, so "insert at front" and "remove from back" are unconditional pointer rewires with no special-casing of the first/last element.
* **MRU lives immediately behind the dummy `head`**; a `get` or a fresh `put` moves/inserts the node there.
* **LRU lives immediately before the dummy `tail`**; when capacity is exceeded, that node is unlinked and its key deleted from the dict in O(1).
* The **hash map stores direct node references**, which is what makes the O(1) unlink possible: `dict[key]` *is* the node, so no list traversal is ever needed.

### Operation Flow

```
get(key)
  ├─ key not in dict ──────────────▶ return -1
  ├─ entry expired (TTL) ──────────▶ unlink node, del dict[key], return -1
  └─ hit ──▶ unlink node, relink after head, return value

put(key, value, ttl=None)
  ├─ key in dict ──▶ update value/TTL, move node to MRU
  ├─ key new, size == capacity ──▶ unlink LRU (before tail), del dict[lru_key]
  └─ insert new node at MRU, dict[key] = node
```

---

## Complexity Analysis

### Time: O(1) average for `get` and `put`

Every operation decomposes into a fixed number of constant-time primitives:

| Step | Cost | Justification |
|---|---|---|
| Hash map lookup (`key in dict`, `dict[key]`) | O(1) avg | Python `dict` is a hash table; expected O(1), worst case O(n) only under pathological hash collisions. |
| Unlink a node from the list | O(1) | Rewiring `node.prev.next` and `node.next.prev` — two assignments, no traversal. |
| Insert node after dummy head (MRU) | O(1) | Four pointer assignments using the sentinels. |
| Evict LRU node | O(1) | `tail.prev` is the victim by construction; one unlink plus one `del dict[key]`. |
| Update-in-place on `put` of an existing key | O(1) | Value assignment + move-to-front, both constant. |

Since `get` and `put` each perform at most **one dict operation plus a constant number of pointer rewires**, total cost is O(1) average time, independent of cache size. No loops, recursion, or searches appear anywhere on the hot path.

### Space: O(C)

The cache holds at most `C` entries at any moment (the eviction step fires before a `C+1`-th entry survives). Each entry contributes:

* one hash-map slot (`key → node`),
* one `ListNode` (value + `prev` + `next` pointers),
* one key reference stored in the node.

All three terms are bounded by `C`, so total auxiliary space is **O(C)**, where `C = capacity`. The sentinel head/tail nodes add two nodes — constant, hence O(1) overhead.

---

## Bonus Feature: TTL Expiration

`put` accepts an optional `ttl` (seconds). Entries with a TTL become invalid after that window.

### Lazy Expiration Strategy

This implementation uses **lazy (passive) expiration**: expiry is checked only when the entry is touched.

* **On `get`:** if the entry exists but `monotonic() - stored_at > ttl`, the node is unlinked, the dict entry deleted, and `-1` returned — the caller sees the same result as a cache miss.
* **On `put`:** writing over an existing entry replaces its value, TTL, and timestamp; a newly inserted key naturally overwrites any stale state.

`time.monotonic()` is used rather than `time.time()` so that wall-clock adjustments (NTP syncs, DST, manual changes) can never make an entry appear unexpired after expiring, or vice versa.

The payoff: expiration adds **zero overhead to every other operation** — no timers, no threads, no scans. The trade-off is that an expired entry that is never touched again keeps occupying memory until it is evicted by LRU pressure.

### Lazy vs. Background Sweeper — Trade-offs

| Criterion | Lazy expiration (this project) | Background sweeper (active) |
|---|---|---|
| **CPU overhead** | Zero — checks only on access | Continuous — periodic scans of the key space (or sampling) consume CPU even when idle |
| **Memory retention** | Expired-but-untouched entries linger until evicted by capacity pressure | Expired entries are reclaimed promptly, bounding memory closer to the live working set |
| **Read latency** | One timestamp comparison per `get`/`put` — negligible and deterministic | Scan runs off the request path, but can compete for locks/CPU and add jitter under load |
| **Implementation complexity** | Trivial — a conditional in the hot path | Requires a scheduler thread or timer wheel, thread-safety around the shared list/dict, and lifecycle management |
| **Suitability** | Read-heavy workloads, small-to-medium caches, single-process demos | Large caches with many short-TTL entries that are rarely re-read (e.g., massive session stores) |

The lazy approach is the same strategy used by Memcached by default, and Redis layers it with a light probabilistic active sweep — a hybrid that recovers the memory-reclamation benefit without full-scan CPU cost.

---

## Setup & Execution

Requires **Python 3.10+**. No third-party packages are needed to run the demo.

### 1. Create and activate a virtual environment

**Linux / macOS**

```bash
python -m venv venv
source venv/bin/activate
```

**Windows (PowerShell)**

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

**Windows (cmd.exe)**

```bat
python -m venv venv
venv\Scripts\activate.bat
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

(Installs `pytest` for the test suite only.)

### 3. Run the demo

```bash
python demo.py
```

Expected output: three clearly separated sections — the canonical LRU sequence, TTL expiration, and the update-does-not-evict invariant.

### 4. Run the test suite

```bash
pytest -v
```

---

## Running Tests in Docker (Optional)

The development workflow optionally runs the suite inside an official Python image, so results are reproducible regardless of the host interpreter. From the project root:

```bash
docker run --rm -v "$(pwd)":/app -w /app python:3.11-slim \
    sh -c "pip install -r requirements.txt && pytest -v"
```

**Windows (PowerShell)** equivalent:

```powershell
docker run --rm -v "${PWD}:/app" -w /app python:3.11-slim `
    sh -c "pip install -r requirements.txt && pytest -v"
```

Notes:

* `--rm` discards the container after the run; the host directory is bind-mounted read-write at `/app`, so results appear locally.
* To run the demo in Docker instead of pytest, replace the command: `sh -c "python demo.py"` (TTL section sleeps ~1.6 s).

---

## Project Structure

```text
.
├── .gitignore              # Python-standard ignores (venv, caches, dist, .env)
├── requirements.txt        # pytest>=7.0 (test-only dependency)
├── README.md               # This document
├── lru_cache/
│   ├── __init__.py         # Public API: exports Cache
│   └── cache.py            # ListNode, LRUCache core implementation
├── demo.py                 # Runnable terminal demo (Sections 1-3)
├── tests/
│   ├── __init__.py
│   └── test_cache.py       # pytest suite: capacity, eviction, TTL, access refresh
└── docs/                   # Project planning / design documents
```

---

## API Reference

### `Cache` (alias of `LRUCache`)

| Member | Signature | Returns / Raises | Behavior |
|---|---|---|---|
| Constructor | `Cache(capacity: int)` | raises `ValueError` if `capacity <= 0` | Creates an empty cache holding at most `capacity` entries. Initializes sentinel head/tail nodes and the key-to-node hash map. |
| `get` | `get(key: Any) -> Any` | stored value, or `-1` on miss/expiration | If the key exists and is unexpired: unlinks its node, relinks it at the MRU position (behind dummy head), and returns the value. On a miss or TTL expiry: returns `-1` (expired entries are removed from both structures first). |
| `put` | `put(key: Any, value: Any, ttl: Optional[float] = None) -> None` | `None` | Inserts or updates `key`. If the key exists: updates value/TTL/timestamp and moves the node to MRU — **the cache size does not grow**. If the key is new and the cache is full: evicts the LRU entry (node before dummy tail) and deletes it from the map before inserting. Passing `ttl` makes the entry expire lazily after `ttl` seconds. |

#### Usage Example

```python
from lru_cache import Cache

cache = Cache(2)
cache.put("A", 10)
cache.put("B", 20)
cache.get("A")                 # 10  -> "A" becomes MRU
cache.put("C", 30)             # cache full -> evicts "B" (LRU)
cache.get("B")                 # -1  (evicted)
cache.get("C")                 # 30
cache.put("token", "x", ttl=1.5)
cache.get("token")             # "x" before expiry; -1 after 1.5 s
```

---

## License

Educational demonstration project.
