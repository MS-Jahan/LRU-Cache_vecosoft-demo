# Task 3 — Algorithm Explanation & Critical Thinking

## 1. Data structures used and why

I used a `dict` plus a custom doubly linked list with dummy head and tail nodes. The dict finds any key instantly. The list tracks recency, so move and remove are just pointer rewires. It must be doubly linked, since a singly linked list cannot unlink a middle node without searching.

## 2. Time and space complexity

Both `get` and `put` are O(1) on average: one dict lookup plus a few pointer changes, with no loops. Space is O(C) for capacity C, since at most C nodes and C dict entries exist.

## 3. Where it performs poorly

A one-time scan hurts it. Looping once over many new keys evicts hot keys. The cache ends up full of keys never read again, so hit rate drops. LRU assumes recent means reused, and scans break that.

## 4. AI suggestion I changed

AI suggested `time.time()` with real `sleep` in TTL tests. I switched to `time.monotonic()` with a fake clock. Wall-clock time can jump and break expiry. Real sleeps are also slow and flaky.
