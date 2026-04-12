"""Simple in-memory TTL cache shared across route modules.

Keys   : arbitrary hashable tuples (e.g. (stock_id, start, end))
Values : any serialisable dict
TTL    : 30 minutes by default

No external dependencies. Cache is process-local and cleared on restart,
which is acceptable for a personal single-user tool.

Usage
-----
    from web.cache import cache

    hit = cache.get(("2330", "2024-01-01", "2026-01-01"))
    if hit is not None:
        return hit

    result = expensive_computation()
    cache.set(("2330", "2024-01-01", "2026-01-01"), result)
    return result
"""

from __future__ import annotations

import time
from typing import Any

_DEFAULT_TTL = 30 * 60   # 30 minutes


class _TTLCache:
    def __init__(self, ttl: int = _DEFAULT_TTL) -> None:
        self._ttl   = ttl
        self._store: dict[tuple, tuple[float, Any]] = {}

    def get(self, key: tuple) -> Any | None:
        """Return cached value or None if missing / expired."""
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.monotonic() - ts > self._ttl:
            del self._store[key]
            return None
        return value

    def set(self, key: tuple, value: Any) -> None:
        self._store[key] = (time.monotonic(), value)

    def invalidate(self, stock_id: str) -> None:
        """Remove all entries for a given stock_id (first element of key)."""
        keys = [k for k in self._store if k[0] == stock_id]
        for k in keys:
            del self._store[k]

    def clear(self) -> None:
        self._store.clear()


# Single shared instance imported by route modules
cache = _TTLCache()
