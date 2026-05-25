"""
kpi.py
======
All audit KPI computations. Input is the DataFrame produced by collect.py.
All functions are pure (no side effects).

KPIs produced — Indo-HCM 2017 (CSIR-CRRI) framework
-----------------------------------------------------
PTI   Planning Time Index       = 95th-pct duration / free-flow duration
                                  Primary LOS measure: Indo-HCM Table 10.7
BTI   Buffer Time Index         = (PTI - TTI) / TTI
                                  Indo-HCM Eq. 10.4
CV    Coefficient of Variation  = SD / mean travel time × 100%
                                  Indo-HCM Eq. 10.3; LOS threshold Table 10.7
FFS%  % Free Flow Speed         = (free_flow_speed / peak_speed) × 100
                                  LOS threshold: Indo-HCM Table 5.7 (multilane divided)
PT    Planning Time (sec/km)    = 95th-pct travel time / distance (sec/km)
                                  Indo-HCM Table 10.2
TTI   Travel Time Index         = peak_duration / free-flow_duration
                                  Retained as secondary mobility measure
LOS   Level of Service          = derived from PTI per Indo-HCM Table 10.7
DELAY Excess delay vs free flow (min)
PROD  Productivity loss (₹ Lakh/yr) — MORTH 2018 VOT

Reference: Indo-HCM 2017, CSIR-CRRI, New Delhi.
           IIT Guwahati was a Regional Coordinator for this manual.
"""

import numpy as np
import pandas as pd

from .config import (
    PTI_LOS_THRESHOLDS,
    FFS_LOS_THRESHOLDS,
    TTI_AUDIT_THRESHOLD,
    PTI_AUDIT_THRESHOLD,
    BI_AUDIT_THRESHOLD,
    CV_AUDIT_THRESHOLD,
    FFS_AUDIT_THRESHOLD,
    VALUE_OF_TIME_INR_PER_HOUR,
    POSTED_SPEED_KMPH,
    CORRIDORS,
)

# ── Low-level helpers ─────────────────────────────────────────────────────────

def _pti_los(pti: float) -> str:
    """Map PTI to Indo-HCM LOS grade (Table 10.7, interrupted urban arterial)."""
    if np.isnan(pti):
        return "N/A"
    for grade, (lo, hi) in PTI_LOS_THRESHOLDS.items():
        if lo <= pti < hi:
            return grade
    return "E"

def _ffs_los(ffs_pct: float) -> str:
    """Map % Free Flow Speed to Indo-HCM LOS grade (Table 5.7, multilane divided)."""
    if np.isnan(ffs_pct):
        return "N/A"
    for grade, (lo, hi) in FFS_LOS_THRESHOLDS.items():
        if lo <= ffs_pct <= hi:
            return grade
    return "F"

def _speed_kmph(distance_m: float, duration_s: float) -> float:
    if duration_s and duration_s > 0:
        return (distance_m / 1000) / (duration_s / 3600)
    return float("nan")

# ── Per-observation enrichment ────────────────────────────────────────────────

def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add per-row derived columns.

    New columns:
        effective_duration_s  : duration_in_traffic_s if available, else duration_s
        tti                   : Travel Time Index (secondary)
        pti_approx            : per-observation PTI proxy (= TTI for single obs)
        los                   : LOS grade from PTI thresholds
        speed_kmph            : average speed
        free_flow_speed_kmph  : free-flow speed
        ffs_pct               : % of free-flow speed achieved
        ffs_los               : LOS from % FFS (Table 5.7)
        delay_s               : excess delay vs free flow
        flagged_pti           : bool — PTI exceeds audit threshold
    """
    df = df.copy()

    df["effective_duration_s"] = df["duration_in_traffic_s"].combine_first(
        df["duration_s"]
    )

    # TTI — peak / free-flow
    df["tti"] = np.where(
        (df["free_flow_duration_s"].notna()) & (df["free_flow_duration_s"] > 0),
        df["effective_duration_s"] / df["free_flow_duration_s"],
        np.nan,
    )

    # PTI proxy at observation level = TTI (PTI is properly a 95th-pct aggregate)
    df["pti_approx"] = df["tti"]

    # LOS from PTI thresholds (Indo-HCM Table 10.7)
    df["los"] = df["pti_approx"].apply(_pti_los)

    # Speed
    df["speed_kmph"] = df.apply(
        lambda r: _speed_kmph(r["distance_m"], r["effective_duration_s"]), axis=1
    )
    df["free_flow_speed_kmph"] = df.apply(
        lambda r: _speed_kmph(r["distance_m"], r["free_flow_duration_s"]), axis=1
    )

    # % Free Flow Speed
    df["ffs_pct"] = np.where(
        df["free_flow_speed_kmph"] > 0,
        (df["speed_kmph"] / df["free_flow_speed_kmph"]) * 100,
        np.nan,
    )
    df["ffs_los"] = df["ffs_pct"].apply(
        lambda v: _ffs_los(v) if not np.isnan(v) else "N/A"
    )

    # Delay
    df["delay_s"] = (
        df["effective_duration_s"] - df["free_flow_duration_s"]
    ).clip(lower=0)

    df["flagged_pti"] = df["pti_approx"] > PTI_AUDIT_THRESHOLD

    return df


# ── Aggregate KPI table ───────────────────────────────────────────────────────

def compute_kpi_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate per-segment observations into corridor × peak KPI rows.
    Uses Indo-HCM 2017 measures as primary framework.

    Input  : enriched DataFrame (output of enrich())
    Returns: pd.DataFrame with one row per (corridor, peak)
    """
    records = []

    for (corridor, peak), grp in df.groupby(["corridor", "peak"]):

        # ── PTI (Indo-HCM primary measure) ────────────────────────────────────
        # 95th percentile of travel time / mean free-flow travel time
        p95_s   = grp["effective_duration_s"].quantile(0.95)
        mean_ff = grp["free_flow_duration_s"].mean()
        pti     = p95_s / mean_ff if mean_ff > 0 else float("nan")

        # ── TTI (secondary mobility measure) ──────────────────────────────────
        mean_tti = grp["tti"].mean()

        # ── BTI (Buffer Time Index) ────────────────────────────────────────────
        # (PTI - TTI) / TTI  [Indo-HCM Eq. 10.4 adapted]
        bti = (pti - mean_tti) / mean_tti if mean_tti > 0 else float("nan")

        # ── CV (Coefficient of Variation) ─────────────────────────────────────
        # SD / mean of peak travel times  [Indo-HCM Eq. 10.3]
        cv = (grp["effective_duration_s"].std() /
              grp["effective_duration_s"].mean()) if grp["effective_duration_s"].mean() > 0 else float("nan")

        # ── Planning Time sec/km ───────────────────────────────────────────────
        # 95th-pct travel time per km [Indo-HCM Table 10.2]
        mean_dist_km = (grp["distance_m"].mean() / 1000)
        pt_sec_km    = (p95_s / mean_dist_km) if mean_dist_km > 0 else float("nan")

        # ── % Free Flow Speed ──────────────────────────────────────────────────
        ffs_pct = grp["ffs_pct"].mean()

        # ── Speed and Delay ────────────────────────────────────────────────────
        avg_speed   = grp["speed_kmph"].mean()
        total_delay = grp.groupby("segment_id")["delay_s"].mean().sum() / 60.0

        # ── LOS ───────────────────────────────────────────────────────────────
        los_grade   = _pti_los(pti)
        los_f_pct   = (grp["los"].isin(["E", "F"])).mean() * 100   # LOS D+ flagged

        # ── Productivity loss ──────────────────────────────────────────────────
        DAILY_TRIPS        = 5_000   # placeholder — replace from traffic count
        annual_delay_h     = (total_delay / 60) * 250 * DAILY_TRIPS
        prod_loss_lakh     = (annual_delay_h * VALUE_OF_TIME_INR_PER_HOUR) / 1e5

        records.append({
            "Corridor":                        corridor,
            "Peak":                            peak,
            "Planning Time Index (PTI)":       round(pti,      3),
            "Travel Time Index (TTI)":         round(mean_tti, 3),
            "Buffer Time Index (BTI)":         round(bti,      3),
            "Coeff. of Variation (CV)":        round(cv,       3),
            "Planning Time (sec/km)":          round(pt_sec_km,1),
            "% Free Flow Speed":               round(ffs_pct,  1),
            "LOS (Indo-HCM PTI)":              los_grade,
            "Average Speed (km/h)":            round(avg_speed,1),
            "Total Corridor Delay (min)":      round(total_delay,1),
            "LOS D/E Segments (%)":            round(los_f_pct,  1),
            "PTI Flag (>1.6)":                 pti     > PTI_AUDIT_THRESHOLD,
            "BTI Flag (>0.40)":                bti     > BI_AUDIT_THRESHOLD,
            "CV Flag (>0.40)":                 cv      > CV_AUDIT_THRESHOLD,
            "FFS% Flag (<59%)":                ffs_pct < FFS_AUDIT_THRESHOLD,
            "Productivity Loss (₹ Lakh/yr)":   round(prod_loss_lakh, 1),
        })

    return pd.DataFrame(records)


def segment_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-segment mean KPIs averaged across sampled timeslots.
    Used for railway dashboard heatmap and transit table.
    """
    agg = (
        df.groupby(["corridor", "peak", "from_stop", "to_stop"])
        .agg(
            mean_tti        =("tti",          "mean"),
            mean_pti        =("pti_approx",   lambda x: x.quantile(0.95)),
            mean_delay_s    =("delay_s",       "mean"),
            mean_speed_kmph =("speed_kmph",    "mean"),
            mean_ffs_pct    =("ffs_pct",       "mean"),
            mean_cv         =("effective_duration_s",
                               lambda x: x.std() / x.mean() if x.mean() > 0 else float("nan")),
            los_mode        =("los",           lambda x: x.mode().iloc[0] if len(x) > 0 else "N/A"),
            flagged_pct     =("flagged_pti",   "mean"),
        )
        .reset_index()
    )
    agg["flagged_pct"] = (agg["flagged_pct"] * 100).round(1)
    return agg


def worst_segments(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Return n worst-performing segments by mean PTI."""
    seg = segment_summary(df)
    return (
        seg.sort_values("mean_pti", ascending=False)
           .head(n)
           .reset_index(drop=True)
    )


def speed_camera_deterrence_coverage(corridor_key: str) -> float:
    """Returns 0.0 — consistent with GSCL audit finding that speed camera
    enforcement is non-operational (no citations issued)."""
    _ = corridor_key
    return 0.0
