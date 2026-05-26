"""
app.py — Guwahati Urban Mobility Dashboard
"""

from datetime import datetime, timedelta, timezone
import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from mobility import config, kpi, viz
from mobility.shapes import get_corridor_layer, get_stop_geodataframe, network_bounds
from mobility.storage import download_csv, cache_size

st.set_page_config(
    page_title="Guwahati Mobility",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_ist():
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=5, minutes=30)

def _peak_status(now):
    h = now.hour
    for pk, pw in config.PEAK_WINDOWS.items():
        if pw["start_hour"] <= h < pw["end_hour"]:
            return {"in_peak": True, "label": pw["label"], "next_label": None}
    upcoming = []
    for pk, pw in config.PEAK_WINDOWS.items():
        t = now.replace(hour=pw["start_hour"], minute=0, second=0, microsecond=0)
        if t <= now:
            t += timedelta(days=1)
        upcoming.append(t)
    upcoming.sort()
    return {"in_peak": False, "label": None, "next_label": upcoming[0].strftime("%-I:%M %p")}

@st.cache_data(ttl=300)
def _load_kpi_table():
    return download_csv(config.GCS_BUCKET, "audit_kpis.csv")

@st.cache_data(ttl=300)
def _load_segment_summary():
    return download_csv(config.GCS_BUCKET, "segment_summary.csv")

@st.cache_data(ttl=300)
def _load_raw():
    return download_csv(config.GCS_BUCKET, "raw_travel_times.csv")

@st.cache_data(ttl=300)
def _load_historical():
    return download_csv(config.GCS_BUCKET, "historical_kpis.csv")

def _tti_hex(v):
    if v is None or (isinstance(v, float) and pd.isna(v)): return "#555"
    if v >= 2.0: return "#ef4444"
    if v >= 1.6: return "#f97316"
    if v >= 1.4: return "#eab308"
    return "#22c55e"

# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.markdown("## Guwahati Mobility")
        st.caption("Peak Hour Analysis")
        st.divider()

        st.markdown("**Corridor**")
        corridor = st.radio(
            "corridor",
            options=list(config.CORRIDORS.keys()),
            format_func=lambda k: config.CORRIDORS[k]["label"],
            label_visibility="collapsed",
        )

        st.divider()
        st.markdown("**Peak Window**")
        peak = st.radio(
            "peak",
            options=list(config.PEAK_WINDOWS.keys()),
            format_func=lambda k: config.PEAK_WINDOWS[k]["label"],
            label_visibility="collapsed",
        )

        st.divider()
        now = _now_ist()
        st.caption(now.strftime("%d %b %Y  %H:%M IST"))

    return corridor, peak

# ── Ticker ────────────────────────────────────────────────────────────────────

def render_ticker(status):
    if status["in_peak"]:
        st.success(f"▶ Live collection window open — {status['label']}")
    else:
        st.info(f"◌  Next live analysis at **{status['next_label']}** — Please feel free to review the summary and KPIs below.")

# ── KPI strip ─────────────────────────────────────────────────────────────────

KPI_DESCS = {
    "Travel Time Index (TTI)":    "Peak time ÷ free-flow time. >1.6 = severe congestion.",
    "Planning Time Index (PTI)":  "95th-pct travel time ÷ free-flow. Worst-case reliability.",
    "Buffer Index (BI)":          "Extra buffer needed as % of avg trip. >40% = unreliable.",
    "Average Speed (km/h)":       "Mean speed across all segments in the peak window.",
    "Total Corridor Delay (min)": "Excess delay vs free flow, summed across all segments.",
    "LOS F Segments (%)":         "% of segments at Level of Service F — breakdown conditions.",
}

def render_kpis(kpi_df, corridor, peak):
    if kpi_df is None:
        st.info("No KPI data yet — run collection first.")
        return

    row = kpi_df[
        (kpi_df["Corridor"] == config.CORRIDORS[corridor]["label"]) &
        (kpi_df["Peak"]     == peak)
    ]
    if row.empty:
        st.warning("No KPI data for this selection.")
        return

    r = row.iloc[0]

    cols = st.columns(6)
    data = [
        ("TTI",          f"{r['Travel Time Index (TTI)']:.3f}",
         r["Travel Time Index (TTI)"] > config.TTI_AUDIT_THRESHOLD,
         KPI_DESCS["Travel Time Index (TTI)"]),
        ("PTI",          f"{r['Planning Time Index (PTI)']:.3f}",
         r["Planning Time Index (PTI)"] > config.PTI_AUDIT_THRESHOLD,
         KPI_DESCS["Planning Time Index (PTI)"]),
        ("Buffer Index", f"{r['Buffer Index (BI)']:.3f}",
         r["Buffer Index (BI)"] > config.BI_AUDIT_THRESHOLD,
         KPI_DESCS["Buffer Index (BI)"]),
        ("Avg Speed",    f"{r['Average Speed (km/h)']:.1f} km/h",
         False,
         KPI_DESCS["Average Speed (km/h)"]),
        ("Delay",        f"{r['Total Corridor Delay (min)']:.1f} min",
         r["Total Corridor Delay (min)"] > 10,
         KPI_DESCS["Total Corridor Delay (min)"]),
        ("LOS F",        f"{r['LOS F Segments (%)']:.1f}%",
         r["LOS F Segments (%)"] > 20,
         KPI_DESCS["LOS F Segments (%)"]),
    ]

    for col, (label, val, flagged, desc) in zip(cols, data):
        delta = "⚠ Above threshold" if flagged else "✓ Within threshold"
        col.metric(label=label, value=val, delta=delta,
                   delta_color="inverse" if flagged else "normal",
                   help=desc)

    prod = r.get("Productivity Loss (₹ Lakh/yr)")
    if prod:
        st.caption(f"Estimated annualised productivity loss: ₹{prod:.1f} Lakh/year (MORTH 2018 VOT — replace DAILY_TRIPS before citing)")

# ── KPI guide ─────────────────────────────────────────────────────────────────

def render_kpi_guide():
    with st.expander("What do these indicators mean?"):
        c1, c2, c3 = st.columns(3)
        items = [
            ("TTI — Travel Time Index",
             f"Ratio of peak travel time to free-flow. TTI 1.6 = a 10-min free-flow trip takes 16 min at peak. Graded A–F per HCM 6th Edition.",
             f"Flag: TTI > {config.TTI_AUDIT_THRESHOLD}"),
            ("PTI — Planning Time Index",
             "95th-percentile travel time ÷ free-flow. Captures worst-case days. PTI 2.0 = on the worst days trips take twice as long.",
             f"Flag: PTI > {config.PTI_AUDIT_THRESHOLD}"),
            ("BI — Buffer Index",
             "Extra buffer as a fraction of average trip. BI = (PTI−TTI)/TTI. BI 0.4 = plan 40% extra. High BI = unreliable, not just slow.",
             f"Flag: BI > {config.BI_AUDIT_THRESHOLD}"),
            ("LOS — Level of Service",
             "HCM letter grade A–F per TTI. LOS A–C acceptable. D = stressed. E = near capacity. F = breakdown. F segments are directly citable.",
             "Flag: LOS F > 20% of segments"),
            ("Corridor Delay",
             "Total excess travel time per trip vs free-flow, summed across all segments. Feeds productivity loss calculation using MORTH 2018 VOT.",
             "Flag: Delay > 10 min/trip"),
            ("Average Speed",
             "Mean vehicle speed across all segments in the peak window. Urban arterials should sustain >20 km/h. Below 15 km/h = breakdown.",
             "Reference: 20 km/h urban arterial"),
        ]
        for i, (title, body, flag) in enumerate(items):
            with [c1, c2, c3][i % 3]:
                st.markdown(f"**{title}**")
                st.caption(body)
                st.caption(f"*{flag}*")
                if i < 3:
                    st.markdown("")

# ── Map ───────────────────────────────────────────────────────────────────────

def render_map(seg_df, corridor, peak):
    bounds = network_bounds(corridor)
    center = [bounds["center_lat"], bounds["center_lng"]]
    m = folium.Map(location=center, zoom_start=13, tiles="CartoDB dark_matter")

    try:
        layer = get_corridor_layer(corridor)
        clr = "#ff6b2b" if corridor == "GS_ROAD" else "#29b6f6"
        for _, row in layer[~layer["is_primary"]].iterrows():
            folium.GeoJson(
                row["geometry"].__geo_interface__,
                style_function=lambda _: {"color": "#334", "weight": 1, "opacity": 0.5},
            ).add_to(m)
        for _, row in layer[layer["is_primary"]].iterrows():
            folium.GeoJson(
                row["geometry"].__geo_interface__,
                style_function=lambda _, c=clr: {"color": c, "weight": 4, "opacity": 0.9},
            ).add_to(m)
    except FileNotFoundError:
        pass

    tti_map = {}
    if seg_df is not None:
        sub = seg_df[
            (seg_df["corridor"] == config.CORRIDORS[corridor]["label"]) &
            (seg_df["peak"]     == peak)
        ]
        for _, row in sub.iterrows():
            tti_map[row["from_stop"]] = row["mean_tti"]

    for _, stop in get_stop_geodataframe(corridor).iterrows():
        folium.CircleMarker(
            location=[stop["lat"], stop["lng"]],
            radius=7, color="#111", weight=2,
            fill=True, fill_color=_tti_hex(tti_map.get(stop["name"])),
            fill_opacity=1.0,
            tooltip=folium.Tooltip(
                f"<b>{stop['name']}</b><br>"
                + (f"TTI: {tti_map[stop['name']]:.2f}" if stop["name"] in tti_map else "No data")
            ),
        ).add_to(m)

    m.fit_bounds([[bounds["min_lat"], bounds["min_lng"]], [bounds["max_lat"], bounds["max_lng"]]])
    st_folium(m, use_container_width=True, height=420, returned_objects=[])

# ── Transit table ─────────────────────────────────────────────────────────────

def render_transit_table(seg_df, corridor, peak):
    if seg_df is None:
        st.info("No segment data yet.")
        return
    sub = seg_df[
        (seg_df["corridor"] == config.CORRIDORS[corridor]["label"]) &
        (seg_df["peak"]     == peak)
    ].copy()
    if sub.empty:
        st.info("No segment data for this selection.")
        return
    sub["Delay (min)"] = (sub["mean_delay_s"] / 60).round(1)
    sub["Speed km/h"]  = sub["mean_speed_kmph"].round(1)
    sub["TTI"]         = sub["mean_tti"].round(3)
    sub["LOS"]         = sub["los_mode"]
    sub = sub.rename(columns={"from_stop": "From", "to_stop": "To"})
    st.dataframe(
        sub[["From", "To", "TTI", "LOS", "Speed km/h", "Delay (min)"]],
        use_container_width=True, hide_index=True, height=400,
    )

# ── Charts ────────────────────────────────────────────────────────────────────

def render_railway(raw_df, corridor, peak):
    if raw_df is None:
        st.info("No raw data yet.")
        return
    try:
        fig = viz.railway_dashboard(kpi.enrich(raw_df), corridor, peak)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.info(f"Railway board: {e}")

def render_io(raw_df, corridor):
    if raw_df is None:
        st.info("No raw data yet.")
        return
    try:
        fig = viz.inbound_outbound_chart(kpi.enrich(raw_df), corridor)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.info(f"Chart: {e}")


# ── Trend Summary ─────────────────────────────────────────────────────────────────────────────

def render_trend_summary(hist_df, corridor):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    st.subheader("Trend Summary")

    if hist_df is None or hist_df.empty:
        st.info("No historical data yet. Trends will appear after multiple collection runs.")
        return

    label = config.CORRIDORS[corridor]["label"]
    sub = hist_df[hist_df["Corridor"] == label].copy()

    if sub.empty:
        st.info(f"No historical data for {label} yet.")
        return

    sub["Date"] = pd.to_datetime(sub["Date"])
    sub = sub.sort_values("Date")

    am = sub[sub["Peak"] == "AM"]
    pm = sub[sub["Peak"] == "PM"]

    # ── PTI trend ──────────────────────────────────────────
    st.markdown("#### Planning Time Index over Time")
    fig_pti = go.Figure()
    if not am.empty:
        fig_pti.add_trace(go.Scatter(
            x=am["Date"], y=am["Planning Time Index (PTI)"],
            name="AM Peak", mode="lines+markers",
            line=dict(color="#ff6b2b", width=2),
            marker=dict(size=6),
        ))
    if not pm.empty:
        fig_pti.add_trace(go.Scatter(
            x=pm["Date"], y=pm["Planning Time Index (PTI)"],
            name="PM Peak", mode="lines+markers",
            line=dict(color="#29b6f6", width=2),
            marker=dict(size=6),
        ))
    fig_pti.add_hline(
        y=config.PTI_AUDIT_THRESHOLD,
        line_dash="dash", line_color="red",
        annotation_text=f"Audit threshold {config.PTI_AUDIT_THRESHOLD}",
        annotation_position="top right",
    )
    fig_pti.update_layout(
        height=300, xaxis_title="Date", yaxis_title="PTI",
        legend=dict(orientation="h"),
        margin=dict(l=20, r=20, t=20, b=20),
    )
    st.plotly_chart(fig_pti, use_container_width=True)

    # ── Speed + Delay trends ──────────────────────────────────
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Average Speed (km/h)")
        fig_spd = go.Figure()
        if not am.empty:
            fig_spd.add_trace(go.Scatter(x=am["Date"], y=am["Average Speed (km/h)"],
                name="AM", mode="lines+markers", line=dict(color="#ff6b2b", width=2)))
        if not pm.empty:
            fig_spd.add_trace(go.Scatter(x=pm["Date"], y=pm["Average Speed (km/h)"],
                name="PM", mode="lines+markers", line=dict(color="#29b6f6", width=2)))
        fig_spd.add_hline(y=20, line_dash="dash", line_color="orange",
            annotation_text="20 km/h norm")
        fig_spd.update_layout(height=250, margin=dict(l=20,r=20,t=20,b=20),
            legend=dict(orientation="h"))
        st.plotly_chart(fig_spd, use_container_width=True)

    with c2:
        st.markdown("#### Corridor Delay (min)")
        fig_dly = go.Figure()
        if not am.empty:
            fig_dly.add_trace(go.Scatter(x=am["Date"], y=am["Total Corridor Delay (min)"],
                name="AM", mode="lines+markers", line=dict(color="#ff6b2b", width=2)))
        if not pm.empty:
            fig_dly.add_trace(go.Scatter(x=pm["Date"], y=pm["Total Corridor Delay (min)"],
                name="PM", mode="lines+markers", line=dict(color="#29b6f6", width=2)))
        fig_dly.add_hline(y=10, line_dash="dash", line_color="orange",
            annotation_text="10 min flag")
        fig_dly.update_layout(height=250, margin=dict(l=20,r=20,t=20,b=20),
            legend=dict(orientation="h"))
        st.plotly_chart(fig_dly, use_container_width=True)

    # ── Summary stats ────────────────────────────────────────────
    st.markdown("#### Statistical Summary")
    summary_rows = []
    for peak_key, peak_df, peak_label in [("AM", am, "AM Peak"), ("PM", pm, "PM Peak")]:
        if peak_df.empty:
            continue
        pti_col = "Planning Time Index (PTI)"
        spd_col = "Average Speed (km/h)"
        dly_col = "Total Corridor Delay (min)"
        summary_rows.append({
            "Peak":           peak_label,
            "Runs":           len(peak_df),
            "Mean PTI":       round(peak_df[pti_col].mean(), 3),
            "Max PTI":        round(peak_df[pti_col].max(), 3),
            "Days PTI > 1.6": int((peak_df[pti_col] > 1.6).sum()),
            "Mean Speed":     round(peak_df[spd_col].mean(), 1),
            "Min Speed":      round(peak_df[spd_col].min(), 1),
            "Mean Delay":     round(peak_df[dly_col].mean(), 1),
            "Max Delay":      round(peak_df[dly_col].max(), 1),
        })
    if summary_rows:
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
        st.caption(f"Based on {len(sub)} collection runs · {sub['Date'].min().strftime('%d %b')} to {sub['Date'].max().strftime('%d %b %Y')}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    corridor, peak = render_sidebar()
    now    = _now_ist()
    status = _peak_status(now)
    cd     = config.CORRIDORS[corridor]
    stops  = [s for s in cd["stops"] if s["lat"] is not None]

    # Header
    c1, c2 = st.columns([3, 1])
    c1.markdown(f"# {cd['description'].upper()}")
    c1.caption(f"{cd['label']}  ·  {config.PEAK_WINDOWS[peak]['label']}  ·  {len(stops)} stops  ·  {cd['length_km']} km")
    c2.markdown(f"<p style='text-align:right;margin-top:20px'>{now.strftime('%d %b %Y  %H:%M IST')}</p>", unsafe_allow_html=True)

    render_ticker(status)
    st.divider()

    kpi_df = _load_kpi_table()
    seg_df = _load_segment_summary()
    raw_df = _load_raw()

    st.subheader("Performance Indicators")
    render_kpis(kpi_df, corridor, peak)
    render_kpi_guide()
    st.divider()

    col_map, col_tbl = st.columns([3, 2])
    with col_map:
        st.subheader("Corridor Map")
        render_map(seg_df, corridor, peak)
    with col_tbl:
        st.subheader("Transit Times")
        render_transit_table(seg_df, corridor, peak)

    st.divider()

    col_r, col_i = st.columns(2)
    with col_r:
        st.subheader("Railway TTI Board")
        render_railway(raw_df, corridor, peak)
    with col_i:
        st.subheader("Inbound vs Outbound")
        render_io(raw_df, corridor)

    if kpi_df is not None:
        st.divider()
        st.subheader("Full KPI Table")
        st.dataframe(kpi_df, use_container_width=True, hide_index=True)

    # Trend summary
    hist_df = _load_historical()
    if hist_df is not None:
        st.divider()
        render_trend_summary(hist_df, corridor)

    st.caption("Google Maps Distance Matrix API · GS Road 34 stops · NH37 12 stops · HCM 6th Ed. · MORTH 2018 VOT")

if __name__ == "__main__":
    main()
