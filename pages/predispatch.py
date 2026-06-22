import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from downloader import (
    download_latest_predispatch, get_latest_predispatch_local,
    download_latest_dispatchis, get_latest_dispatchis_local,
    get_all_dispatchis_today_local, download_all_dispatchis_today,
    download_latest_p5min, get_latest_p5min_local,
)
from parser import load_predispatch_region, load_dispatch_price, load_p5min_regionsolution

STATES = ["NSW", "QLD", "VIC", "SA", "TAS"]

REGION_COLOURS = {
    "NSW": "#1f77b4",
    "QLD": "#d62728",
    "VIC": "#2ca02c",
    "SA":  "#ff7f0e",
    "TAS": "#9467bd",
}

PRICE_PERIODS = [
    ("ON", "Overnight",    "12am–6am",  "Wind-weighted, lower-demand period",      0,  6),
    ("MP", "Morning Peak", "6am–10am",  "Demand ramp and system tightening",        6, 10),
    ("MD", "Midday",       "10am–4pm",  "Solar oversupply and negative price risk", 10, 16),
    ("EP", "Evening Peak", "4pm–8pm",   "Highest demand and price risk",            16, 20),
    ("LE", "Late Evening", "8pm–12am",  "Post-peak residual volatility",            20, 24),
]

PERIOD_COLOURS = {
    "ON": "#94a3b8",
    "MP": "#fbbf24",
    "MD": "#10b981",
    "EP": "#ef4444",
    "LE": "#8b5cf6",
}


def _hex_to_rgba(hex_colour: str, alpha: float) -> str:
    h = hex_colour.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


refresh_count = st_autorefresh(interval=300_000, key="predispatch_autorefresh")
_last = st.session_state.get("_pd_last_refresh", -1)
_is_autorefresh = refresh_count != _last
st.session_state["_pd_last_refresh"] = refresh_count


def _snapshot() -> dict:
    pd_p  = get_latest_predispatch_local()
    dis_p = get_latest_dispatchis_local()
    p5_p  = get_latest_p5min_local()
    return {
        "pd":  pd_p.name  if pd_p  else "",
        "dis": dis_p.name if dis_p else "",
        "p5":  p5_p.name  if p5_p  else "",
    }


def _fetch_all(spinner: bool = False, bulk_dis: bool = False):
    ctx = st.spinner("Checking NEMWEB...") if spinner else _null()
    with ctx:
        try:
            _, msg = download_latest_predispatch()
        except Exception as e:
            msg = f"Failed: {e}"
        for fn in (download_latest_dispatchis, download_latest_p5min):
            try:
                fn()
            except Exception:
                pass
        if bulk_dis:
            try:
                download_all_dispatchis_today()
            except Exception:
                pass
    return msg


class _null:
    def __enter__(self): return self
    def __exit__(self, *_): pass


@st.cache_data(show_spinner=False)
def _load_pd(path: str) -> pd.DataFrame:
    from pathlib import Path
    return load_predispatch_region(Path(path))


@st.cache_data(show_spinner=False)
def _load_p5(path: str) -> pd.DataFrame:
    from pathlib import Path
    return load_p5min_regionsolution(Path(path))


@st.cache_data(show_spinner=False)
def _load_dis_today(paths: tuple) -> pd.DataFrame:
    from pathlib import Path
    dfs = []
    for p in paths:
        try:
            dfs.append(load_dispatch_price(Path(p)))
        except Exception:
            pass
    if not dfs:
        return pd.DataFrame()
    df = pd.concat(dfs, ignore_index=True)
    return df.drop_duplicates(subset=["SETTLEMENTDATE", "REGIONID"])


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Pre-Dispatch")
    st.caption("Spot price signal — all NEM states")
    st.divider()

    if "predispatch_status" not in st.session_state:
        msg = _fetch_all(spinner=True, bulk_dis=True)
        st.session_state["predispatch_status"] = msg
        st.session_state["_pd_files"] = _snapshot()
    elif _is_autorefresh:
        old = st.session_state.get("_pd_files", {})
        msg = _fetch_all(spinner=False)
        new = _snapshot()
        if new != old:
            st.cache_data.clear()
            st.session_state["_pd_files"] = new
        st.session_state["predispatch_status"] = msg

    st.info(st.session_state["predispatch_status"])

    if st.button("Refresh now"):
        st.session_state.pop("predispatch_status", None)
        st.cache_data.clear()
        msg = _fetch_all(spinner=True, bulk_dis=True)
        st.session_state["predispatch_status"] = msg
        st.session_state["_pd_files"] = _snapshot()

    st.divider()

    def _ts(path) -> str:
        import re
        if path is None:
            return "—"
        m = re.search(r"_(\d{12})_", path.name)
        if not m:
            return path.name
        try:
            return pd.to_datetime(m.group(1), format="%Y%m%d%H%M").strftime("%d %b %H:%M")
        except Exception:
            return m.group(1)

    pd_path  = get_latest_predispatch_local()
    dis_path = get_latest_dispatchis_local()
    p5_path  = get_latest_p5min_local()

    st.markdown("**Data sources**")
    st.markdown(
        f"| Source | Latest |\n|---|---|\n"
        f"| Pre-Dispatch 30min | {_ts(pd_path)} |\n"
        f"| DispatchIS (actual) | {_ts(dis_path)} |\n"
        f"| P5MIN (5min) | {_ts(p5_path)} |"
    )
    st.divider()
    st.caption("Auto-refreshes every 5 minutes")


# ── Load data ─────────────────────────────────────────────────────────────────
if pd_path is None:
    st.error("No Pre-Dispatch file found.")
    st.stop()

df_pd_all = _load_pd(str(pd_path))

try:
    df_p5_all = _load_p5(str(p5_path)) if p5_path else pd.DataFrame()
except Exception:
    df_p5_all = pd.DataFrame()

_today_dis_paths = tuple(str(p) for p in get_all_dispatchis_today_local())
try:
    df_dis_today = _load_dis_today(_today_dis_paths)
except Exception:
    df_dis_today = pd.DataFrame()

actual_prices: dict[str, tuple[float, str]] = {}
if not df_dis_today.empty:
    latest_dt = df_dis_today["SETTLEMENTDATE"].max()
    for _, row in df_dis_today[df_dis_today["SETTLEMENTDATE"] == latest_dt].iterrows():
        lbl = row.get("REGION_LABEL", "")
        rrp = row.get("RRP")
        if lbl and pd.notna(rrp):
            actual_prices[lbl] = (float(rrp), latest_dt.strftime("%d %b %H:%M"))

run_dt = df_pd_all["PREDISPATCHSEQNO"].dropna().max() if not df_pd_all.empty else None
run_label = run_dt.strftime("%d %b %Y %H:%M") if run_dt and pd.notna(run_dt) else "—"


# ── Header ────────────────────────────────────────────────────────────────────
st.title("AEMO Predispatch price signal")
st.caption(f"Pre-Dispatch run: **{run_label}** | Auto-refreshes every 5 minutes")

st.divider()


# ── AEST now ──────────────────────────────────────────────────────────────────
from datetime import datetime, timezone, timedelta as _dtdelta
_now           = pd.Timestamp(datetime.now(tz=timezone(_dtdelta(hours=10))).replace(tzinfo=None))
_today_date    = _now.date()
_tomorrow_date = (_now + pd.Timedelta(days=1)).date()


def _period_avg_for_date(df_region: pd.DataFrame, target_date, start_h: int, end_h: int):
    if end_h == 24:
        hmask = df_region["PERIODID"].dt.hour >= start_h
    else:
        hmask = (df_region["PERIODID"].dt.hour >= start_h) & (df_region["PERIODID"].dt.hour < end_h)
    date_mask = df_region["PERIODID"].dt.date == target_date
    if target_date == _today_date:
        sub = df_region.loc[date_mask & hmask & (df_region["PERIODID"] >= _now)].dropna(subset=["RRP"])
    else:
        sub = df_region.loc[date_mask & hmask].dropna(subset=["RRP"])
    return sub["RRP"].mean() if not sub.empty else None


def _render_card(col, code, label, hours, avg, day_str, is_active=False):
    val = f"${avg:,.2f}" if avg is not None else "—"
    clr = PERIOD_COLOURS[code]
    bg  = _hex_to_rgba(clr, 0.10)
    bdr = _hex_to_rgba(clr, 0.35)
    badge = (
        f'<span style="background:{clr};color:#fff;font-size:9px;'
        f'padding:1px 6px;border-radius:3px;margin-left:5px;vertical-align:middle">NOW</span>'
    ) if is_active else ""
    with col:
        st.markdown(
            f'<div style="background:{bg};border:1px solid {bdr};'
            f'border-left:4px solid {clr};border-radius:8px;padding:14px 16px;text-align:center">'
            f'<div style="font-size:12px;font-weight:700;color:{clr};text-transform:uppercase;letter-spacing:1px">'
            f'{code} · {label}{badge}</div>'
            f'<div style="font-size:11px;color:#64748b;margin-top:2px">{hours}</div>'
            f'<div style="font-size:22px;font-weight:700;color:#0f172a;margin-top:6px">{val}</div>'
            f'<div style="font-size:12px;color:#64748b;font-weight:600;margin-top:4px">{day_str}</div>'
            f'<div style="font-size:11px;color:#94a3b8">avg $/MWh</div>'
            f'</div>', unsafe_allow_html=True
        )


# ── State tabs ────────────────────────────────────────────────────────────────
tabs = st.tabs(STATES)
_shade_colours = {code: _hex_to_rgba(clr, 0.12) for code, clr in PERIOD_COLOURS.items()}

for tab, state in zip(tabs, STATES):
    with tab:
        df_pd  = df_pd_all[df_pd_all["REGION_LABEL"] == state].sort_values("PERIODID")
        df_p5  = (
            df_p5_all[df_p5_all["REGION_LABEL"] == state].sort_values("INTERVAL_DATETIME")
            if not df_p5_all.empty else pd.DataFrame()
        )
        df_act = (
            df_dis_today[df_dis_today["REGION_LABEL"] == state].sort_values("SETTLEMENTDATE")
            if not df_dis_today.empty else pd.DataFrame()
        )

        colour = REGION_COLOURS[state]
        actual_rrp, actual_dt = actual_prices.get(state, (None, ""))

        _act_col, _ = st.columns([1, 4])
        with _act_col:
            val = f"${actual_rrp:,.2f}" if actual_rrp is not None else "—"
            st.markdown(
                f'<div style="background:#0f172a;color:#fff;border-radius:8px;padding:14px 16px;text-align:center">'
                f'<div style="font-size:11px;opacity:0.7;text-transform:uppercase;letter-spacing:1px">Actual</div>'
                f'<div style="font-size:11px;opacity:0.5;margin-top:2px">{actual_dt}</div>'
                f'<div style="font-size:26px;font-weight:700;margin-top:6px">{val}</div>'
                f'<div style="font-size:11px;opacity:0.6">$/MWh</div>'
                f'</div>', unsafe_allow_html=True
            )

        if df_pd.empty:
            st.info(f"No predispatch data for {state}.")
            continue

        _today_cards = [
            (code, label, hours, sh, eh,
             _period_avg_for_date(df_pd, _today_date, sh, eh),
             (pd.Timestamp(_today_date) + pd.Timedelta(hours=sh))
             <= _now <
             (pd.Timestamp(_today_date) + pd.Timedelta(hours=eh)))
            for code, label, hours, desc, sh, eh in PRICE_PERIODS
            if (pd.Timestamp(_today_date) + pd.Timedelta(hours=eh)) > _now
        ]

        if _today_cards:
            st.caption("**Today**")
            _cols = st.columns(len(_today_cards))
            for _c, (code, label, hours, sh, eh, avg, is_active) in zip(_cols, _today_cards):
                _render_card(_c, code, label, hours, avg, "Today", is_active)

        st.caption("**Tomorrow**")
        _tomorrow_cards = [
            (code, label, hours, sh, eh, _period_avg_for_date(df_pd, _tomorrow_date, sh, eh))
            for code, label, hours, desc, sh, eh in PRICE_PERIODS
        ]
        _cols = st.columns(5)
        for _c, (code, label, hours, sh, eh, avg) in zip(_cols, _tomorrow_cards):
            _render_card(_c, code, label, hours, avg, "Tomorrow")

        st.markdown(f"**Realised Spot price and AEMO Predispatch price signal — {state}**")
        st.caption("Green = realised today (DispatchIS) | Solid = 30-min pre-dispatch | Dotted = P5MIN (5-min)")

        fig = go.Figure()

        if not df_act.empty:
            df_act_rrp = df_act.dropna(subset=["RRP"])
            if not df_act_rrp.empty:
                fig.add_trace(go.Scatter(
                    x=df_act_rrp["SETTLEMENTDATE"], y=df_act_rrp["RRP"],
                    name="Actual (today)",
                    line=dict(color="#16a34a", width=2),
                    hovertemplate="%{x|%d %b %H:%M}<br>$%{y:,.2f}/MWh<extra>Actual</extra>",
                ))

        df_rrp = df_pd.dropna(subset=["RRP"])
        if not df_rrp.empty:
            fig.add_trace(go.Scatter(
                x=df_rrp["PERIODID"], y=df_rrp["RRP"],
                name="Forecast 30min",
                line=dict(color=colour, width=2.5),
                hovertemplate="%{x|%d %b %H:%M}<br>$%{y:,.2f}/MWh<extra>30min</extra>",
            ))

        if not df_p5.empty:
            df_p5_rrp = df_p5.dropna(subset=["RRP"])
            if not df_p5_rrp.empty:
                fig.add_trace(go.Scatter(
                    x=df_p5_rrp["INTERVAL_DATETIME"], y=df_p5_rrp["RRP"],
                    name="Forecast 5min",
                    mode="lines",
                    line=dict(color=colour, width=1.5, dash="dot"),
                    hovertemplate="%{x|%d %b %H:%M}<br>$%{y:,.2f}/MWh<extra>5min</extra>",
                ))

        if not df_pd.empty:
            _min_x = df_pd["PERIODID"].min()
            _max_x = df_pd["PERIODID"].max()
            _day = _min_x.normalize()
            while _day <= _max_x:
                for code, _, _hours, _desc, sh, eh in PRICE_PERIODS:
                    _s = _day + pd.Timedelta(hours=sh)
                    _e = _day + pd.Timedelta(hours=eh)
                    if _e <= _now or _s >= _max_x:
                        continue
                    fig.add_vrect(
                        x0=_s, x1=_e,
                        fillcolor=_shade_colours.get(code, "rgba(0,0,0,0.03)"),
                        layer="below", line_width=0,
                    )
                _day += pd.Timedelta(days=1)

        fig.update_layout(
            yaxis_title="Spot Price ($/MWh)",
            xaxis_title=None,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            margin=dict(l=0, r=0, t=30, b=0),
            height=460,
            hovermode="x unified",
            plot_bgcolor="#f8fafc",
            paper_bgcolor="#ffffff",
        )
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(gridcolor="#e2e8f0")

        st.plotly_chart(fig, use_container_width=True)

st.divider()
st.caption("Source: AEMO NEMWEB — Predispatch Reports + P5MIN + DispatchIS | Physical run (INTERVENTION=0)")
