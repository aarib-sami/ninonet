"""
Local Day 5 API — live CNN forecast + click impacts.

Run (repo root):
  uvicorn cloud.impacts_api:app --reload --port 8000

Needed files:
  artifacts/enso_cnn_lead6_tuned.pt   — trained CNN
  data/pacific_anom.nc                — SST anomaly maps (CNN input)
  data/oni_monthly.csv                — ONI history (impacts regression)

Env overrides:
  ENSOCAST_MODEL_CKPT, ENSOCAST_ANOM_NC, ENSOCAST_ONI_CSV, ENSOCAST_FORECAST_JSON
"""

from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from enso.forecast_model import run_cnn_forecast  # noqa: E402
from enso.impacts_live import load_oni_by_winter, predict_impacts_for_point  # noqa: E402

DEFAULT_FORECAST = Path(
    os.environ.get("ENSOCAST_FORECAST_JSON", str(ROOT / "artifacts" / "forecast.json"))
)
DEFAULT_ONI = Path(
    os.environ.get("ENSOCAST_ONI_CSV", str(ROOT / "data" / "oni_monthly.csv"))
)

app = FastAPI(title="ENSOcast API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def _oni():
    path = DEFAULT_ONI
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Copy oni_monthly.csv from Drive into data/."
        )
    return load_oni_by_winter(str(path))


def _live_or_cached_forecast() -> dict:
    """Prefer live CNN; fall back to Day 4 forecast.json if anom/model missing."""
    try:
        return run_cnn_forecast()
    except FileNotFoundError:
        if DEFAULT_FORECAST.exists():
            data = json.loads(DEFAULT_FORECAST.read_text(encoding="utf-8"))
            data["source"] = "forecast_json_fallback"
            return data
        raise


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/forecast")
def forecast(live: bool = Query(True, description="Run the CNN (true) or read forecast.json")):
    try:
        if live:
            return _live_or_cached_forecast()
        if not DEFAULT_FORECAST.exists():
            raise FileNotFoundError(f"Missing {DEFAULT_FORECAST}")
        data = json.loads(DEFAULT_FORECAST.read_text(encoding="utf-8"))
        data["source"] = "forecast_json"
        return data
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Forecast failed: {e}") from e


@app.get("/impacts")
def impacts(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
):
    try:
        fc = _live_or_cached_forecast()
        oni = _oni()
        out = predict_impacts_for_point(
            lat=lat,
            lon=lon,
            forecast_oni=float(fc["forecast_oni"]),
            oni_by_winter=oni,
            winter_label=str(fc.get("winter", "2026-27")),
        )
        out["forecast_source"] = fc.get("source")
        return out
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Upstream/weather error: {e}") from e
