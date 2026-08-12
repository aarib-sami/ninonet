"""Run the trained ENSO CNN on the latest Pacific SST anomaly maps.

Input:  last WINDOW months from pacific_anom.nc  → shape (12, lat, lon)
Output: forecast_oni (scalar)

This is what Day 4 baked into forecast.json; the API can call it live instead.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_CKPT = Path(
    os.environ.get(
        "ENSOCAST_MODEL_CKPT",
        str(ROOT / "artifacts" / "enso_cnn_lead6_tuned.pt"),
    )
)
DEFAULT_ANOM = Path(
    os.environ.get(
        "ENSOCAST_ANOM_NC",
        str(ROOT / "data" / "pacific_anom.nc"),
    )
)
WINTER_LABEL = os.environ.get("ENSOCAST_WINTER", "2026-27")


class ENSOForecaster(nn.Module):
    def __init__(self, in_months: int = 12, dropout: float = 0.4, use_bn: bool = True):
        super().__init__()
        layers: list[nn.Module] = [nn.Conv2d(in_months, 32, 3, padding=1)]
        if use_bn:
            layers.append(nn.BatchNorm2d(32))
        layers += [nn.ReLU(), nn.MaxPool2d(2), nn.Conv2d(32, 64, 3, padding=1)]
        if use_bn:
            layers.append(nn.BatchNorm2d(64))
        layers += [
            nn.ReLU(),
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1),
        ]
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


def _load_anomaly_stack(anom_path: Path) -> tuple[np.ndarray, pd.Timestamp]:
    if not anom_path.exists():
        raise FileNotFoundError(
            f"Missing {anom_path}. Copy pacific_anom.nc from Drive "
            "(MyDrive/ensocast/data/) into data/ — this is the CNN input."
        )
    anom = xr.open_dataarray(anom_path)
    if isinstance(anom, xr.Dataset):
        anom = anom[list(anom.data_vars)[0]]
    arr = anom.values.astype("float32")
    times = pd.to_datetime(anom["time"].values).to_period("M").to_timestamp()
    return arr, times[-1]


def run_cnn_forecast(
    ckpt_path: Path | None = None,
    anom_path: Path | None = None,
    winter_label: str = WINTER_LABEL,
) -> dict[str, Any]:
    """Load checkpoint + latest 12 SST anomaly maps → ONI forecast."""
    ckpt_path = ckpt_path or DEFAULT_CKPT
    anom_path = anom_path or DEFAULT_ANOM

    if not ckpt_path.exists():
        raise FileNotFoundError(f"Missing model checkpoint: {ckpt_path}")

    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    state = ckpt["model_state"]
    window = int(ckpt.get("window", 12))
    lead = int(ckpt.get("lead", 6))
    hp = ckpt.get("hp") if isinstance(ckpt.get("hp"), dict) else {}
    dropout = float(hp.get("dropout", 0.4))
    use_bn = any("running_mean" in k for k in state)

    arr, last_month = _load_anomaly_stack(anom_path)
    if len(arr) < window:
        raise ValueError(f"Need at least {window} months in anomaly file, got {len(arr)}")

    x = arr[-window:].astype("float32")
    mu, sd = ckpt.get("norm_mu"), ckpt.get("norm_sd")
    if mu is not None and sd is not None:
        x = (x - float(mu)) / float(sd)

    model = ENSOForecaster(in_months=window, dropout=dropout, use_bn=use_bn)
    model.load_state_dict(state)
    model.eval()

    with torch.no_grad():
        forecast_oni = float(model(torch.from_numpy(x[None])).numpy().squeeze())

    return {
        "winter": winter_label,
        "forecast_oni": forecast_oni,
        "model_checkpoint": ckpt_path.name,
        "model_lead": lead,
        "input_end": str(pd.Timestamp(last_month).date()),
        "input_shape": list(x.shape),
        "source": "pytorch_live",
        "disclaimer": (
            "Live CNN ONI forecast from the latest Pacific SST anomaly maps. "
            "Map clicks still use Open-Meteo + historical ONI regression for local winters."
        ),
    }
