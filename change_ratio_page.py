from __future__ import annotations

import os
import glob
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from hydrocron_client import fetch_lake_timeseries

st.set_page_config(page_title="Change Ratio Analysis", layout="wide")

APP_DIR = Path(__file__).resolve().parent
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
HIST_COLS = [f"{m}_mean" for m in MONTHS]


def inject_css() -> None:
    st.markdown(
        """
        <style>
            .stApp {
                background: #06101d;
                color: #f8fafc;
            }

            [data-testid="stSidebar"] {
                background: #101827;
            }

            .block-container {
                padding-top: 1.1rem !important;
                padding-left: 1.2rem !important;
                padding-right: 1.2rem !important;
                max-width: 100% !important;
            }

            .app-sub {
                color: #93c5fd;
                margin: 0;
                line-height: 1.35;
            }

            .metric-card {
                background: linear-gradient(90deg, #0f3d1e 0%, #104b2c 100%);
                border: 1px solid rgba(34,197,94,0.25);
                border-radius: 12px;
                padding: 14px 16px;
                margin-bottom: 14px;
                color: #dcfce7;
                font-weight: 600;
            }

            div[data-testid="stMetric"] {
                background: #0b1626;
                border: 1px solid rgba(255,255,255,0.08);
                padding: 14px 16px;
                border-radius: 16px;
            }

            div[data-testid="stMetricLabel"] {
                color: #cbd5e1 !important;
            }

            div[data-testid="stMetricValue"] {
                color: #f8fafc !important;
            }

            .dryness-card {
                background: #0b1626;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 16px;
                padding: 14px 14px 8px 14px;
                margin-bottom: 14px;
            }

            .dryness-card-title {
                color: #cbd5e1;
                font-size: 0.98rem;
                font-weight: 600;
                margin-bottom: 0.45rem;
            }

            .month-chip-wrap {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
            }

            .month-chip {
                min-width: 64px;
                text-align: center;
                padding: 10px 8px;
                border-radius: 12px;
                font-weight: 700;
                font-size: 14px;
                border: 1px solid;
            }

            .month-chip.dry {
                background: #4b1110;
                border-color: #b91c1c;
                color: #ffe4e6;
            }

            .month-chip.normal {
                background: #0c2d48;
                border-color: #0284c7;
                color: #e0f2fe;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def load_historical_monthly_means(data_dir: str) -> pd.DataFrame | None:
    patterns = [
        os.path.join(data_dir, "historical_monthly_mean*.xlsx"),
        os.path.join(data_dir, "historical_monthly_mean*.xls"),
        os.path.join(data_dir, "historical_monthly_mean*.csv"),
    ]
    files: list[str] = []
    for p in patterns:
        files.extend(glob.glob(p))
    if not files:
        return None

    path = sorted(files)[0]
    if path.lower().endswith(".csv"):
        hist = pd.read_csv(path)
    else:
        hist = pd.read_excel(path)

    hist.columns = [c.strip() for c in hist.columns]

    if "lake_id" not in hist.columns:
        return None
    for c in HIST_COLS:
        if c not in hist.columns:
            return None

    hist["lake_id"] = hist["lake_id"].astype(str).str.strip()
    for c in HIST_COLS:
        hist[c] = pd.to_numeric(hist[c], errors="coerce")

    return hist


def compute_change_ratio(df_swot: pd.DataFrame, lake_id: str, hist_df: pd.DataFrame) -> pd.DataFrame | None:
    if df_swot is None or df_swot.empty:
        return None

    sw = df_swot.copy()
    if "time_str" not in sw.columns or "area_total" not in sw.columns:
        return None

    sw["time_str"] = pd.to_datetime(sw["time_str"], errors="coerce", utc=True)
    sw["area_total"] = pd.to_numeric(sw["area_total"], errors="coerce")

    if "quality_f" in sw.columns:
        sw["quality_f"] = pd.to_numeric(sw["quality_f"], errors="coerce")
    else:
        sw["quality_f"] = np.nan

    sw = sw.dropna(subset=["time_str", "area_total"])
    if sw.empty:
        return None

    sw["Month"] = sw["time_str"].dt.strftime("%b")
    sw = sw[sw["Month"].isin(MONTHS)]
    if sw.empty:
        return None

    q0 = sw[sw["quality_f"] == 0]
    q1 = sw[sw["quality_f"] == 1]

    swot_q0 = q0.groupby("Month")["area_total"].mean()
    swot_q1 = q1.groupby("Month")["area_total"].mean()

    swot_monthly = pd.Series(index=MONTHS, dtype="float64")
    used_quality = pd.Series(index=MONTHS, dtype="float64")

    for m in MONTHS:
        if m in swot_q0.index and pd.notna(swot_q0.loc[m]):
            swot_monthly.loc[m] = float(swot_q0.loc[m])
            used_quality.loc[m] = 0
        elif m in swot_q1.index and pd.notna(swot_q1.loc[m]):
            swot_monthly.loc[m] = float(swot_q1.loc[m])
            used_quality.loc[m] = 1
        else:
            swot_monthly.loc[m] = np.nan
            used_quality.loc[m] = np.nan

    lake_id_str = str(lake_id).strip()
    row = hist_df[hist_df["lake_id"] == lake_id_str]
    if row.empty:
        return None

    hist_vals = row.iloc[0][HIST_COLS].to_numpy(dtype=float)
    hist_monthly = pd.Series(hist_vals, index=MONTHS)

    denom = hist_monthly.replace(0, np.nan)
    cr = (swot_monthly - hist_monthly) / denom

    out = pd.DataFrame({
        "Month": MONTHS,
        "SWOT_mean": swot_monthly.values,
        "HIST_mean": hist_monthly.values,
        "Change_Ratio": cr.values,
        "Used_quality": used_quality.values,
    })
    return out


def build_dryness_summary(cr_df: pd.DataFrame, percentile_fraction: float = 0.20):
    if cr_df is None or cr_df.empty:
        return None, None, None

    df = cr_df.copy()
    df = df.dropna(subset=["Month", "Change_Ratio"]).reset_index(drop=True)

    if df.empty:
        return None, None, None

    threshold_percentile = percentile_fraction * 100.0
    threshold_value = float(np.percentile(df["Change_Ratio"].astype(float), threshold_percentile))

    df["Dry_Status"] = np.where(df["Change_Ratio"] < threshold_value, "Dry", "Normal")
    df["Is_Dry"] = df["Dry_Status"] == "Dry"

    return df, threshold_value, threshold_percentile


def render_relative_dryness_panel(cr_df: pd.DataFrame, lake_id: str):
    BG = "#06101d"
    CARD = "#0b1626"
    TEXT = "#f8fafc"
    SUBTEXT = "#cbd5e1"
    DRY = "#ef4444"
    NORMAL = "#38bdf8"
    THRESH = "#fbbf24"
    LINE = "#7dd3fc"
    GRID = "rgba(255,255,255,0.10)"

    st.markdown("### Relative Dryness Summary")

    slider_col, metric_col = st.columns([5, 1])

    with slider_col:
        percentile_fraction = st.slider(
            "Select dryness percentile threshold",
            min_value=0.05,
            max_value=0.50,
            value=0.20,
            step=0.01,
            format="%.2f",
            key=f"dryness_slider_{lake_id}",
        )

    with metric_col:
        st.metric("Threshold", f"{percentile_fraction:.2f}")

    result_df, threshold_value, threshold_percentile = build_dryness_summary(
        cr_df, percentile_fraction
    )

    if result_df is None or result_df.empty:
        st.warning("No valid change-ratio data available for dryness summary.")
        return

    dry_count = int(result_df["Is_Dry"].sum())
    total_count = int(len(result_df))
    normal_count = total_count - dry_count
    dry_percent = (dry_count / total_count) * 100 if total_count > 0 else 0.0

    left_panel, right_panel = st.columns([0.95, 1.45], gap="large")

    with left_panel:
        st.markdown('<div class="dryness-card">', unsafe_allow_html=True)
        st.markdown('<div class="dryness-card-title">Dry Month Summary</div>', unsafe_allow_html=True)

        fig_donut = go.Figure(
            data=[
                go.Pie(
                    labels=["Dry", "Normal"],
                    values=[dry_count, normal_count],
                    hole=0.72,
                    marker=dict(
                        colors=[DRY, NORMAL],
                        line=dict(color=BG, width=2),
                    ),
                    textinfo="none",
                    sort=False,
                    showlegend=False,
                )
            ]
        )
        fig_donut.update_layout(
            height=220,
            margin=dict(l=10, r=10, t=0, b=0),
            paper_bgcolor=CARD,
            plot_bgcolor=CARD,
            font=dict(color=TEXT),
            annotations=[
                dict(
                    text=f"<b>{dry_count}</b><br><span style='font-size:12px'>Dry</span>",
                    x=0.5,
                    y=0.5,
                    showarrow=False,
                    font=dict(color=TEXT, size=20),
                )
            ],
        )
        st.plotly_chart(fig_donut, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="dryness-card">', unsafe_allow_html=True)
        st.markdown('<div class="dryness-card-title">Dry Share</div>', unsafe_allow_html=True)

        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=dry_percent,
            number={"suffix": "%", "font": {"color": TEXT, "size": 24}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": SUBTEXT},
                "bar": {"color": DRY},
                "bgcolor": CARD,
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 50], "color": "#12324a"},
                    {"range": [50, 100], "color": "#3a1717"},
                ],
            },
            title={"text": "", "font": {"color": SUBTEXT, "size": 14}},
        ))
        fig_gauge.update_layout(
            height=220,
            margin=dict(l=10, r=10, t=10, b=0),
            paper_bgcolor=CARD,
            plot_bgcolor=CARD,
            font=dict(color=TEXT),
        )
        st.plotly_chart(fig_gauge, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="dryness-card">', unsafe_allow_html=True)
        st.markdown('<div class="dryness-card-title">Dry Months by Month</div>', unsafe_allow_html=True)

        month_html = ['<div class="month-chip-wrap">']
        for _, row in result_df.iterrows():
            month = str(row["Month"])
            cls = "dry" if bool(row["Is_Dry"]) else "normal"
            month_html.append(f'<div class="month-chip {cls}">{month}</div>')
        month_html.append("</div>")
        st.markdown("".join(month_html), unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    with right_panel:
        fig_line = go.Figure()

        fig_line.add_trace(
            go.Scatter(
                x=result_df["Month"].astype(str),
                y=result_df["Change_Ratio"],
                mode="lines+markers",
                line=dict(width=3, color=LINE),
                marker=dict(size=8, color=LINE),
                name="Change Ratio",
                hovertemplate="<b>%{x}</b><br>Change Ratio: %{y:.3f}<extra></extra>",
            )
        )

        dry_df = result_df[result_df["Is_Dry"]].copy()
        if not dry_df.empty:
            fig_line.add_trace(
                go.Scatter(
                    x=dry_df["Month"].astype(str),
                    y=dry_df["Change_Ratio"],
                    mode="markers",
                    marker=dict(
                        size=14,
                        color=DRY,
                        symbol="diamond",
                        line=dict(color="#ffffff", width=1.1),
                    ),
                    name="Dry Months",
                    hovertemplate="<b>%{x}</b><br>Dry Month<br>Change Ratio: %{y:.3f}<extra></extra>",
                )
            )

        fig_line.add_hline(
            y=threshold_value,
            line_dash="dash",
            line_color=THRESH,
            line_width=2,
            annotation_text=f"{threshold_percentile:.0f}th percentile = {threshold_value:.3f}",
            annotation_position="top left",
            annotation_font_color=THRESH,
        )

        fig_line.update_layout(
            title=f"Change Ratio vs Selected Percentile Threshold • Lake ID: {lake_id}",
            height=720,
            margin=dict(l=20, r=20, t=60, b=20),
            paper_bgcolor=BG,
            plot_bgcolor=CARD,
            font=dict(color=TEXT),
            legend=dict(
                orientation="h",
                y=1.02,
                x=1,
                xanchor="right",
                bgcolor="rgba(0,0,0,0)"
            ),
            hovermode="x unified",
        )

        fig_line.update_xaxes(
            title="Month",
            categoryorder="array",
            categoryarray=MONTHS,
            showgrid=False,
            color=TEXT,
        )

        fig_line.update_yaxes(
            title="Change Ratio",
            showgrid=True,
            gridcolor=GRID,
            zeroline=True,
            zerolinecolor="rgba(255,255,255,0.18)",
            color=TEXT,
        )

        st.plotly_chart(fig_line, use_container_width=True)

    show_cols = [c for c in ["Month", "SWOT_mean", "HIST_mean", "Change_Ratio", "Used_quality", "Dry_Status"] if c in result_df.columns]
    table_df = result_df[show_cols].copy()

    if "SWOT_mean" in table_df.columns:
        table_df["SWOT_mean"] = pd.to_numeric(table_df["SWOT_mean"], errors="coerce").round(3)
    if "HIST_mean" in table_df.columns:
        table_df["HIST_mean"] = pd.to_numeric(table_df["HIST_mean"], errors="coerce").round(3)
    if "Change_Ratio" in table_df.columns:
        table_df["Change_Ratio"] = pd.to_numeric(table_df["Change_Ratio"], errors="coerce").round(3)

    # st.markdown("#### Dry Summary Table")
    # st.dataframe(table_df, use_container_width=True, hide_index=True)


def load_df_from_session_or_query():
    lake_id = st.session_state.get("selected_lake_id")
    df = st.session_state.get("last_df", pd.DataFrame())

    qp = st.query_params
    qp_lake_id = qp.get("lake_id", None)
    qp_start = qp.get("start_date", None)
    qp_end = qp.get("end_date", None)

    if qp_lake_id:
        lake_id = str(qp_lake_id)

    if lake_id is None:
        return None, pd.DataFrame(), None, None

    if isinstance(df, pd.DataFrame) and not df.empty:
        return lake_id, df, qp_start, qp_end

    if qp_start is None or qp_end is None:
        return lake_id, pd.DataFrame(), qp_start, qp_end

    try:
        df = fetch_lake_timeseries(
            lake_id=lake_id,
            start_time=pd.to_datetime(qp_start).date(),
            end_time=pd.to_datetime(qp_end).date(),
        )
        st.session_state["selected_lake_id"] = lake_id
        st.session_state["last_df"] = df
        return lake_id, df, qp_start, qp_end
    except Exception as exc:
        st.error(f"Hydrocron request failed while loading analysis page: {exc}")
        return lake_id, pd.DataFrame(), qp_start, qp_end


def main() -> None:
    inject_css()

    st.markdown(
        '<div class="app-sub">Change ratio, threshold selection, dry-month detection, and summary tables</div>',
        unsafe_allow_html=True,
    )

    top1, top2 = st.columns([7, 2], gap="small")
    with top2:
        st.link_button("Home ↗", "/", type="secondary")
        st.link_button("Site Verified Lakes ↗", "/site-verified-lakes", type="secondary")

    lake_id, df, qp_start, qp_end = load_df_from_session_or_query()

    if not lake_id:
        st.warning("No lake selected yet. Open the Home page, select a lake, and fetch SWOT data first.")
        return

    st.markdown(
        f'<div class="metric-card">Selected Lake ID: {lake_id}</div>',
        unsafe_allow_html=True,
    )

    if qp_start and qp_end:
        st.caption(f"Loaded date window: {qp_start} to {qp_end}")

    if not isinstance(df, pd.DataFrame) or df.empty:
        st.warning("No SWOT data loaded yet. Go to the Home page, select a lake, fetch data, and then reopen this page.")
        return

    st.markdown("### 📉 Change Ratio (SWOT monthly mean area vs Historical monthly mean)")
    st.caption("Change Ratio = (SWOT_mean - HIST_mean) / HIST_mean")

    hist_df = load_historical_monthly_means(str(APP_DIR / "data"))
    if hist_df is None:
        st.warning(
            "Historical monthly mean file not found in `data/`.\n\n"
            "Put Excel in `data/` named like `historical_monthly_mean_....xlsx`\n"
            "Required columns: lake_id, Jan_mean ... Dec_mean"
        )
        return

    cr_df = compute_change_ratio(df, str(lake_id), hist_df)
    if cr_df is None:
        st.warning("Could not compute change ratio (lake not found in historical file or SWOT monthly means missing).")
        return

    render_relative_dryness_panel(cr_df, str(lake_id))

    # with st.expander(
    #     "Show mean values used (SWOT mean, Historical mean, Change Ratio, Used_quality)",
    #     expanded=False,
    # ):
    #     st.dataframe(cr_df, use_container_width=True)

    with st.expander("Returned Hydrocron Table", expanded=False):
        st.dataframe(df, use_container_width=True, height=280)


if __name__ == "__main__":
    main()