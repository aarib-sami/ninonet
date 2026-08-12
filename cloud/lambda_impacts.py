"""
AWS Lambda entry for click→impacts (Stretch / Day 6 wiring).

Expects env:
  FORECAST_JSON_S3  s3://bucket/key  OR local /tmp after download
  ONI_CSV_S3        s3://bucket/key

For local tests prefer cloud.impacts_api (FastAPI).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from enso.impacts_live import load_oni_by_winter, predict_impacts_for_point  # noqa: E402

_oni = None
_forecast = None


def _load_forecast():
    global _forecast
    if _forecast is not None:
        return _forecast
    path = os.environ.get("FORECAST_JSON", "/tmp/forecast.json")
    _forecast = json.loads(Path(path).read_text(encoding="utf-8"))
    return _forecast


def _load_oni():
    global _oni
    if _oni is not None:
        return _oni
    path = os.environ.get("ONI_CSV", "/tmp/oni_monthly.csv")
    _oni = load_oni_by_winter(path)
    return _oni


def handler(event, context):
    headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
    try:
        params = event.get("queryStringParameters") or {}
        if not params and event.get("rawQueryString"):
            params = {k: v[0] for k, v in parse_qs(event["rawQueryString"]).items()}

        path = event.get("rawPath") or event.get("path") or ""
        if path.endswith("/forecast") or params.get("resource") == "forecast":
            body = _load_forecast()
            return {"statusCode": 200, "headers": headers, "body": json.dumps(body)}

        lat = float(params["lat"])
        lon = float(params["lon"])
        fc = _load_forecast()
        result = predict_impacts_for_point(
            lat=lat,
            lon=lon,
            forecast_oni=float(fc["forecast_oni"]),
            oni_by_winter=_load_oni(),
            winter_label=str(fc.get("winter", "2026-27")),
        )
        return {"statusCode": 200, "headers": headers, "body": json.dumps(result)}
    except KeyError:
        return {
            "statusCode": 400,
            "headers": headers,
            "body": json.dumps({"error": "lat and lon query params required"}),
        }
    except Exception as e:  # noqa: BLE001
        return {
            "statusCode": 502,
            "headers": headers,
            "body": json.dumps({"error": str(e)}),
        }
