import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.markdown(
    """<style>
    section[data-testid="stMain"] > div:first-child {
        max-width: 100% !important;
        width: 100% !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        box-sizing: border-box !important;
    }
    </style>""",
    unsafe_allow_html=True,
)

from downloader import (
    download_latest_predispatch, get_latest_predispatch_local,
    download_latest_dispatchis, get_latest_dispatchis_local,
    get_all_dispatchis_today_local, get_all_dispatchis_yesterday_local,
    download_all_dispatchis_today,
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
    ("ON", "Overnight",    "12am–6am",   0,  6),
    ("MP", "Morning Peak", "6am–10am",   6, 10),
    ("MD", "Midday",       "10am–4pm",  10, 16),
    ("EP", "Evening Peak", "4pm–8pm",   16, 20),
    ("LE", "Late Evening", "8pm–12am",  20, 24),
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


# ── Auto-refresh ──────────────────────────────────────────────────────────────
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

_yday_dis_paths = tuple(str(p) for p in get_all_dispatchis_yesterday_local())
try:
    df_dis_yday = _load_dis_today(_yday_dis_paths) if _yday_dis_paths else pd.DataFrame()
except Exception:
    df_dis_yday = pd.DataFrame()

# Pre-compute per-state daily averages (today and yesterday)
def _state_avg(df: pd.DataFrame) -> dict[str, float]:
    if df.empty:
        return {}
    return (
        df.dropna(subset=["RRP"])
        .groupby("REGION_LABEL")["RRP"]
        .mean()
        .to_dict()
    )

_today_avgs = _state_avg(df_dis_today)
_yday_avgs  = _state_avg(df_dis_yday)

actual_prices: dict[str, tuple[float, str]] = {}
if not df_dis_today.empty:
    latest_dt = df_dis_today["SETTLEMENTDATE"].max()
    for _, row in df_dis_today[df_dis_today["SETTLEMENTDATE"] == latest_dt].iterrows():
        lbl = row.get("REGION_LABEL", "")
        rrp = row.get("RRP")
        if lbl and pd.notna(rrp):
            actual_prices[lbl] = (float(rrp), latest_dt.strftime("%d %b %H:%M"))

run_dt    = df_pd_all["PREDISPATCHSEQNO"].dropna().max() if not df_pd_all.empty else None
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


def _period_avg(df_region: pd.DataFrame, target_date, sh: int, eh: int):
    hmask = (
        df_region["PERIODID"].dt.hour >= sh
        if eh == 24
        else (df_region["PERIODID"].dt.hour >= sh) & (df_region["PERIODID"].dt.hour < eh)
    )
    date_mask = df_region["PERIODID"].dt.date == target_date
    if target_date == _today_date:
        sub = df_region.loc[date_mask & hmask & (df_region["PERIODID"] >= _now)].dropna(subset=["RRP"])
    else:
        sub = df_region.loc[date_mask & hmask].dropna(subset=["RRP"])
    return sub["RRP"].mean() if not sub.empty else None


# ── State summary cards (one per state, all periods as rows) ──────────────────
def _render_state_card(col, state: str, df_pd: pd.DataFrame):
    state_colour        = REGION_COLOURS[state]
    actual_rrp, act_dt = actual_prices.get(state, (None, ""))

    daily_avg = _today_avgs.get(state)
    yday_avg  = _yday_avgs.get(state)

    rows_today    = []
    rows_tomorrow = []
    for code, label, hours, sh, eh in PRICE_PERIODS:
        end_ts = pd.Timestamp(_today_date) + pd.Timedelta(hours=eh)
        if end_ts > _now:
            avg       = _period_avg(df_pd, _today_date, sh, eh)
            is_active = (
                pd.Timestamp(_today_date) + pd.Timedelta(hours=sh)
                <= _now <
                pd.Timestamp(_today_date) + pd.Timedelta(hours=eh)
            )
            rows_today.append((code, label, hours, avg, is_active))
        rows_tomorrow.append((code, label, hours, _period_avg(df_pd, _tomorrow_date, sh, eh)))

    def _row_html(code, label, hours, avg, is_active=False):
        clr  = PERIOD_COLOURS[code]
        val  = f"${avg:,.2f}" if avg is not None else "—"
        now_ = (
            f'<span style="background:{clr};color:#fff;font-size:8px;'
            f'padding:1px 5px;border-radius:3px;margin-left:4px">NOW</span>'
        ) if is_active else ""
        return (
            f'<div style="display:flex;align-items:center;padding:5px 0;'
            f'border-bottom:1px solid #f1f5f9">'
            f'<span style="width:6px;height:6px;border-radius:50%;background:{clr};'
            f'flex-shrink:0;margin-right:8px"></span>'
            f'<span style="font-size:11px;color:#475569;flex:1">'
            f'<b>{code}</b> {label}{now_}</span>'
            f'<span style="font-size:13px;font-weight:700;color:#0f172a">{val}</span>'
            f'</div>'
        )

    today_html    = "".join(_row_html(*r) for r in rows_today)
    tomorrow_html = "".join(_row_html(c, l, h, a) for c, l, h, a in rows_tomorrow)
    actual_price_html = (
        f'<span style="font-size:16px;font-weight:800;color:{state_colour}">'
        f'${actual_rrp:,.2f}</span>'
    ) if actual_rrp is not None else ""

    if daily_avg is not None and yday_avg is not None:
        avg_text = f"D-1 avg ${yday_avg:,.2f} | D avg ${daily_avg:,.2f}"
    elif daily_avg is not None:
        avg_text = f"D avg ${daily_avg:,.2f}"
    else:
        avg_text = None

    daily_avg_html = (
        f'<span style="font-size:13px;font-weight:600;color:{state_colour};opacity:0.7;margin-left:6px">'
        f'({avg_text})</span>'
    ) if avg_text is not None else ""

    header_bg     = _hex_to_rgba(state_colour, 0.12)
    border        = _hex_to_rgba(state_colour, 0.4)
    today_content = today_html or '<div style="font-size:11px;color:#94a3b8;padding:4px 0">No remaining periods</div>'

    with col:
        st.markdown(
            f'<div style="border:1px solid {border};border-top:4px solid {state_colour};'
            f'border-radius:8px;overflow:hidden">'
            f'<div style="background:{header_bg};padding:10px 14px;display:flex;'
            f'align-items:center;justify-content:space-between">'
            f'<span>'
            f'<span style="font-size:16px;font-weight:800;color:{state_colour}">{state}</span>'
            f'{daily_avg_html}'
            f'</span>'
            f'{actual_price_html}'
            f'</div>'
            f'<div style="padding:8px 14px 4px">'
            f'<div style="font-size:10px;font-weight:700;color:#94a3b8;'
            f'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">Today</div>'
            f'{today_content}'
            f'<div style="font-size:10px;font-weight:700;color:#94a3b8;'
            f'text-transform:uppercase;letter-spacing:0.5px;margin:8px 0 4px">Tomorrow</div>'
            f'{tomorrow_html}'
            f'</div></div>',
            unsafe_allow_html=True,
        )


cols = st.columns(5)
for col, state in zip(cols, STATES):
    df_pd = df_pd_all[df_pd_all["REGION_LABEL"] == state].sort_values("PERIODID")
    _render_state_card(col, state, df_pd)

st.divider()


# ── Charts — all states, stacked ──────────────────────────────────────────────
st.subheader("Realised Spot price and AEMO Predispatch price signal")
st.caption("Green = realised today (DispatchIS) | Solid = 30-min pre-dispatch | Dotted = P5MIN (5-min)")

_shade_colours = {code: _hex_to_rgba(clr, 0.12) for code, clr in PERIOD_COLOURS.items()}

for state in STATES:
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

    st.markdown(f"**{state}**")
    fig = go.Figure()

    if not df_act.empty:
        df_act_rrp = df_act.dropna(subset=["RRP"])
        if not df_act_rrp.empty:
            fig.add_trace(go.Scatter(
                x=df_act_rrp["SETTLEMENTDATE"], y=df_act_rrp["RRP"],
                name="Actual",
                line=dict(color="#16a34a", width=2),
                hovertemplate="%{x|%d %b %H:%M}<br>$%{y:,.2f}/MWh<extra>Actual</extra>",
            ))

    df_rrp = df_pd.dropna(subset=["RRP"])
    if not df_rrp.empty:
        fig.add_trace(go.Scatter(
            x=df_rrp["PERIODID"], y=df_rrp["RRP"],
            name="30min forecast",
            line=dict(color=colour, width=2.5),
            hovertemplate="%{x|%d %b %H:%M}<br>$%{y:,.2f}/MWh<extra>30min</extra>",
        ))

    if not df_p5.empty:
        df_p5_rrp = df_p5.dropna(subset=["RRP"])
        if not df_p5_rrp.empty:
            fig.add_trace(go.Scatter(
                x=df_p5_rrp["INTERVAL_DATETIME"], y=df_p5_rrp["RRP"],
                name="5min forecast",
                mode="lines",
                line=dict(color=colour, width=1.5, dash="dot"),
                hovertemplate="%{x|%d %b %H:%M}<br>$%{y:,.2f}/MWh<extra>5min</extra>",
            ))

    if not df_pd.empty:
        _min_x = df_pd["PERIODID"].min()
        _max_x = df_pd["PERIODID"].max()
        _day   = _min_x.normalize()
        while _day <= _max_x:
            for code, _, _hours, sh, eh in PRICE_PERIODS:
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
        yaxis_title="$/MWh",
        xaxis_title=None,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=0, r=0, t=30, b=0),
        height=320,
        hovermode="x unified",
        plot_bgcolor="#f8fafc",
        paper_bgcolor="#ffffff",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#e2e8f0")

    st.plotly_chart(fig, use_container_width=True)

st.divider()
st.caption("Source: AEMO NEMWEB — Predispatch Reports + P5MIN + DispatchIS | Physical run (INTERVENTION=0)")
