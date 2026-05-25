"""
cache.py
========
Lightweight disk-backed JSON cache for Google Maps Distance Matrix results.
Keyed on (origin, destination, departure_datetime_iso).
Prevents repeat API charges on re-runs.
"""

import hashlib
import json
import os
from datetime import datetime
from typing import Any, Optional

from .config import CACHE_DIR


def _ensure_dir() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)


def cache_key(origin: str, destination: str, departure_dt: datetime) -> str:
    """Return a filesystem-safe hash key for the query triple."""
    raw = f"{origin}|{destination}|{departure_dt.isoformat()}"
    return hashlib.sha1(raw.encode()).hexdigest()


def load(key: str) -> Optional[dict]:
    """Return cached dict for key, or None if not present."""
    _ensure_dir()
    path = os.path.join(CACHE_DIR, f"{key}.json")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)


def save(key: str, data: Any) -> None:
    """Persist data as JSON for key."""
    _ensure_dir()
    path = os.path.join(CACHE_DIR, f"{key}.json")
    with open(path, "w") as fh:
        json.dump(data, fh)


def invalidate(key: str) -> None:
    """Delete a single cache entry (force re-fetch)."""
    path = os.path.join(CACHE_DIR, f"{key}.json")
    if os.path.exists(path):
        os.remove(path)


def clear_all() -> int:
    """Delete every cached entry. Returns count of deleted files."""
    _ensure_dir()
    count = 0
    for fname in os.listdir(CACHE_DIR):
        if fname.endswith(".json"):
            os.remove(os.path.join(CACHE_DIR, fname))
            count += 1
    return count


def cache_size() -> dict:
    """Return count and total size (bytes) of cached entries."""
    _ensure_dir()
    files = [f for f in os.listdir(CACHE_DIR) if f.endswith(".json")]
    total = sum(os.path.getsize(os.path.join(CACHE_DIR, f)) for f in files)
    return {"count": len(files), "bytes": total}
