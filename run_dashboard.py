"""
run_dashboard.py
================
Top-level collection runner for the Guwahati Mobility Audit Dashboard.
Run this on your Mac during peak windows to collect travel time data
and write results to GCS for the Streamlit app to display.

Usage
-----
    python run_dashboard.py --api-key YOUR_KEY --date 2026-05-22

    # Or store key in environment to avoid typing it each time:
    export MAPS_API_KEY=AIzaSy...
    python run_dashboard.py --date 2026-05-22

Options
-------
--api-key   Google Maps Platform API key (or set MAPS_API_KEY env var)
--date      Reference date YYYY-MM-DD (default: today IST)
--corridor  GS_ROAD | NH37 | all  (default: all)
--peak      AM | PM | all  (default: all)
--show      Open figures in browser after collection
--no-export Skip writing to GCS
--clear-cache  Wipe GCS cache before running
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import googlemaps

from mobility import collect, kpi, viz, export
from mobility import storage
from mobility.config import CORRIDORS, PEAK_WINDOWS, GCS_BUCKET


def _ist_today() -> str:
    """Return today's date in IST as YYYY-MM-DD."""
    ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
    return ist.strftime("%Y-%m-%d")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Guwahati Mobility Audit — Data Collection")
    p.add_argument("--api-key",     default=os.environ.get("MAPS_API_KEY"),
                   help="Google Maps API key (or set MAPS_API_KEY env var)")
    p.add_argument("--date",        default=_ist_today(),
                   help="Reference date YYYY-MM-DD (default: today IST)")
    p.add_argument("--corridor",    default="all",
                   choices=["all"] + list(CORRIDORS.keys()))
    p.add_argument("--peak",        default="all",
                   choices=["all"] + list(PEAK_WINDOWS.keys()))
    p.add_argument("--show",        action="store_true",
                   help="Open figures in browser")
    p.add_argument("--no-export",   action="store_true",
                   help="Skip writing to GCS")
    p.add_argument("--clear-cache", action="store_true",
                   help="Wipe GCS cache before running")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if not args.api_key:
        print("ERROR: No API key. Pass --api-key or set MAPS_API_KEY env var.")
        sys.exit(1)

    ref_date  = datetime.strptime(args.date, "%Y-%m-%d")
    corridors = list(CORRIDORS.keys())    if args.corridor == "all" else [args.corridor]
    peaks     = list(PEAK_WINDOWS.keys()) if args.peak     == "all" else [args.peak]

    print("=" * 65)
    print("  Guwahati Urban Mobility Audit — Data Collection")
    print(f"  Date      : {args.date}")
    print(f"  Corridors : {corridors}")
    print(f"  Peaks     : {peaks}")
    print(f"  GCS Bucket: {GCS_BUCKET}")
    info = storage.cache_size(GCS_BUCKET)
    print(f"  Cache     : {info['count']} entries")
    print("=" * 65)

    if args.clear_cache:
        n = storage.cache_clear(GCS_BUCKET)
        print(f"  Cache cleared ({n} entries deleted)\n")

    # ── Step 1: Collect ───────────────────────────────────────────────────────
    client = googlemaps.Client(key=args.api_key)
    df_raw = collect.collect_all(
        client, ref_date,
        corridors=corridors,
        peaks=peaks,
    )

    if df_raw.empty:
        print("\n  No data collected. Check API key and stop coordinates.")
        sys.exit(1)

    # ── Step 2: Enrich and summarise ─────────────────────────────────────────
    df        = kpi.enrich(df_raw)
    kpi_table = kpi.compute_kpi_table(df)
    seg_sum   = kpi.segment_summary(df)

    print("\nAUDIT KPI TABLE")
    print("-" * 65)
    print(kpi_table.to_string(index=False))

    print("\nWORST SEGMENTS (by TTI)")
    print("-" * 65)
    print(kpi.worst_segments(df, n=5).to_string(index=False))

    # ── Step 3: Figures ───────────────────────────────────────────────────────
    figures = {}
    for ck in corridors:
        for pk in peaks:
            try:
                figures[f"railway_{ck}_{pk}"]   = viz.railway_dashboard(df, ck, pk)
                figures[f"spacetime_{ck}_{pk}"]  = viz.spacetime_diagram(df, ck, pk)
            except ValueError as exc:
                print(f"  [SKIP] {exc}")
        try:
            figures[f"inbound_outbound_{ck}"] = viz.inbound_outbound_chart(df, ck)
        except ValueError as exc:
            print(f"  [SKIP] {exc}")

    figures["kpi_panel"] = viz.kpi_panel(kpi_table)

    if args.show:
        for fig in figures.values():
            fig.show()

    # ── Step 4: Export to GCS ─────────────────────────────────────────────────
    if not args.no_export:
        print("\nEXPORTING TO GCS")
        print("-" * 65)

        # Merge with existing GCS data — never overwrite other corridors/peaks
        import io, pandas as pd
        for fname, new_df, merge_keys in [
            ("raw_travel_times.csv",  df,         ["corridor_key", "peak"]),
            ("audit_kpis.csv",        kpi_table,  ["Corridor", "Peak"]),
            ("segment_summary.csv",   seg_sum,    ["corridor", "peak"]),
        ]:
            existing = storage.download_csv(GCS_BUCKET, fname)
            if existing is not None and not existing.empty:
                # Drop rows for corridors/peaks being updated, keep the rest
                mask = pd.Series([True] * len(existing))
                for key in merge_keys:
                    if key in existing.columns and key in new_df.columns:
                        mask = mask & existing[key].isin(new_df[key].unique())
                existing = existing[~mask]
                merged = pd.concat([existing, new_df], ignore_index=True)
            else:
                merged = new_df
            storage.upload_csv(GCS_BUCKET, fname, merged)
        print("  ✓ CSVs merged and uploaded")

        # ── Append to historical KPI log ──────────────────────────────────────
        kpi_with_date = kpi_table.copy()
        kpi_with_date.insert(0, "Date", ref_date.strftime("%Y-%m-%d"))
        kpi_with_date.insert(1, "Run_IST", datetime.now().strftime("%Y-%m-%d %H:%M"))
        existing_hist = storage.download_csv(GCS_BUCKET, "historical_kpis.csv")
        if existing_hist is not None and not existing_hist.empty:
            historical = pd.concat([existing_hist, kpi_with_date], ignore_index=True)
        else:
            historical = kpi_with_date
        storage.upload_csv(GCS_BUCKET, "historical_kpis.csv", historical)
        print(f"  ✓ Historical log updated ({len(historical)} total runs)")

        for stem, fig in figures.items():
            html = fig.to_html(include_plotlyjs="cdn", full_html=True)
            storage.upload_html(GCS_BUCKET, f"{stem}.html", html)
        print(f"  ✓ {len(figures)} figures uploaded")

        print("\n  Files in GCS exports/:")
        for fname in storage.list_exports(GCS_BUCKET):
            print(f"    {fname}")

    print("\n  Done.")


if __name__ == "__main__":
    main()
