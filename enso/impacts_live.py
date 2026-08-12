"""Live ONI → local winter impacts (Open-Meteo on demand).

Used by the Day 5 click API: for a lat/lon, fetch history, fit vs DJF ONI,
return anomalies for the forecasted winter ONI.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd
import requests

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DEFAULT_START = "1960-01-01"
DEFAULT_END = "2025-12-31"


def load_oni_by_winter(oni_csv_path: str) -> pd.Series:
    """DJF ONI indexed by winter year (January-centered)."""
    oni_df = pd.read_csv(oni_csv_path, parse_dates=["time"])
    oni_df["month"] = oni_df["time"].dt.month
    oni_df["year"] = oni_df["time"].dt.year
    return (
        oni_df.loc[oni_df["month"] == 1]
        .set_index("year")["oni"]
        .astype(float)
        .sort_index()
    )


def fetch_daily(
    lat: float,
    lon: float,
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
    retries: int = 5,
) -> dict[str, Any]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "daily": "temperature_2m_mean,precipitation_sum,snowfall_sum",
        "timezone": "auto",
    }
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(ARCHIVE_URL, params=params, timeout=120)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(30 * (attempt + 1))
                last_err = RuntimeError("HTTP 429 from Open-Meteo")
                continue
            last_err = RuntimeError(f"HTTP {r.status_code}")
        except Exception as e:  # noqa: BLE001
            last_err = e
        time.sleep(2 * (attempt + 1))
    raise last_err or RuntimeError("Open-Meteo fetch failed")


def daily_to_winters(payload: dict[str, Any]) -> pd.DataFrame:
    """Winter year Y = Dec(Y-1) + Jan Y + Feb Y."""
    daily = payload["daily"]
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(daily["time"]),
            "tmean": daily["temperature_2m_mean"],
            "precip": daily["precipitation_sum"],
            "snow": daily["snowfall_sum"],
        }
    )
    df["month"] = df["date"].dt.month
    df["year"] = df["date"].dt.year
    df["winter_year"] = np.where(df["month"] == 12, df["year"] + 1, df["year"])
    winter = df[df["month"].isin([12, 1, 2])]
    g = winter.groupby("winter_year").agg(
        tmean=("tmean", "mean"),
        precip=("precip", "sum"),
        snow=("snow", "sum"),
        n_days=("tmean", "count"),
    )
    return g[g["n_days"] >= 85]


def phrase(var: str, anom: float) -> str:
    if var == "temp":
        if anom > 0.3:
            return "warmer than usual"
        if anom < -0.3:
            return "colder than usual"
        return "near-normal temperatures"
    if var == "precip":
        if anom > 10:
            return "wetter than usual"
        if anom < -10:
            return "drier than usual"
        return "near-normal precipitation"
    if anom > 5:
        return "snowier than usual"
    if anom < -5:
        return "less snow than usual"
    return "near-normal snowfall"


def confidence_tag(score: float) -> str:
    if score >= 0.7:
        return "strong"
    if score >= 0.55:
        return "moderate"
    return "mixed"


def fit_and_predict(
    winters: pd.DataFrame,
    oni_by_winter: pd.Series,
    forecast_oni: float,
) -> dict[str, Any] | None:
    common = winters.join(oni_by_winter.rename("oni"), how="inner").dropna()
    if len(common) < 20:
        return None

    confidences: list[float] = []
    out: dict[str, Any] = {"n_winters": int(len(common))}
    for var, key in [("temp", "tmean"), ("precip", "precip"), ("snow", "snow")]:
        clim = float(common[key].mean())
        anom = common[key] - clim
        b, a = np.polyfit(common["oni"].to_numpy(), anom.to_numpy(), 1)
        pred = float(a + b * forecast_oni)
        enso = common[common["oni"] >= 0.5]
        if len(enso) >= 5 and abs(pred) > 1e-6:
            conf = float((np.sign(enso[key] - clim) == np.sign(pred)).mean())
        else:
            conf = 0.5
        confidences.append(conf)
        out[f"{var}_anom"] = pred
        out[f"{var}_phrase"] = phrase(var, pred)
        out[f"{var}_slope"] = float(b)

    out["confidence"] = float(np.mean(confidences))
    out["confidence_tag"] = confidence_tag(out["confidence"])
    return out


def predict_impacts_for_point(
    lat: float,
    lon: float,
    forecast_oni: float,
    oni_by_winter: pd.Series,
    winter_label: str = "2026-27",
) -> dict[str, Any]:
    """Full click path: Open-Meteo → winters → ONI regression → forecast anomalies."""
    winters = daily_to_winters(fetch_daily(lat, lon))
    fitted = fit_and_predict(winters, oni_by_winter, forecast_oni)
    if fitted is None:
        raise ValueError("Not enough overlapping winters at this location")
    return {
        "lat": float(lat),
        "lon": float(lon),
        "winter": winter_label,
        "forecast_oni": float(forecast_oni),
        **fitted,
        "source": "live_open_meteo",
    }
