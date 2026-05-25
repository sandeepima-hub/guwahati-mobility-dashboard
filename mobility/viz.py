"""
viz.py
======
All visualisation functions for the Guwahati Mobility Audit Dashboard.
Each function is self-contained: pass in a DataFrame, get back a Plotly figure.
Call fig.show() or fig.write_html() as needed.

Functions
---------
railway_dashboard(df_enriched, corridor_key, peak_key)
    Heatmap of mean TTI per segment × timeslot (the "railway board").

spacetime_diagram(df_enriched, corridor_key, peak_key)
    Space-time congestion diagram showing trajectory compression at bottlenecks.

kpi_panel(kpi_df)
    Six-panel bar chart of aggregate KPIs.

inbound_outbound_chart(df_enriched, corridor_key)
    AM vs PM peak bar chart of corridor-level delay for both directions.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .config import CORRIDORS, PEAK_WINDOWS, TTI_AUDIT_THRESHOLD
from .kpi import segment_summary


# ── Colour helpers ────────────────────────────────────────────────────────────

_LOS_COLOUR = {
    "A": "#2ecc71",
    "B": "#a8d5a2",
    "C": "#f9c846",
    "D": "#f4a261",
    "E": "#e76f51",
    "F": "#c0392b",
    "N/A": "#cccccc",
}

_CORRIDOR_COLOUR = {
    "GS_ROAD": {"AM": "#E63946", "PM": "#f4a0a7"},
    "NH37":    {"AM": "#2196F3", "PM": "#90caf9"},
}


def _tti_to_colour(tti: float) -> str:
    """Map a TTI value to a hex colour via LOS grade."""
    if np.isnan(tti):
        return _LOS_COLOUR["N/A"]
    if tti < 1.00:
        return _LOS_COLOUR["A"]
    if tti < 1.25:
        return _LOS_COLOUR["B"]
    if tti < 1.40:
        return _LOS_COLOUR["C"]
    if tti < 1.60:
        return _LOS_COLOUR["D"]
    if tti < 2.00:
        return _LOS_COLOUR["E"]
    return _LOS_COLOUR["F"]


# ── Railway Dashboard ─────────────────────────────────────────────────────────

def railway_dashboard(
    df: pd.DataFrame,
    corridor_key: str,
    peak_key: str,
) -> go.Figure:
    """
    Heatmap of mean TTI per (segment × timeslot) — styled as a railway
    departure board.  Rows = stop-to-stop segments; columns = time slots.

    Parameters
    ----------
    df           : enriched DataFrame (output of kpi.enrich())
    corridor_key : "GS_ROAD" or "NH37"
    peak_key     : "AM" or "PM"

    Returns
    -------
    plotly Figure
    """
    corridor_label = CORRIDORS[corridor_key]["label"]
    peak_label     = PEAK_WINDOWS[peak_key]["label"]

    sub = df[
        (df["corridor_key"] == corridor_key) &
        (df["peak"]         == peak_key)
    ].copy()

    if sub.empty:
        raise ValueError(f"No data for {corridor_key} {peak_key}.")

    sub["timeslot"] = pd.to_datetime(sub["departure_iso"]).dt.strftime("%H:%M")
    sub["segment_label"] = sub["from_stop"] + " → " + sub["to_stop"]

    pivot = sub.pivot_table(
        index="segment_label",
        columns="timeslot",
        values="tti",
        aggfunc="mean",
    )

    # Preserve stop-sequence order
    stop_order = []
    for _, row in sub.drop_duplicates("segment_id").iterrows():
        lbl = f"{row['from_stop']} → {row['to_stop']}"
        if lbl not in stop_order:
            stop_order.append(lbl)
    pivot = pivot.reindex([s for s in stop_order if s in pivot.index])

    z_text = pivot.map(lambda v: f"{v:.2f}" if not np.isnan(v) else "N/A")

    # Build colour grid
    colour_grid = pivot.map(_tti_to_colour).values.tolist()

    # Plotly annotated heatmap
    fig = go.Figure(
        go.Heatmap(
            z=pivot.values,
            x=pivot.columns.tolist(),
            y=pivot.index.tolist(),
            text=z_text.values,
            texttemplate="%{text}",
            colorscale=[
                [0.00, "#2ecc71"],
                [0.35, "#f9c846"],
                [0.55, "#f4a261"],
                [0.75, "#e76f51"],
                [1.00, "#c0392b"],
            ],
            zmin=0.8,
            zmax=2.5,
            colorbar=dict(
                title="TTI",
                tickvals=[1.0, 1.25, 1.4, 1.6, 2.0, 2.5],
                ticktext=["1.0 (A)", "1.25 (B)", "1.4 (C)", "1.6 (D/E)", "2.0 (E/F)", "2.5 (F)"],
            ),
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Time: %{x}<br>"
                "TTI: %{z:.3f}<br>"
                "<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title=dict(
            text=f"<b>Railway Travel Time Index — {corridor_label} | {peak_label}</b><br>"
                 f"<sup>TTI > {TTI_AUDIT_THRESHOLD} = LOS D/E threshold (audit-reportable)</sup>",
            font=dict(size=14),
        ),
        xaxis_title="Departure time",
        yaxis_title="Corridor segment",
        height=max(400, 60 + 40 * len(pivot)),
        margin=dict(l=240, r=60, t=100, b=60),
        font=dict(family="Arial", size=11),
        plot_bgcolor="#1a1a2e",
        paper_bgcolor="#12122a",
        font_color="#e0e0e0",
    )
    return fig


# ── Space-Time Diagram ────────────────────────────────────────────────────────

def spacetime_diagram(
    df: pd.DataFrame,
    corridor_key: str,
    peak_key: str,
) -> go.Figure:
    """
    Space-time congestion diagram.
    X = cumulative distance from first stop (km).
    Y = sampled departure time.
    Colour = TTI at each segment × slot.
    Trajectory compression = congestion bottleneck.
    """
    corridor_label = CORRIDORS[corridor_key]["label"]
    peak_label     = PEAK_WINDOWS[peak_key]["label"]

    sub = df[
        (df["corridor_key"] == corridor_key) &
        (df["peak"]         == peak_key)
    ].copy()

    if sub.empty:
        raise ValueError(f"No data for {corridor_key} {peak_key}.")

    sub["timeslot"] = pd.to_datetime(sub["departure_iso"]).dt.strftime("%H:%M")

    # Build cumulative distance axis
    seg_dist = (
        sub.groupby("segment_id")["distance_m"]
        .mean()
        .reset_index()
        .rename(columns={"distance_m": "seg_dist_m"})
    )
    # Ordered by stop sequence — use from_stop_id ordering from config
    stop_order = [
        s["id"] for s in CORRIDORS[corridor_key]["stops"]
        if s["lat"] is not None
    ]
    sub["from_order"] = sub["from_stop_id"].map(
        {sid: i for i, sid in enumerate(stop_order)}
    )
    sub = sub.sort_values(["from_order", "timeslot"])

    cum_dist = {}
    running = 0.0
    prev_seg = None
    for _, row in sub.drop_duplicates("segment_id").iterrows():
        if row["segment_id"] != prev_seg:
            cum_dist[row["segment_id"]] = running / 1000  # km
            running += row["distance_m"]
            prev_seg = row["segment_id"]

    sub["cum_dist_km"] = sub["segment_id"].map(cum_dist)

    fig = go.Figure(
        go.Scatter(
            x=sub["cum_dist_km"],
            y=sub["timeslot"],
            mode="markers",
            marker=dict(
                color=sub["tti"],
                colorscale=[
                    [0.0, "#2ecc71"],
                    [0.4, "#f9c846"],
                    [0.6, "#f4a261"],
                    [0.8, "#e76f51"],
                    [1.0, "#c0392b"],
                ],
                cmin=0.8,
                cmax=2.5,
                size=14,
                colorbar=dict(title="TTI"),
                showscale=True,
            ),
            text=(
                "<b>" + sub["from_stop"] + " → " + sub["to_stop"] + "</b><br>"
                "TTI: " + sub["tti"].round(3).astype(str) + "<br>"
                "Speed: " + sub["speed_kmph"].round(1).astype(str) + " km/h"
            ),
            hoverinfo="text",
        )
    )

    fig.update_layout(
        title=dict(
            text=(
                f"<b>Space-Time Congestion Diagram — {corridor_label} | {peak_label}</b><br>"
                "<sup>Trajectory compression = bottleneck; colour = TTI</sup>"
            ),
            font=dict(size=14),
        ),
        xaxis_title="Distance from start (km)",
        yaxis_title="Departure time",
        height=500,
        plot_bgcolor="#1a1a2e",
        paper_bgcolor="#12122a",
        font_color="#e0e0e0",
        font=dict(family="Arial", size=11),
    )
    return fig


# ── KPI Panel ─────────────────────────────────────────────────────────────────

def kpi_panel(kpi_df: pd.DataFrame) -> go.Figure:
    """
    Six-panel bar chart of aggregate KPIs.
    One bar group per (corridor × peak) combination.
    Audit thresholds shown as dashed horizontal lines.

    Input: pd.DataFrame from kpi.compute_kpi_table()
    """
    metrics = [
        ("Travel Time Index (TTI)",     TTI_AUDIT_THRESHOLD,  1, 1),
        ("Planning Time Index (PTI)",    2.0,                   1, 2),
        ("Buffer Index (BI)",            0.40,                  1, 3),
        ("Average Speed (km/h)",         None,                  2, 1),
        ("Total Corridor Delay (min)",   None,                  2, 2),
        ("LOS F Segments (%)",           None,                  2, 3),
    ]

    fig = make_subplots(
        rows=2, cols=3,
        subplot_titles=[m[0] for m in metrics],
        vertical_spacing=0.22,
        horizontal_spacing=0.10,
    )

    for _, row in kpi_df.iterrows():
        label  = f"{row['Corridor']} {row['Peak']}"
        ck     = "GS_ROAD" if "GS" in row["Corridor"] else "NH37"
        colour = _CORRIDOR_COLOUR[ck][row["Peak"]]

        for metric, threshold, r, c in metrics:
            if metric not in kpi_df.columns:
                continue
            fig.add_trace(
                go.Bar(
                    name=label,
                    x=[label],
                    y=[row[metric]],
                    marker_color=colour,
                    showlegend=(r == 1 and c == 1),
                    legendgroup=label,
                ),
                row=r, col=c,
            )

    # Add threshold lines
    for metric, threshold, r, c in metrics:
        if threshold is not None:
            fig.add_hline(
                y=threshold,
                line_dash="dash",
                line_color="#ff4444",
                annotation_text=f"Audit threshold: {threshold}",
                annotation_position="top right",
                row=r, col=c,
            )

    fig.update_layout(
        title=dict(
            text="<b>Audit KPI Summary — Peak-Hour Performance</b>",
            font=dict(size=14),
        ),
        height=650,
        barmode="group",
        plot_bgcolor="#1a1a2e",
        paper_bgcolor="#12122a",
        font_color="#e0e0e0",
        font=dict(family="Arial", size=11),
        legend=dict(orientation="h", y=-0.08),
    )
    return fig


# ── Inbound / Outbound Chart ──────────────────────────────────────────────────

def inbound_outbound_chart(
    df: pd.DataFrame,
    corridor_key: str,
) -> go.Figure:
    """
    AM vs PM peak average delay chart for a single corridor.
    Shows the asymmetry between inbound (AM) and outbound (PM) congestion,
    which is a reportable pattern in mobility audits.
    """
    corridor_label = CORRIDORS[corridor_key]["label"]

    sub = df[df["corridor_key"] == corridor_key].copy()
    if sub.empty:
        raise ValueError(f"No data for {corridor_key}.")

    summary = sub.groupby("peak").agg(
        mean_delay_min =("delay_s", lambda s: s.mean() / 60),
        mean_tti       =("tti",     "mean"),
        mean_speed     =("speed_kmph", "mean"),
    ).reset_index()

    peak_labels = {"AM": "AM Peak (08:00–10:00)", "PM": "PM Peak (17:00–19:00)"}
    colours     = {"AM": "#E63946", "PM": "#2196F3"}

    fig = go.Figure()

    for _, row in summary.iterrows():
        pk = row["peak"]
        fig.add_trace(go.Bar(
            name=peak_labels.get(pk, pk),
            x=[peak_labels.get(pk, pk)],
            y=[row["mean_delay_min"]],
            marker_color=colours.get(pk, "#888"),
            text=f"{row['mean_delay_min']:.1f} min<br>TTI {row['mean_tti']:.2f}<br>{row['mean_speed']:.0f} km/h",
            textposition="outside",
        ))

    fig.update_layout(
        title=dict(
            text=f"<b>Inbound / Outbound Congestion — {corridor_label}</b><br>"
                 "<sup>Average segment delay vs free-flow baseline</sup>",
            font=dict(size=14),
        ),
        yaxis_title="Mean delay per segment (minutes)",
        height=420,
        barmode="group",
        plot_bgcolor="#1a1a2e",
        paper_bgcolor="#12122a",
        font_color="#e0e0e0",
        font=dict(family="Arial", size=11),
    )
    return fig
