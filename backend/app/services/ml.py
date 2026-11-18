"""ML risk predictor (advisory layer on top of the rules).

Design choice: the model can raise a green patient to yellow ("look at her
sooner") but can never create a red alert by itself and never lowers a zone.
Rules stay the safety net; ML adds early signal. This keeps the system
explainable and safe while the model is trained on non-local data.
"""
from __future__ import annotations

import logging
from functools import lru_cache

import numpy as np

from ..config import settings

log = logging.getLogger(__name__)
ENABLED = True  # seed script switches this off while replaying history (speed)


@lru_cache
def _bundle():
    if not settings.model_path.exists():
        log.warning("ML model not found at %s — run `python ml/train.py`", settings.model_path)
        return None
    import joblib

    return joblib.load(settings.model_path)


def model_info() -> dict | None:
    b = _bundle()
    return b["meta"] if b else None


def predict(features: dict) -> dict | None:
    """features: age, sbp, dbp, glucose, temp_c, heart_rate. Needs at least age + BP."""
    b = _bundle() if ENABLED else None
    if b is None:
        return None
    meta = b["meta"]
    if any(features.get(k) is None for k in ("age", "sbp", "dbp")):
        return None
    # The training data has no missing values: fill gaps with normal physiological values
    # and report which ones were imputed so the UI can show reduced confidence.
    defaults = {"glucose": 5.0, "temp_c": 36.7, "heart_rate": 76}
    imputed = [k for k in defaults if features.get(k) is None]
    row = [features.get(k) if features.get(k) is not None else defaults[k] for k in meta["features"]]
    proba = b["model"].predict_proba(np.array([row], dtype=float))[0]
    probs = {c: round(float(p), 3) for c, p in zip(meta["classes"], proba)}
    return {
        "probabilities": probs,
        "predicted": max(probs, key=probs.get),
        "high": probs.get("high", 0.0),
        "imputed": imputed,
        "model": meta["model_name"],
    }
