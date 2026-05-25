"""
export.py
=========
Save all dashboard outputs to EXPORT_DIR for inclusion in the CAG audit dossier.

Outputs produced
----------------
raw_travel_times.csv        — full enriched DataFrame
segment_summary.csv         — per-segment mean KPIs
audit_kpis.csv              — corridor × peak KPI table
railway_<corridor>_<peak>.html  — interactive Plotly heatmaps
spacetime_<corridor>_<peak>.html
kpi_panel.html
inbound_outbound_<corridor>.html
"""

import os
import pandas as pd
import plotly.graph_objects as go

from .config import EXPORT_DIR, CORRIDORS, PEAK_WINDOWS
from .kpi import enrich, compute_kpi_table, segment_summary


def _ensure_dir() -> None:
    os.makedirs(EXPORT_DIR, exist_ok=True)


def _path(filename: str) -> str:
    return os.path.join(EXPORT_DIR, filename)


# ── CSV exports ───────────────────────────────────────────────────────────────

def save_raw(df: pd.DataFrame) -> str:
    """Save enriched travel-time DataFrame.  Returns filepath."""
    _ensure_dir()
    path = _path("raw_travel_times.csv")
    df.to_csv(path, index=False)
    print(f"  ✓ Saved {path}  ({len(df)} rows)")
    return path


def save_segment_summary(df: pd.DataFrame) -> str:
    """Save per-segment KPI summary.  Returns filepath."""
    _ensure_dir()
    seg = segment_summary(df)
    path = _path("segment_summary.csv")
    seg.to_csv(path, index=False)
    print(f"  ✓ Saved {path}  ({len(seg)} segments)")
    return path


def save_kpi_table(df: pd.DataFrame) -> str:
    """Compute and save corridor-level KPI table.  Returns filepath."""
    _ensure_dir()
    kpi = compute_kpi_table(df)
    path = _path("audit_kpis.csv")
    kpi.to_csv(path, index=False)
    print(f"  ✓ Saved {path}")
    return path


# ── HTML figure exports ───────────────────────────────────────────────────────

def save_figure(fig: go.Figure, filename: str) -> str:
    """Write a Plotly figure to HTML.  Returns filepath."""
    _ensure_dir()
    path = _path(filename)
    fig.write_html(path, include_plotlyjs="cdn", full_html=True)
    size_kb = os.path.getsize(path) / 1024
    print(f"  ✓ Saved {path}  ({size_kb:.0f} KB)")
    return path


# ── Full export pipeline ──────────────────────────────────────────────────────

def export_all(df_raw: pd.DataFrame, figures: dict) -> list[str]:
    """
    Save all CSVs and HTML figures.

    Parameters
    ----------
    df_raw  : enriched DataFrame (from kpi.enrich())
    figures : dict of {filename_stem: plotly_Figure}
              e.g. {"railway_NH37_AM": fig1, "kpi_panel": fig2}

    Returns
    -------
    List of all saved file paths.
    """
    _ensure_dir()
    paths = []

    paths.append(save_raw(df_raw))
    paths.append(save_segment_summary(df_raw))
    paths.append(save_kpi_table(df_raw))

    for stem, fig in figures.items():
        paths.append(save_figure(fig, f"{stem}.html"))

    print(f"\n  Export complete: {len(paths)} files in {EXPORT_DIR}/")
    return paths


def list_exports() -> list[dict]:
    """List all files currently in EXPORT_DIR with sizes."""
    _ensure_dir()
    result = []
    for fname in sorted(os.listdir(EXPORT_DIR)):
        fp = os.path.join(EXPORT_DIR, fname)
        result.append({
            "file": fname,
            "size_kb": round(os.path.getsize(fp) / 1024, 1),
        })
    return result
