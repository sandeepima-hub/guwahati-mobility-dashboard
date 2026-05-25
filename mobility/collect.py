"""
collect.py
==========
Builds the corridor × segment × timeslot travel-time DataFrame.
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import Optional

import googlemaps

from .config import (
    CORRIDORS,
    PEAK_WINDOWS,
    SAMPLE_INTERVAL_MINUTES,
)
from .api import query_segment_safe


def _sample_times(reference_date: datetime, peak_key: str):
    """
    Return sampled departure datetimes within the peak window.
    If a slot is in the past, substitute now + 2 min to satisfy API requirement.
    """
    pw   = PEAK_WINDOWS[peak_key]
    base = reference_date.replace(hour=pw["start_hour"], minute=0, second=0, microsecond=0)
    end  = reference_date.replace(hour=pw["end_hour"],   minute=0, second=0, microsecond=0)
    now  = datetime.now()
    slots, t = [], base
    while t <= end:
        slots.append(t if t > now else now + timedelta(minutes=2))
        t += timedelta(minutes=SAMPLE_INTERVAL_MINUTES)
    return slots


def _valid_stops(stops):
    return [s for s in stops if s["lat"] is not None and s["lng"] is not None]


def collect_corridor(
    client,
    corridor_key: str,
    peak_key: str,
    reference_date: datetime,
) -> pd.DataFrame:
    corridor = CORRIDORS[corridor_key]
    stops    = _valid_stops(corridor["stops"])
    if len(stops) < 2:
        raise ValueError(f"Corridor {corridor_key} has fewer than 2 verified stops.")

    slots = _sample_times(reference_date, peak_key)
    rows  = []

    print(f"\n→ Collecting {corridor['label']} | {PEAK_WINDOWS[peak_key]['label']} "
          f"| {len(stops)-1} segments | {len(slots)} timeslots")

    for i in range(len(stops) - 1):
        o, d   = stops[i], stops[i + 1]
        seg_id = f"{o['id']}→{d['id']}"

        # Free-flow baseline: query at current time + 2 min (off-peak proxy)
        ff = query_segment_safe(
            client,
            o["lat"], o["lng"],
            d["lat"], d["lng"],
            datetime.now() + timedelta(minutes=2),
        )
        ff_duration_s = ff["duration_s"] if ff else None

        for slot in slots:
            result = query_segment_safe(
                client,
                o["lat"], o["lng"],
                d["lat"], d["lng"],
                slot,
            )
            if result is None:
                continue

            rows.append({
                "corridor":              corridor["label"],
                "corridor_key":          corridor_key,
                "peak":                  peak_key,
                "segment_id":            seg_id,
                "from_stop_id":          o["id"],
                "from_stop":             o["name"],
                "to_stop_id":            d["id"],
                "to_stop":               d["name"],
                "departure_iso":         result["departure_iso"],
                "duration_s":            result["duration_s"],
                "duration_in_traffic_s": result["duration_in_traffic_s"],
                "distance_m":            result["distance_m"],
                "free_flow_duration_s":  ff_duration_s,
            })
            print(f"   {o['name']:22s} → {d['name']:22s}  "
                  f"{slot.strftime('%H:%M')}  "
                  f"{(result['duration_in_traffic_s'] or 0)//60:3.0f} min")

    df = pd.DataFrame(rows)
    print(f"   ✓ {len(df)} records collected for {corridor['label']} {peak_key}")
    return df


def collect_all(
    client,
    reference_date: datetime,
    corridors=None,
    peaks=None,
) -> pd.DataFrame:
    corridors = corridors or list(CORRIDORS.keys())
    peaks     = peaks     or list(PEAK_WINDOWS.keys())

    frames = []
    for ck in corridors:
        for pk in peaks:
            df = collect_corridor(client, ck, pk, reference_date)
            frames.append(df)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
