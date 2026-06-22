import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from downloader import download_latest_mtpasa, get_latest_mtpasa_local, count_mtpasa_local_files
from parser import load_region_result, load_lolp, load_region_summary, REGION_DISPLAY

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


@st.cache_data(show_spinner=False)
def load_data(zip_path: str):
    from pathlib import Path
    p = Path(zip_path)
    result  = load_region_result(p)
    lolp    = load_lolp(p)
    summary = load_region_summary(p)
    return result, lolp, summary


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("MTPASA Dashboard")
    st.caption("Medium Term PASA - AEMO")
    st.divider()

    if "download_status" not in st.session_state:
        with st.spinner("Checking for new MTPASA data..."):
            try:
                _, msg = download_latest_mtpasa()
                st.session_state["download_status"] = msg
            except Exception as e:
                st.session_state["download_status"] = f"Download failed: {e}"

    st.info(st.session_state["download_status"])

    if st.button("Check for new data"):
        st.session_state.pop("download_status", None)
        st.cache_data.clear()
        with st.spinner("Checking NEMWEB..."):
            try:
                _, msg = download_latest_mtpasa()
                st.session_state["download_status"] = msg
                st.success(msg)
            except Exception as e:
                st.session_state["download_status"] = f"Download failed: {e}"
                st.error(st.session_state["download_status"])

    st.divider()

    zip_path = get_latest_mtpasa_local()
    if zip_path is None:
        st.error("No MTPASA file found in data folder.")
        st.stop()

    st.metric("Weeks stored", count_mtpasa_local_files())
    st.caption(f"Latest: `{zip_path.name}`")
    st.divider()

    all_regions = list(REGION_DISPLAY.values())
    selected_regions = st.multiselect("Regions", options=all_regions, default=all_regions)
    if not selected_regions:
        st.warning("Select at least one region.")
        st.stop()


# ── Load and filter data ──────────────────────────────────────────────────────
result, lolp, summary = load_data(str(zip_path))

if result.empty:
    st.error("Could not parse REGIONRESULT data from the ZIP file.")
    st.stop()

poe50 = result[result["DEMAND_POE_TYPE"].str.strip().str.upper() == "POE50"].copy()
poe10 = result[result["DEMAND_POE_TYPE"].str.strip().str.upper() == "POE10"].copy()

_primary_poe_label = "50% POE" if not poe50.empty else "10% POE"
_primary_poe = poe50 if not poe50.empty else poe10


def filter_region(df):
    return df[df["REGION_LABEL"].isin(selected_regions)]


poe50_f   = filter_region(poe50)
poe10_f   = filter_region(poe10)
primary_f = filter_region(_primary_poe)

min_day = result["DAY"].dropna().min()
max_day = result["DAY"].dropna().max()

if pd.isna(min_day) or pd.isna(max_day):
    st.error("Could not determine forecast date range from the ZIP file.")
    st.stop()

with st.sidebar:
    st.divider()
    date_range = st.slider(
        "Forecast horizon",
        min_value=min_day.to_pydatetime(),
        max_value=max_day.to_pydatetime(),
        value=(min_day.to_pydatetime(), max_day.to_pydatetime()),
        format="MMM YYYY",
    )


def apply_date(df, col="DAY"):
    return df[(df[col] >= pd.Timestamp(date_range[0])) & (df[col] <= pd.Timestamp(date_range[1]))]


poe50_fd   = apply_date(poe50_f)
poe10_fd   = apply_date(poe10_f)
primary_fd = apply_date(primary_f)
lolp_fd    = apply_date(filter_region(lolp)) if not lolp.empty else pd.DataFrame()


# ── Header ────────────────────────────────────────────────────────────────────
run_dt    = result["RUN_DATETIME"].dropna().max()
run_label = run_dt.strftime("%d %b %Y %H:%M") if pd.notna(run_dt) else "unknown"

st.header("Medium Term PASA - Supply & Demand Forecast")
st.caption(f"Forecast run: **{run_label}** | Demand scenario: **{_primary_poe_label}** | Source: AEMO NEMWEB")


# ── Section 1: Status cards ───────────────────────────────────────────────────
st.subheader("Reserve Status by Region")

region_cols = st.columns(len(selected_regions))
for i, region in enumerate(selected_regions):
    df_r = primary_fd[primary_fd["REGION_LABEL"] == region]
    with region_cols[i]:
        if df_r.empty:
            st.metric(region, "No data")
            continue

        first   = df_r.sort_values("DAY").iloc[0]
        demand  = first.get("DEMAND")
        avail   = first.get("TOTALAVAILABLEGEN50")
        surplus = (avail - demand) if (pd.notna(avail) and pd.notna(demand)) else None

        lolp_val = None
        if not lolp_fd.empty:
            lr = lolp_fd[lolp_fd["REGION_LABEL"] == region].sort_values("DAY")
            if not lr.empty:
                lolp_val = lr.iloc[0].get("LOSSOFLOADPROBABILITY")

        if lolp_val is not None and lolp_val > 5:
            colour, label = "red", "High Risk"
        elif lolp_val is not None and lolp_val > 0.5:
            colour, label = "orange", "Elevated Risk"
        elif surplus is not None and surplus < 300:
            colour, label = "orange", "Marginal"
        else:
            colour, label = "green", "Adequate"

        bg           = {"green": "#e6f4ea", "orange": "#fff3e0", "red": "#fce8e6"}.get(colour, "#f5f5f5")
        surplus_text = f"Surplus: {surplus:,.0f} MW" if surplus is not None else ""
        lolp_text    = f"LOLP: {lolp_val:.1f}%"    if lolp_val is not None else ""

        st.markdown(
            f'<div style="background:{bg};border-left:5px solid {colour};'
            f'border-radius:6px;padding:12px 16px;margin-bottom:4px">'
            f'<div style="font-size:20px;font-weight:700">{region}</div>'
            f'<div style="font-size:14px;color:{colour};font-weight:600">{label}</div>'
            f'<div style="font-size:12px;color:#555">{surplus_text}</div>'
            f'<div style="font-size:12px;color:#555">{lolp_text}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.divider()


# ── Supply & Demand Breakdown ─────────────────────────────────────────────────
st.subheader("Supply & Demand Breakdown")
st.caption(
    "Stacked areas show the supply stack. "
    "Black line = operational demand (50% POE). "
    "Lower panel = daily Loss of Load Probability (%)."
)

from plotly.subplots import make_subplots as _make_subplots

_sd_tabs = st.tabs(selected_regions)
for _tab, _region in zip(_sd_tabs, selected_regions):
    with _tab:
        _df_r   = primary_fd[primary_fd["REGION_LABEL"] == _region].sort_values("DAY")
        _lolp_r = lolp_fd[lolp_fd["REGION_LABEL"] == _region].sort_values("DAY") if not lolp_fd.empty else pd.DataFrame()

        if _df_r.empty:
            st.info(f"No data for {_region}.")
            continue

        _has_lolp = not _lolp_r.empty and "LOSSOFLOADPROBABILITY" in _lolp_r.columns
        _n_rows   = 2 if _has_lolp else 1

        _fig = _make_subplots(
            rows=_n_rows, cols=1,
            shared_xaxes=True,
            row_heights=[0.72, 0.28] if _has_lolp else [1.0],
            vertical_spacing=0.04,
        )

        _layers = [
            ("AGGREGATEINSTALLEDCAPACITY", "Installed Capacity",        "#cbd5e1", 0.6),
            ("TOTALAVAILABLEGEN50",         "Available Generation",      "#0ea5e9", 0.75),
            ("TOTALINTERMITTENTGEN50",      "Intermittent Generation",   "#10b981", 0.75),
            ("DEMANDSIDEPARTICIPATION50",   "Demand Side Participation", "#8b5cf6", 0.75),
        ]
        for _col, _lbl, _clr, _op in _layers:
            if _col not in _df_r.columns:
                continue
            _dc = _df_r.dropna(subset=[_col])
            if _dc.empty:
                continue
            _fig.add_trace(go.Scatter(
                x=_dc["DAY"], y=_dc[_col],
                name=_lbl, fill="tozeroy", mode="lines",
                line=dict(color=_clr, width=0), fillcolor=_clr, opacity=_op,
                hovertemplate="%{x|%d %b %Y}<br>%{y:,.0f} MW<extra>" + _lbl + "</extra>",
            ), row=1, col=1)

        _dd = _df_r.dropna(subset=["DEMAND"])
        if not _dd.empty:
            _fig.add_trace(go.Scatter(
                x=_dd["DAY"], y=_dd["DEMAND"],
                name="Operational Demand", mode="lines",
                line=dict(color="#0f172a", width=2),
                hovertemplate="%{x|%d %b %Y}<br>%{y:,.0f} MW<extra>Demand</extra>",
            ), row=1, col=1)

        if _has_lolp:
            _dl = _lolp_r.dropna(subset=["LOSSOFLOADPROBABILITY"])
            _fig.add_trace(go.Bar(
                x=_dl["DAY"], y=_dl["LOSSOFLOADPROBABILITY"],
                name="LOLP %", marker_color="#f43f5e", opacity=0.85,
                hovertemplate="%{x|%d %b %Y}<br>%{y:.2f}%<extra>LOLP</extra>",
            ), row=2, col=1)
            _fig.update_yaxes(title_text="LOLP (%)", row=2, col=1)

        _fig.update_yaxes(title_text="MW", row=1, col=1)
        _fig.update_layout(
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            margin=dict(l=0, r=0, t=30, b=0),
            height=520 if _has_lolp else 400,
            hovermode="x unified",
        )
        st.plotly_chart(_fig, use_container_width=True)

st.divider()


# ── Section 2: Demand Forecast ────────────────────────────────────────────────
st.subheader("Demand Forecast - 10% and 50% Probability of Exceedance")

fig_demand = go.Figure()
for region in selected_regions:
    colour = REGION_COLOURS.get(region, "#888")
    df50   = poe50_fd[poe50_fd["REGION_LABEL"] == region].sort_values("DAY")
    df10   = poe10_fd[poe10_fd["REGION_LABEL"] == region].sort_values("DAY")

    if not df50.empty:
        fig_demand.add_trace(go.Scatter(
            x=df50["DAY"], y=df50["DEMAND"],
            name=f"{region} 50% POE",
            line=dict(color=colour, width=2),
            hovertemplate="%{x|%d %b %Y}<br>%{y:,.0f} MW<extra>" + region + " 50% POE</extra>",
        ))
    if not df10.empty:
        fig_demand.add_trace(go.Scatter(
            x=df10["DAY"], y=df10["DEMAND"],
            name=f"{region} 10% POE",
            line=dict(color=colour, width=1.5, dash="dot"),
            hovertemplate="%{x|%d %b %Y}<br>%{y:,.0f} MW<extra>" + region + " 10% POE</extra>",
        ))

fig_demand.update_layout(
    yaxis_title="MW (peak half-hour)",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    margin=dict(l=0, r=0, t=30, b=0),
    height=380,
    hovermode="x unified",
)
st.plotly_chart(fig_demand, use_container_width=True)


# ── Section 3: Available Generation vs Demand ─────────────────────────────────
st.subheader(f"Available Generation vs Demand ({_primary_poe_label})")

if len(selected_regions) == 1:
    region = selected_regions[0]
    df_r   = primary_fd[primary_fd["REGION_LABEL"] == region].sort_values("DAY")
    colour = REGION_COLOURS.get(region, "#888")

    fig_gap = go.Figure()
    if "TOTALAVAILABLEGEN50" in df_r.columns:
        fig_gap.add_trace(go.Bar(
            x=df_r["DAY"], y=df_r["TOTALAVAILABLEGEN50"],
            name="Available Generation",
            marker_color=colour, opacity=0.6,
            hovertemplate="%{x|%d %b %Y}<br>%{y:,.0f} MW<extra>Available Gen</extra>",
        ))
    if "DEMAND" in df_r.columns:
        fig_gap.add_trace(go.Scatter(
            x=df_r["DAY"], y=df_r["DEMAND"],
            name="Demand (50% POE)",
            line=dict(color="black", width=2),
            hovertemplate="%{x|%d %b %Y}<br>%{y:,.0f} MW<extra>Demand</extra>",
        ))
    fig_gap.update_layout(
        yaxis_title="MW", barmode="overlay",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=0, r=0, t=30, b=0), height=350,
    )
    st.plotly_chart(fig_gap, use_container_width=True)
else:
    fig_gap = go.Figure()
    for region in selected_regions:
        df_r = primary_fd[primary_fd["REGION_LABEL"] == region].sort_values("DAY")
        if "TOTALAVAILABLEGEN50" in df_r.columns and "DEMAND" in df_r.columns:
            df_r = df_r.dropna(subset=["TOTALAVAILABLEGEN50", "DEMAND"]).copy()
            df_r["SURPLUS"] = df_r["TOTALAVAILABLEGEN50"] - df_r["DEMAND"]
            colour = REGION_COLOURS.get(region, "#888")
            fig_gap.add_trace(go.Scatter(
                x=df_r["DAY"], y=df_r["SURPLUS"],
                name=region, line=dict(color=colour, width=2),
                hovertemplate="%{x|%d %b %Y}<br>%{y:,.0f} MW<extra>" + region + "</extra>",
            ))

    fig_gap.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.5)
    fig_gap.update_layout(
        yaxis_title="Generation surplus over demand (MW)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=0, r=0, t=30, b=0), height=350,
        hovermode="x unified",
    )
    st.plotly_chart(fig_gap, use_container_width=True)


# ── Section 4: Reserve Surplus ────────────────────────────────────────────────
st.subheader("Reserve Surplus Over Forecast Horizon")

fig_res = go.Figure()
for region in selected_regions:
    df_r = primary_fd[primary_fd["REGION_LABEL"] == region].sort_values("DAY")
    if "TOTALAVAILABLEGEN50" not in df_r.columns or "DEMAND" not in df_r.columns:
        continue
    df_r = df_r.dropna(subset=["TOTALAVAILABLEGEN50", "DEMAND"]).copy()
    df_r["SURPLUS"] = df_r["TOTALAVAILABLEGEN50"] - df_r["DEMAND"]
    colour = REGION_COLOURS.get(region, "#888")
    fig_res.add_trace(go.Scatter(
        x=df_r["DAY"], y=df_r["SURPLUS"],
        name=region,
        line=dict(color=colour, width=2),
        fill="tozeroy",
        hovertemplate="%{x|%d %b %Y}<br>%{y:,.0f} MW<extra>" + region + "</extra>",
    ))

fig_res.add_hline(y=0, line_color="black", line_width=1.5)
fig_res.update_layout(
    yaxis_title="MW above demand  (negative = deficit)",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    margin=dict(l=0, r=0, t=30, b=0), height=380,
    hovermode="x unified",
)
st.plotly_chart(fig_res, use_container_width=True)


def supply_chart(col_base: str, title: str, caption: str) -> None:
    c10, c50, c90 = f"{col_base}10", f"{col_base}50", f"{col_base}90"
    st.subheader(title)
    st.caption(caption)
    fig = go.Figure()
    has_data = False
    for region in selected_regions:
        df_r   = primary_fd[primary_fd["REGION_LABEL"] == region].sort_values("DAY")
        colour = REGION_COLOURS.get(region, "#888")
        faint  = REGION_COLOURS_FAINT.get(region, "rgba(128,128,128,0.15)")
        if df_r.empty or c50 not in df_r.columns:
            continue
        df_r = df_r.dropna(subset=[c50])
        has_data = True

        if c10 in df_r.columns and c90 in df_r.columns:
            df_r2 = df_r.dropna(subset=[c10, c90])
            fig.add_trace(go.Scatter(
                x=pd.concat([df_r2["DAY"], df_r2["DAY"].iloc[::-1]]),
                y=pd.concat([df_r2[c90], df_r2[c10].iloc[::-1]]),
                fill="toself", fillcolor=faint,
                line=dict(color="rgba(0,0,0,0)"),
                name=f"{region} P10-P90", showlegend=False, hoverinfo="skip",
            ))
        fig.add_trace(go.Scatter(
            x=df_r["DAY"], y=df_r[c50],
            name=region,
            line=dict(color=colour, width=2),
            hovertemplate="%{x|%d %b %Y}<br>%{y:,.0f} MW<extra>" + region + "</extra>",
        ))
        for col, dash_style, lbl in [(c10, "dot", "P10"), (c90, "dash", "P90")]:
            if col in df_r.columns:
                fig.add_trace(go.Scatter(
                    x=df_r["DAY"], y=df_r[col],
                    name=f"{region} {lbl}",
                    line=dict(color=colour, width=1, dash=dash_style),
                    showlegend=False,
                    hovertemplate="%{x|%d %b %Y}<br>%{y:,.0f} MW<extra>" + f"{region} {lbl}" + "</extra>",
                ))
    if not has_data:
        st.info("Data not available for the selected filters.")
        return
    fig.update_layout(
        yaxis_title="MW",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=0, r=0, t=30, b=0),
        height=360,
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.divider()


supply_chart(
    "TOTALSCHEDULEDGEN",
    "Total Scheduled Generation",
    "Dispatchable generation (coal, gas, hydro, batteries) committed by AEMO. "
    "Solid line = P50 forecast. Shaded band + dashed lines = P10 / P90 range.",
)
supply_chart(
    "TOTALINTERMITTENTGEN",
    "Total Intermittent Generation",
    "Unscheduled variable renewable generation (wind, rooftop solar). "
    "Higher variability than scheduled generation.",
)
supply_chart(
    "TOTALSEMISCHEDULEGEN",
    "Total Semi-Scheduled Generation",
    "Large-scale renewables (utility solar, wind farms) that can be curtailed by AEMO.",
)
supply_chart(
    "DEMANDSIDEPARTICIPATION",
    "Demand Side Participation",
    "Demand response — load that can be reduced during periods of high demand or low supply.",
)
supply_chart(
    "TOTALAVAILABLEGEN",
    "Total Available Generation",
    "Sum of all available generation (scheduled + semi-scheduled + intermittent + demand response), "
    "net of outages and constraints.",
)


if not lolp_fd.empty:
    st.subheader("Loss of Load Probability (LOLP) by Region")
    fig_lolp = go.Figure()
    for region in selected_regions:
        df_r = lolp_fd[lolp_fd["REGION_LABEL"] == region].sort_values("DAY")
        if df_r.empty or "LOSSOFLOADPROBABILITY" not in df_r.columns:
            continue
        colour = REGION_COLOURS.get(region, "#888")
        fig_lolp.add_trace(go.Scatter(
            x=df_r["DAY"], y=df_r["LOSSOFLOADPROBABILITY"],
            name=region, line=dict(color=colour, width=2),
            hovertemplate="%{x|%d %b %Y}<br>LOLP: %{y:.2f}%<extra>" + region + "</extra>",
        ))
    fig_lolp.update_layout(
        yaxis_title="Loss of Load Probability (%)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=0, r=0, t=30, b=0), height=320,
        hovermode="x unified",
    )
    st.plotly_chart(fig_lolp, use_container_width=True)


st.divider()

st.header("Region Summary (Monthly)")
st.caption("Monthly aggregates from REGIONSUMMARY — energy in MWh, unserved energy risk, and reliability flag (LRC).")

if summary.empty:
    st.info("REGIONSUMMARY data not available.")
else:
    sum_poe50 = summary[summary["DEMAND_POE_TYPE"].str.strip().str.upper() == "POE50"].copy()
    sum_poe10 = summary[summary["DEMAND_POE_TYPE"].str.strip().str.upper() == "POE10"].copy()

    def filter_summary(df):
        df = df[df["REGION_LABEL"].isin(selected_regions)]
        return df[
            (df["PERIOD_ENDING"] >= pd.Timestamp(date_range[0])) &
            (df["PERIOD_ENDING"] <= pd.Timestamp(date_range[1]))
        ]

    sum50_f = filter_summary(sum_poe50)
    sum10_f = filter_summary(sum_poe10)

    st.subheader("Monthly Native Demand")
    st.caption("Total energy consumed per region per month (GWh). POE50 = median demand scenario, POE10 = high demand scenario.")

    fig_nd = go.Figure()
    for region in selected_regions:
        colour = REGION_COLOURS.get(region, "#888")
        df50   = sum50_f[sum50_f["REGION_LABEL"] == region].sort_values("PERIOD_ENDING")
        df10   = sum10_f[sum10_f["REGION_LABEL"] == region].sort_values("PERIOD_ENDING")
        if not df50.empty and "NATIVEDEMAND" in df50.columns:
            fig_nd.add_trace(go.Scatter(
                x=df50["PERIOD_ENDING"],
                y=df50["NATIVEDEMAND"] / 1000,
                name=f"{region} 50% POE",
                line=dict(color=colour, width=2),
                hovertemplate="%{x|%b %Y}<br>%{y:,.1f} GWh<extra>" + region + " 50% POE</extra>",
            ))
        if not df10.empty and "NATIVEDEMAND" in df10.columns:
            fig_nd.add_trace(go.Scatter(
                x=df10["PERIOD_ENDING"],
                y=df10["NATIVEDEMAND"] / 1000,
                name=f"{region} 10% POE",
                line=dict(color=colour, width=1.5, dash="dot"),
                hovertemplate="%{x|%b %Y}<br>%{y:,.1f} GWh<extra>" + region + " 10% POE</extra>",
            ))
    fig_nd.update_layout(
        yaxis_title="GWh per month",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=0, r=0, t=30, b=0),
        height=360,
        hovermode="x unified",
    )
    st.plotly_chart(fig_nd, use_container_width=True)

    st.divider()

    st.subheader("Unserved Energy (USE) — Monthly Average")
    st.caption(
        "Expected energy not supplied due to insufficient generation (MWh per month). "
        "Values above zero indicate periods of forecast supply shortfall."
    )

    fig_use = go.Figure()
    has_any_use = False
    for region in selected_regions:
        colour = REGION_COLOURS.get(region, "#888")
        df50   = sum50_f[sum50_f["REGION_LABEL"] == region].sort_values("PERIOD_ENDING")
        if df50.empty or "USE_AVERAGE" not in df50.columns:
            continue
        df50 = df50.dropna(subset=["USE_AVERAGE"])
        if df50["USE_AVERAGE"].sum() > 0:
            has_any_use = True
        fig_use.add_trace(go.Bar(
            x=df50["PERIOD_ENDING"],
            y=df50["USE_AVERAGE"],
            name=f"{region} USE avg",
            marker_color=colour,
            opacity=0.75,
            hovertemplate="%{x|%b %Y}<br>%{y:,.1f} MWh<extra>" + region + " USE avg</extra>",
        ))
    fig_use.update_layout(
        yaxis_title="MWh unserved per month",
        barmode="group",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=0, r=0, t=30, b=0),
        height=320,
        hovermode="x unified",
    )
    if not has_any_use:
        st.info(
            "All USE values are currently zero — no forecast supply shortfalls in this run. "
            "This chart will show non-zero values if a future MTPASA run identifies a shortfall period."
        )
    st.plotly_chart(fig_use, use_container_width=True)

    st.divider()

    st.subheader("Unserved Energy — Percentile Distribution")
    st.caption("Distribution of USE outcomes across all modelled scenarios. A wider spread means greater uncertainty.")

    use_pct_region = st.selectbox("Region for USE distribution", options=selected_regions, key="use_pct_region")
    df_pct = sum50_f[sum50_f["REGION_LABEL"] == use_pct_region].sort_values("PERIOD_ENDING")

    pct_cols = [c for c in ["USE_PERCENTILE10", "USE_PERCENTILE50", "USE_PERCENTILE90", "USE_PERCENTILE100"] if c in df_pct.columns]
    if df_pct.empty or not pct_cols:
        st.info("Percentile data not available.")
    else:
        fig_pct = go.Figure()
        pct_colours = {
            "USE_PERCENTILE10": "#2ca02c", "USE_PERCENTILE50": "#1f77b4",
            "USE_PERCENTILE90": "#ff7f0e", "USE_PERCENTILE100": "#d62728",
        }
        pct_labels = {
            "USE_PERCENTILE10": "10th pctile", "USE_PERCENTILE50": "50th pctile",
            "USE_PERCENTILE90": "90th pctile", "USE_PERCENTILE100": "100th pctile (worst)",
        }
        for col in pct_cols:
            fig_pct.add_trace(go.Scatter(
                x=df_pct["PERIOD_ENDING"],
                y=df_pct[col],
                name=pct_labels.get(col, col),
                line=dict(color=pct_colours.get(col, "#888"), width=2),
                hovertemplate="%{x|%b %Y}<br>%{y:,.1f} MWh<extra>" + pct_labels.get(col, col) + "</extra>",
            ))
        fig_pct.update_layout(
            yaxis_title="MWh unserved",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            margin=dict(l=0, r=0, t=30, b=0),
            height=320,
            hovermode="x unified",
        )
        st.plotly_chart(fig_pct, use_container_width=True)

    st.divider()

    st.subheader("Loss of Reserve Condition (LRC) Flag")
    st.caption("LRC = 1 means AEMO has identified a period where reserves fall below the minimum requirement.")

    lrc_data = []
    for region in selected_regions:
        df50 = sum50_f[sum50_f["REGION_LABEL"] == region].sort_values("PERIOD_ENDING")
        if df50.empty or "LRC" not in df50.columns:
            continue
        for _, row in df50.iterrows():
            lrc_data.append({
                "Month": row["PERIOD_ENDING"],
                "Region": region,
                "LRC": pd.to_numeric(row["LRC"], errors="coerce"),
            })

    if lrc_data:
        lrc_df  = pd.DataFrame(lrc_data)
        fig_lrc = go.Figure()
        for region in selected_regions:
            df_r   = lrc_df[lrc_df["Region"] == region].sort_values("Month")
            colour = REGION_COLOURS.get(region, "#888")
            fig_lrc.add_trace(go.Scatter(
                x=df_r["Month"],
                y=df_r["LRC"],
                name=region,
                mode="lines+markers",
                line=dict(color=colour, width=2),
                marker=dict(size=6),
                hovertemplate="%{x|%b %Y}<br>LRC: %{y}<extra>" + region + "</extra>",
            ))
        fig_lrc.update_layout(
            yaxis=dict(title="LRC flag", tickvals=[0, 1], ticktext=["0 - OK", "1 - Condition triggered"]),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            margin=dict(l=0, r=0, t=30, b=0),
            height=280,
            hovermode="x unified",
        )
        st.plotly_chart(fig_lrc, use_container_width=True)
    else:
        st.info("LRC data not available.")


st.divider()
st.caption(
    "Source: AEMO NEMWEB - Medium Term PASA Reports | Updated weekly | "
    "REGIONRESULT: daily MW forecasts | REGIONSUMMARY: monthly MWh aggregates"
)
