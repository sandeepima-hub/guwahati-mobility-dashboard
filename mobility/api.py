"""
api.py
======
Thin wrapper around the Google Maps Distance Matrix API.
Every call is cache-backed.  Raises on non-OK status so callers can decide
whether to skip, retry, or abort.
"""

import time
import googlemaps
from datetime import datetime
from typing import Optional

from .config import API_SLEEP_S
from . import cache as _cache


class DistanceMatrixError(Exception):
    """Raised when the API returns a non-OK element status."""
    pass


def build_client(api_key: str) -> googlemaps.Client:
    """Construct and return a googlemaps.Client."""
    return googlemaps.Client(key=api_key)


def query_segment(
    client: googlemaps.Client,
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    departure_dt: datetime,
    mode: str = "driving",
) -> dict:
    """
    Query travel time and distance for one origin→destination pair.

    Returns
    -------
    dict with keys:
        status              : "OK"
        duration_s          : free-flow travel time (seconds)
        duration_in_traffic_s : actual travel time with live traffic (seconds)
        distance_m          : route distance (metres)
        origin              : "lat,lng" string
        destination         : "lat,lng" string
        departure_iso       : departure_dt.isoformat()

    Raises DistanceMatrixError if element status is not OK.
    Caches results keyed on (origin, destination, departure_iso).
    """
    origin      = f"{origin_lat},{origin_lng}"
    destination = f"{dest_lat},{dest_lng}"
    key         = _cache.cache_key(origin, destination, departure_dt)

    cached = _cache.load(key)
    if cached:
        return cached

    result  = client.distance_matrix(
        origins=origin,
        destinations=destination,
        mode=mode,
        departure_time=departure_dt,
        traffic_model="best_guess",
    )
    element = result["rows"][0]["elements"][0]

    if element["status"] != "OK":
        raise DistanceMatrixError(
            f"API returned status '{element['status']}' "
            f"for {origin} → {destination} at {departure_dt.isoformat()}"
        )

    data = {
        "status":                 "OK",
        "duration_s":             element["duration"]["value"],
        "distance_m":             element["distance"]["value"],
        "duration_in_traffic_s":  element.get("duration_in_traffic", {}).get("value"),
        "origin":                 origin,
        "destination":            destination,
        "departure_iso":          departure_dt.isoformat(),
    }
    _cache.save(key, data)
    time.sleep(API_SLEEP_S)
    return data


def query_segment_safe(
    client: googlemaps.Client,
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    departure_dt: datetime,
    mode: str = "driving",
) -> Optional[dict]:
    """
    Same as query_segment but returns None on failure instead of raising.
    Logs the error to stdout.  Use in bulk collection loops.
    """
    try:
        return query_segment(
            client, origin_lat, origin_lng,
            dest_lat, dest_lng, departure_dt, mode
        )
    except DistanceMatrixError as exc:
        print(f"  [WARN] {exc}")
        return None
    except Exception as exc:
        print(f"  [ERROR] Unexpected: {exc}")
        return None


def query_free_flow(
    client: googlemaps.Client,
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    reference_date: datetime,
    free_flow_hour: int = 6,
) -> Optional[dict]:
    """
    Query off-peak (free-flow) travel time.
    Uses reference_date at free_flow_hour (default 06:00) as the departure time.
    Returns same dict structure as query_segment_safe.
    """
    departure_dt = reference_date.replace(
        hour=free_flow_hour, minute=0, second=0, microsecond=0
    )
    return query_segment_safe(
        client, origin_lat, origin_lng,
        dest_lat, dest_lng, departure_dt
    )
