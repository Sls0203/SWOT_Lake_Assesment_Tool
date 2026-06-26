from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import streamlit as st
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import plotly.express as px

from hydrocron_client import fetch_lake_timeseries

st.set_page_config(page_title="India lake Volume analyser", layout="wide")

APP_DIR = Path(__file__).resolve().parent
LAKES_POINTS_PATH = APP_DIR / "data" / "final_lakes_779.geojson"
STATES_PATH = APP_DIR / "data" / "india_states.geojson"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def inject_css() -> None:
    st.markdown(
        """
        <style>
        /* Main page spacing */
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1400px;
        }

        /* Hide default Streamlit top gap slightly */
        header[data-testid="stHeader"] {
            background: transparent;
        }

        /* Sidebar */
        section[data-testid="stSidebar"] {
            background-color: #F4F8FB;
            border-right: 1px solid #E1E8EF;
        }

        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] label {
            color: #1E1E1E !important;
        }

        /* Main title */
        .main-title {
            font-size: 2.2rem;
            font-weight: 800;
            color: #12355B;
            margin-bottom: 0.2rem;
        }

        .main-subtitle {
            font-size: 1rem;
            color: #5C6B73;
            margin-bottom: 1.5rem;
        }

        /* Card box */
        .info-card {
            background-color: #FFFFFF;
            padding: 1rem 1.2rem;
            border-radius: 14px;
            border: 1px solid #E1E8EF;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
            margin-bottom: 1rem;
        }

        /* Buttons */
        div.stButton > button {
            border-radius: 10px;
            font-weight: 600;
        }

        div[data-testid="stLinkButton"] a {
            border-radius: 10px;
            font-weight: 600;
            text-decoration: none;
        }

        /* Inputs */
        input, textarea, select {
            border-radius: 8px !important;
        }

        /* Reduce huge empty spaces */
        .element-container {
            margin-bottom: 0.6rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data
def load_geojson(path: str) -> gpd.GeoDataFrame:
    return gpd.read_file(path,engine="pyogrio")


def extract_lake_id_from_popup(s: str | None) -> str | None:
    if not s:
        return None
    m = re.search(r"(\d+)", s)
    return m.group(1) if m else None


def remove_outliers_iqr(df: pd.DataFrame, col: str, k: float = 1.5) -> pd.DataFrame:
    s = pd.to_numeric(df[col], errors="coerce")
    q1 = s.quantile(0.25)
    q3 = s.quantile(0.75)
    iqr = q3 - q1
    if pd.isna(iqr) or iqr == 0:
        return df
    lo = q1 - k * iqr
    hi = q3 + k * iqr
    return df[(s >= lo) & (s <= hi)]


def compute_storage_timeseries(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    work = df.copy()
    work["wse"] = pd.to_numeric(work.get("wse"), errors="coerce")
    work["area_total"] = pd.to_numeric(work.get("area_total"), errors="coerce")

    if "quality_f" in work.columns:
        work["quality_f"] = pd.to_numeric(work["quality_f"], errors="coerce")
    else:
        work["quality_f"] = np.nan

    work["time_str"] = pd.to_datetime(work.get("time_str"), errors="coerce", utc=True)
    work = work.dropna(subset=["time_str", "wse", "area_total"]).copy()

    if work.empty:
        return pd.DataFrame()

    work_f = remove_outliers_iqr(work, "wse", k=1.5)
    work_f = remove_outliers_iqr(work_f, "area_total", k=1.5)

    curve_src = work_f.copy()
    q0 = curve_src[curve_src["quality_f"] == 0]
    if len(q0) >= 2:
        curve_src = q0

    ha = (
        curve_src.groupby("wse", as_index=False)["area_total"]
        .mean()
        .sort_values("wse")
    )

    if len(ha) < 2:
        return pd.DataFrame()

    h = ha["wse"].to_numpy(dtype=float)
    a = ha["area_total"].to_numpy(dtype=float) * 1_000_000.0

    cumv = np.zeros_like(h)
    total_v = 0.0

    for i in range(len(h) - 1):
        h1, h2 = h[i], h[i + 1]
        a1, a2 = a[i], a[i + 1]
        dh = h2 - h1

        if dh <= 0 or a1 <= 0 or a2 <= 0:
            cumv[i + 1] = total_v
            continue

        am = ((np.sqrt(a1) + np.sqrt(a2)) / 2.0) ** 2
        vi = (dh / 6.0) * (a1 + 4.0 * am + a2)

        total_v += vi
        cumv[i + 1] = total_v

    ts_df = work_f.sort_values("time_str").reset_index(drop=True).copy()
    wse_obs = ts_df["wse"].to_numpy(dtype=float)
    vol_m3 = np.interp(wse_obs, h, cumv, left=0.0, right=float(cumv.max()))

    ts_df["volume_m3"] = vol_m3
    ts_df["volume_MCM"] = ts_df["volume_m3"] / 1e6
    ts_df["volume_TMC"] = ts_df["volume_m3"] / 28_316_846.592
    return ts_df


def plot_volume_series(df: pd.DataFrame):
    if "time_str" not in df.columns or "volume_MCM" not in df.columns:
        st.info("Volume time series is not available.")
        return

    plot_df = df.dropna(subset=["time_str", "volume_MCM"]).copy()
    if plot_df.empty:
        st.info("No valid volume points found.")
        return

    fig = px.line(
        plot_df.sort_values("time_str"),
        x="time_str",
        y="volume_MCM",
        markers=True,
        title="Volume Time Series (MCM)",
    )
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, use_container_width=True)


def get_marker_lat_lon(geom):
    if geom is None or geom.is_empty:
        return None

    if geom.geom_type == "Point":
        return geom.y, geom.x

    centroid = geom.centroid
    if centroid is None or centroid.is_empty:
        return None

    return centroid.y, centroid.x


def update_query_params(lake_id: str | None, start_date, end_date) -> None:
    params = {}
    if lake_id:
        params["lake_id"] = str(lake_id)
    if start_date is not None:
        params["start_date"] = str(start_date)
    if end_date is not None:
        params["end_date"] = str(end_date)

    st.query_params.clear()
    for k, v in params.items():
        st.query_params[k] = v


def main() -> None:
    inject_css()

title_col, btn_col = st.columns([6, 2], gap="large")

with title_col:
    st.markdown(
        """
        <div class="main-title">SWOT Lakes Monitoring</div>
        <div class="main-subtitle">
        A satellite-based platform for lake volume estimation, change-ratio analysis, 
        and site-verified lake assessment using SWOT observations.
        </div>
        """,
        unsafe_allow_html=True,
    )

with btn_col:
    st.link_button("Change Ratio Analysis ↗", "/change-ratio-analysis", type="secondary")
    st.link_button("Site Verified Lakes ↗", "/site-verified-lakes", type="secondary")
    st.sidebar.title("India SWOT Lakes")
    st.sidebar.markdown("Choose lake by ID or click directly on the map.")

    if not LAKES_POINTS_PATH.exists():
        st.sidebar.error("Missing data/final_lakes_779.geojson")
        st.stop()

    lakes_gdf = load_geojson(str(LAKES_POINTS_PATH))

    if "lake_id" not in lakes_gdf.columns:
        st.error("`lake_id` column missing in final_lakes_779.geojson.")
        st.stop()

    lakes_gdf = lakes_gdf[~lakes_gdf.geometry.isna()].copy()
    lakes_gdf = lakes_gdf[~lakes_gdf.geometry.is_empty].copy()
    lakes_gdf = lakes_gdf.to_crs(4326)
    lakes_gdf["lake_id"] = lakes_gdf["lake_id"].astype(str)

    show_states = st.sidebar.checkbox("Show India states overlay", value=False)
    states_exists = STATES_PATH.exists()

    st.sidebar.markdown("---")
    max_points = st.sidebar.slider("Max lakes to display (performance)", 100, 800, 100, step=100)

    q = st.sidebar.text_input(
        "Search lake_id",
        value=st.session_state.get("search_lake_id", "")
    ).strip()

    filtered = lakes_gdf
    if q:
        filtered = filtered[filtered["lake_id"].str.contains(q, na=False)]
        st.session_state["search_lake_id"] = q

    if len(filtered) > max_points:
        display_gdf = filtered.sample(n=max_points, random_state=42)
    else:
        display_gdf = filtered

    st.sidebar.markdown("---")
    pick = st.sidebar.selectbox(
        "Or select lake_id",
        ["(click on map)"] + filtered["lake_id"].head(5000).tolist()
    )

    colL, colR = st.columns([1.05, 1.25], gap="large")

    with colL:
        st.subheader("🗺️ India Map (click a lake point)")
        st.caption(f"Showing {len(display_gdf):,} lake points inside the India bounding box.")

        m = folium.Map(location=[22.5, 79.0], zoom_start=5, tiles="CartoDB positron")

        if show_states and states_exists:
            try:
                states_gdf = load_geojson(str(STATES_PATH)).to_crs(4326)
                folium.GeoJson(
                    states_gdf.to_json(),
                    name="States",
                    style_function=lambda x: {"weight": 1, "fillOpacity": 0.03},
                ).add_to(m)
            except Exception as e:
                st.sidebar.warning(f"States overlay not loaded: {e}")

        cluster = MarkerCluster(
            name=f"Lakes (showing {len(display_gdf)} / {len(filtered)})"
        ).add_to(m)

        for _, r in display_gdf.iterrows():
            coords = get_marker_lat_lon(r.geometry)
            if coords is None:
                continue

            lat, lon = coords
            folium.Marker(
                location=[lat, lon],
                popup=f"Lake ID: {r['lake_id']}",
                tooltip=str(r["lake_id"]),
            ).add_to(cluster)

        folium.LayerControl().add_to(m)

        out = st_folium(m, height=640, width=None)

        clicked_popup = out.get("last_object_clicked_popup")
        clicked_id = extract_lake_id_from_popup(clicked_popup)

        selected_lake_id = None
        if pick != "(click on map)":
            selected_lake_id = pick
        elif clicked_id:
            selected_lake_id = clicked_id

        st.session_state["selected_lake_id"] = selected_lake_id

    with colR:
        st.subheader("📈Relative Volume Time Series Using SWOT data")

        lake_id = st.session_state.get("selected_lake_id")
        if not lake_id:
            st.markdown(
                '<div class="helper-box">Click a lake point on the map or choose a lake_id from the sidebar.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="metric-card">Selected Lake ID: {lake_id}</div>',
                unsafe_allow_html=True,
            )

            c1, c2 = st.columns(2)
            with c1:
                start_date = st.date_input(
                    "Start date",
                    value=pd.Timestamp("2023-01-01").date(),
                    format="YYYY/MM/DD",
                    key="main_start_date",
                )
            with c2:
                end_date = st.date_input(
                    "End date",
                    value=pd.Timestamp("2026-02-28").date(),
                    format="YYYY/MM/DD",
                    key="main_end_date",
                )

            update_query_params(lake_id, start_date, end_date)

            action_col1, action_col2 = st.columns([1, 1])
            with action_col1:
                if st.button("Fetch volume Data", type="primary"):
                    try:
                        df = fetch_lake_timeseries(
                            lake_id=lake_id,
                            start_time=start_date,
                            end_time=end_date,
                        )
                        st.session_state["last_df"] = df
                        st.session_state["last_storage_df"] = compute_storage_timeseries(df)
                        update_query_params(lake_id, start_date, end_date)
                    except Exception as exc:
                        st.error(f"Hydrocron request failed: {exc}")

            with action_col2:
                if st.button("Open Change Ratio Analysis"):
                    st.switch_page("change_ratio_page.py")

            df = st.session_state.get("last_df", pd.DataFrame())
            storage_df = st.session_state.get("last_storage_df", pd.DataFrame())

            if isinstance(storage_df, pd.DataFrame) and not storage_df.empty:
                plot_volume_series(storage_df)

            if isinstance(df, pd.DataFrame) and not df.empty:
                st.info("Open the 'Change Ratio Analysis' page for monthly mean, change-ratio, and dryness visuals.")

                with st.expander("Returned Hydrocron Table", expanded=False):
                    st.dataframe(df, use_container_width=True, height=280)

    st.markdown("---")
    st.caption(
        f"Filtered lakes available: {len(filtered):,}. "
        "Map uses your stable clustered India view; Hydrocron returns lake observations and volume is computed locally."
    )


if __name__ == "__main__":
    main()