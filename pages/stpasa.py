import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from downloader import download_latest_stpasa, get_latest_stpasa_local
from parser import load_regionsolution, REGION_DISPLAY

REGION_COLOURS = {
    "NSW": "#1f77b4",
    "QLD": "#d62728",
    "VIC": "#2ca02c",
    "SA":  "#ff7f0e",
    "TAS": "#9467bd",
}

REGION_COLOURS_FAINT = {
    "NSW": "rgba(31,119,180,0.15)",
    "QLD": "rgba(214,39,40,0.15)",
    "VIC": "rgba(44,160,44,0.15)",
    "SA":  "rgba(255,127,14,0.15)",
    "TAS": "rgba(148,103,189,0.15)",
}

st_autorefresh(interval=3_600_000, key="stpasa_autorefresh")


@st.cache_data(show_spinner=False)
def load_data(zip_path: str) -> pd.DataFrame:
    from pathlib import Path
    return load_regionsolution(Path(zip_path))


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("STPASA Dashboard")
    st.caption("Short Term PASA — AEMO (hourly updates)")
    st.divider()

    if "stpasa_download_status" not in st.session_state:
        with st.spinner("Checking for new STPASA data..."):
            try:
                _, msg = download_latest_stpasa()
                st.session_state["stpasa_download_status"] = msg
            except Exception as e:
                st.session_state["stpasa_download_status"] = f"Download failed: {e}"

    st.info(st.session_state["stpasa_download_status"])

    if st.button("Check for new data"):
        st.session_state.pop("stpasa_download_status", None)
        st.cache_data.clear()
        with st.spinner("Checking NEMWEB..."):
            try:
                _, msg = download_latest_stpasa()
                st.session_state["stpasa_download_status"] = msg
                st.success(msg)
            except Exception as e:
                st.session_state["stpasa_download_status"] = f"Download failed: {e}"
                st.error(st.session_state["stpasa_download_status"])

    st.divider()

    zip_path = get_latest_stpasa_local()
    if zip_path is None:
        st.error("No STPASA file found. Click 'Check for new data'.")
        st.stop()

    st.caption(f"Latest: `{zip_path.name}`")
    st.divider()

    all_regions = list(REGION_DISPLAY.values())
    selected_regions = st.multiselect("Regions", options=all_regions, default=all_regions)
    if not selected_regions:
        st.warning("Select at least one region.")
        st.stop()

    st.divider()
    st.caption("Auto-refreshes every hour")


# ── Load data ─────────────────────────────────────────────────────────────────
df = load_data(str(zip_path))

if df.empty:
    st.error("Could not parse REGIONSOLUTION data from the ZIP file.")
    st.stop()

df_f = df[df["REGION_LABEL"].isin(selected_regions)].copy()

min_dt = df_f["INTERVAL_DATETIME"].min()
max_dt = df_f["INTERVAL_DATETIME"].max()
run_dt = df["RUN_DATETIME"].dropna().max()
run_label = run_dt.strftime("%d %b %Y %H:%M") if pd.notna(run_dt) else "unknown"


# ── Header ────────────────────────────────────────────────────────────────────
st.header("Short Term PASA — Supply Adequacy Forecast")
st.caption(f"Forecast run: **{run_label}** | Horizon: {min_dt:%d %b %Y} – {max_dt:%d %b %Y} | Source: AEMO NEMWEB")

st.divider()


# ── Section 1: Status cards ───────────────────────────────────────────────────
st.subheader("Current Reserve Status by Region")
st.caption("Based on the first forecast interval in this run.")

region_cols = st.columns(len(selected_regions))
for i, region in enumerate(selected_regions):
    df_r = df_f[df_f["REGION_LABEL"] == region].sort_values("INTERVAL_DATETIME")
    with region_cols[i]:
        if df_r.empty:
            st.metric(region, "No data")
            continue

        first = df_r.iloc[0]
        surplus_cap  = first.get("SURPLUSCAPACITY")
        surplus_res  = first.get("SURPLUSRESERVE")
        reserve_cond = first.get("RESERVECONDITION")
        lor_cond     = first.get("LORCONDITION")

        if pd.notna(lor_cond) and lor_cond > 0:
            colour, label = "red", f"LOR{int(lor_cond)} Active"
        elif pd.notna(reserve_cond) and reserve_cond > 0:
            colour, label = "orange", "Reserve Condition"
        elif pd.notna(surplus_cap) and surplus_cap < 200:
            colour, label = "orange", "Marginal"
        else:
            colour, label = "green", "Adequate"

        bg       = {"green": "#e6f4ea", "orange": "#fff3e0", "red": "#fce8e6"}.get(colour, "#f5f5f5")
        cap_text = f"Surplus capacity: {surplus_cap:,.0f} MW" if pd.notna(surplus_cap) else ""
        res_text = f"Surplus reserve: {surplus_res:,.0f} MW"  if pd.notna(surplus_res) else ""

        st.markdown(
            f'<div style="background:{bg};border-left:5px solid {colour};'
            f'border-radius:6px;padding:12px 16px;margin-bottom:4px">'
            f'<div style="font-size:20px;font-weight:700">{region}</div>'
            f'<div style="font-size:14px;color:{colour};font-weight:600">{label}</div>'
            f'<div style="font-size:12px;color:#555">{cap_text}</div>'
            f'<div style="font-size:12px;color:#555">{res_text}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.divider()


# ── Section 2: Demand Forecast ────────────────────────────────────────────────
st.subheader("Demand Forecast — P10 / P50 / P90")
st.caption(
    "Half-hourly demand forecast over the 7-day horizon. "
    "Solid line = P50 (median), dashed = P10 (high demand) / P90 (low demand). "
    "Shaded band spans P10 → P90."
)

fig_dem = go.Figure()
for region in selected_regions:
    df_r   = df_f[df_f["REGION_LABEL"] == region].sort_values("INTERVAL_DATETIME")
    colour = REGION_COLOURS.get(region, "#888")
    faint  = REGION_COLOURS_FAINT.get(region, "rgba(128,128,128,0.15)")

    df_band = df_r.dropna(subset=["DEMAND10", "DEMAND90"])
    if not df_band.empty:
        fig_dem.add_trace(go.Scatter(
            x=pd.concat([df_band["INTERVAL_DATETIME"], df_band["INTERVAL_DATETIME"].iloc[::-1]]),
            y=pd.concat([df_band["DEMAND10"], df_band["DEMAND90"].iloc[::-1]]),
            fill="toself", fillcolor=faint,
            line=dict(color="rgba(0,0,0,0)"),
            name=f"{region} P10-P90", showlegend=False, hoverinfo="skip",
        ))

    df_p50 = df_r.dropna(subset=["DEMAND50"])
    if not df_p50.empty:
        fig_dem.add_trace(go.Scatter(
            x=df_p50["INTERVAL_DATETIME"], y=df_p50["DEMAND50"],
            name=region, line=dict(color=colour, width=2),
            hovertemplate="%{x|%d %b %H:%M}<br>%{y:,.0f} MW<extra>" + region + " P50</extra>",
        ))

    for col, dash, lbl in [("DEMAND10", "dot", "P10"), ("DEMAND90", "dash", "P90")]:
        df_c = df_r.dropna(subset=[col])
        if not df_c.empty:
            fig_dem.add_trace(go.Scatter(
                x=df_c["INTERVAL_DATETIME"], y=df_c[col],
                name=f"{region} {lbl}", showlegend=False,
                line=dict(color=colour, width=1, dash=dash),
                hovertemplate="%{x|%d %b %H:%M}<br>%{y:,.0f} MW<extra>" + f"{region} {lbl}" + "</extra>",
            ))

fig_dem.update_layout(
    yaxis_title="MW",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    margin=dict(l=0, r=0, t=30, b=0),
    height=380,
    hovermode="x unified",
)
st.plotly_chart(fig_dem, use_container_width=True)

st.divider()


# ── Section 3: Surplus Capacity ───────────────────────────────────────────────
st.subheader("Surplus Capacity")
st.caption("Available generation above the capacity requirement (MW). Values below zero indicate a capacity deficit.")

fig_sc = go.Figure()
for region in selected_regions:
    df_r = df_f[df_f["REGION_LABEL"] == region].sort_values("INTERVAL_DATETIME").dropna(subset=["SURPLUSCAPACITY"])
    if df_r.empty:
        continue
    colour = REGION_COLOURS.get(region, "#888")
    fig_sc.add_trace(go.Scatter(
        x=df_r["INTERVAL_DATETIME"], y=df_r["SURPLUSCAPACITY"],
        name=region, line=dict(color=colour, width=2),
        fill="tozeroy",
        hovertemplate="%{x|%d %b %H:%M}<br>%{y:,.0f} MW<extra>" + region + "</extra>",
    ))

fig_sc.add_hline(y=0, line_color="black", line_width=1.5)
fig_sc.update_layout(
    yaxis_title="MW above capacity requirement",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    margin=dict(l=0, r=0, t=30, b=0),
    height=360,
    hovermode="x unified",
)
st.plotly_chart(fig_sc, use_container_width=True)

st.divider()


# ── Section 4: Surplus Reserve ────────────────────────────────────────────────
st.subheader("Surplus Reserve")
st.caption("Generation above the reserve requirement (MW). Negative values trigger a Reserve Condition.")

fig_sr = go.Figure()
for region in selected_regions:
    df_r = df_f[df_f["REGION_LABEL"] == region].sort_values("INTERVAL_DATETIME").dropna(subset=["SURPLUSRESERVE"])
    if df_r.empty:
        continue
    colour = REGION_COLOURS.get(region, "#888")
    fig_sr.add_trace(go.Scatter(
        x=df_r["INTERVAL_DATETIME"], y=df_r["SURPLUSRESERVE"],
        name=region, line=dict(color=colour, width=2),
        fill="tozeroy",
        hovertemplate="%{x|%d %b %H:%M}<br>%{y:,.0f} MW<extra>" + region + "</extra>",
    ))

fig_sr.add_hline(y=0, line_color="black", line_width=1.5)
fig_sr.update_layout(
    yaxis_title="MW above reserve requirement",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    margin=dict(l=0, r=0, t=30, b=0),
    height=360,
    hovermode="x unified",
)
st.plotly_chart(fig_sr, use_container_width=True)

st.divider()


# ── Section 5: LOR Levels ─────────────────────────────────────────────────────
st.subheader("LOR1 and LOR2 Levels")
st.caption(
    "Calculated LOR1 (reserve) and LOR2 (capacity) thresholds in MW. "
    "When surplus reserve falls below LOR1, AEMO issues a market notice. "
    "When surplus capacity falls below LOR2, load shedding risk rises."
)

col_lor1, col_lor2 = st.columns(2)

with col_lor1:
    st.markdown("**LOR1 Level**")
    fig_l1 = go.Figure()
    for region in selected_regions:
        df_r = df_f[df_f["REGION_LABEL"] == region].sort_values("INTERVAL_DATETIME").dropna(subset=["CALCULATEDLOR1LEVEL"])
        if df_r.empty:
            continue
        colour = REGION_COLOURS.get(region, "#888")
        fig_l1.add_trace(go.Scatter(
            x=df_r["INTERVAL_DATETIME"], y=df_r["CALCULATEDLOR1LEVEL"],
            name=region, line=dict(color=colour, width=2),
            hovertemplate="%{x|%d %b %H:%M}<br>%{y:,.0f} MW<extra>" + region + " LOR1</extra>",
        ))
    fig_l1.update_layout(
        yaxis_title="MW",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=0, r=0, t=10, b=0),
        height=320,
        hovermode="x unified",
    )
    st.plotly_chart(fig_l1, use_container_width=True)

with col_lor2:
    st.markdown("**LOR2 Level**")
    fig_l2 = go.Figure()
    for region in selected_regions:
        df_r = df_f[df_f["REGION_LABEL"] == region].sort_values("INTERVAL_DATETIME").dropna(subset=["CALCULATEDLOR2LEVEL"])
        if df_r.empty:
            continue
        colour = REGION_COLOURS.get(region, "#888")
        fig_l2.add_trace(go.Scatter(
            x=df_r["INTERVAL_DATETIME"], y=df_r["CALCULATEDLOR2LEVEL"],
            name=region, line=dict(color=colour, width=2),
            hovertemplate="%{x|%d %b %H:%M}<br>%{y:,.0f} MW<extra>" + region + " LOR2</extra>",
        ))
    fig_l2.update_layout(
        yaxis_title="MW",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=0, r=0, t=10, b=0),
        height=320,
        hovermode="x unified",
    )
    st.plotly_chart(fig_l2, use_container_width=True)

st.divider()
st.caption(
    "Source: AEMO NEMWEB — Short Term PASA Reports | Updated hourly | "
    "REGIONSOLUTION table | RUNTYPE: LOR"
)
