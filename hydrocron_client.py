from __future__ import annotations

import io
from datetime import date, datetime

import pandas as pd
import requests

HYDROCRON_URL = "https://soto.podaac.earthdatacloud.nasa.gov/hydrocron/v1/timeseries"


def _date_to_iso_start(d: date) -> str:
    return f"{d.isoformat()}T00:00:00Z"


def _date_to_iso_end(d: date) -> str:
    return f"{d.isoformat()}T23:59:59Z"


def clean_timeseries_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    if "time_str" in out.columns:
        out["time_str"] = pd.to_datetime(out["time_str"], errors="coerce", utc=True)
        out = out.sort_values("time_str")

    numeric_cols = ["wse", "area_total", "area_detct", "quality_f"]
    for col in numeric_cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    return out.reset_index(drop=True)


def fetch_lake_timeseries(
    lake_id: str,
    start_time: str | date,
    end_time: str | date,
    timeout: int = 90,
) -> pd.DataFrame:
    if isinstance(start_time, date) and not isinstance(start_time, datetime):
        start_time = _date_to_iso_start(start_time)
    if isinstance(end_time, date) and not isinstance(end_time, datetime):
        end_time = _date_to_iso_end(end_time)

    fields = [
        "lake_id",
        "time_str",
        "wse",
        "area_total",
        "quality_f",
        "collection_shortname",
        "crid",
        "PLD_version",
        "range_start_time",
    ]

    params = {
        "feature": "PriorLake",
        "feature_id": str(lake_id).strip(),
        "start_time": str(start_time),
        "end_time": str(end_time),
        "fields": ",".join(fields),
        "output": "csv",
    }

    response = requests.get(HYDROCRON_URL, params=params, timeout=timeout)
    response.raise_for_status()

    try:
        payload = response.json()
        csv_text = payload.get("results", {}).get("csv", "")
        if csv_text and csv_text.strip():
            return clean_timeseries_df(pd.read_csv(io.StringIO(csv_text)))
    except Exception:
        pass

    text = response.text.strip()
    if not text:
        return pd.DataFrame()

    return clean_timeseries_df(pd.read_csv(io.StringIO(text)))