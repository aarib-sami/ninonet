"""
Local click→impacts API for Day 5.

Run (from repo root, with deps installed):
  uvicorn cloud.impacts_api:app --reload --port 8000

Env (optional):
  ENSOCAST_FORECAST_JSON  path to forecast.json from Day 4
  ENSOCAST_ONI_CSV        path to oni_monthly.csv from Day 1

Endpoints:
  GET /health
  GET /forecast
  GET /impacts?lat=43.65&lon=-79.38
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

from enso.impacts_live import load_oni_by_winter, predict_impacts_for_point  # noqa: E402

DEFAULT_FORECAST = Path(
    os.environ.get(
        "ENSOCAST_FORECAST_JSON",
        str(ROOT / "artifacts" / "forecast.json"),
    )
)
DEFAULT_ONI = Path(
    os.environ.get(
        "ENSOCAST_ONI_CSV",
        str(ROOT / "data" / "oni_monthly.csv"),
    )
)

app = FastAPI(title="ENSOcast impacts API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def _forecast() -> dict:
    path = DEFAULT_FORECAST
    if not path.exists():
        # Colab Drive layout fallback hints
        raise FileNotFoundError(
            f"Missing forecast.json at {path}. Run Day 4 first "
            "(or set ENSOCAST_FORECAST_JSON)."
        )
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _oni():
    path = DEFAULT_ONI
    if not path.exists():
        raise FileNotFoundError(
            f"Missing oni_monthly.csv at {path}. Run Day 1 first "
            "(or set ENSOCAST_ONI_CSV)."
        )
    return load_oni_by_winter(str(path))


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/forecast")
def forecast():
    try:
        return _forecast()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.get("/impacts")
def impacts(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
):
    try:
        fc = _forecast()
        oni = _oni()
        return predict_impacts_for_point(
            lat=lat,
            lon=lon,
            forecast_oni=float(fc["forecast_oni"]),
            oni_by_winter=oni,
            winter_label=str(fc.get("winter", "2026-27")),
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Upstream/weather error: {e}") from e
