"""Train the baseline maternal risk model.

Dataset: UCI "Maternal Health Risk" (Ahmed & Kashem, 2020), 1014 rows from
rural clinics in Bangladesh. Columns: Age, SystolicBP, DiastolicBP, BS
(blood glucose, mmol/L), BodyTemp (F), HeartRate, RiskLevel (low/mid/high).

IMPORTANT: the raw file contains many exact duplicate rows. If you split
before de-duplicating, the same row lands in train and test and accuracy is
inflated (~85-90%). We evaluate on de-duplicated data with stratified CV to get
an honest number, then fit the final model on all unique rows.

This model is a *baseline / demo*. It is advisory only and must be retrained
on local Uzbek data (exported from the registry via /api/export/ml-dataset.csv)
before any real use.

Usage:  python ml/train.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score, recall_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw" / "Maternal Health Risk Data Set.csv"
OUT_DIR = ROOT / "models"

FEATURES = ["age", "sbp", "dbp", "glucose", "temp_c", "heart_rate"]
LABELS = {"low risk": "low", "mid risk": "mid", "high risk": "high"}
CLASS_ORDER = ["low", "mid", "high"]


def load() -> pd.DataFrame:
    df = pd.read_csv(RAW, encoding="utf-8-sig")
    df = df.rename(
        columns={
            "Age": "age",
            "SystolicBP": "sbp",
            "DiastolicBP": "dbp",
            "BS": "glucose",
            "BodyTemp": "temp_f",
            "HeartRate": "heart_rate",
            "RiskLevel": "risk",
        }
    )
    df["temp_c"] = ((df["temp_f"] - 32) * 5 / 9).round(1)
    df["risk"] = df["risk"].map(LABELS)
    # Obvious data-entry error in the source (heart rate 7 bpm)
    df = df[df["heart_rate"] >= 30]
    return df


def candidates():
    return {
        "logreg": make_pipeline(
            StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced")
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=400, min_samples_leaf=2, class_weight="balanced", random_state=42
        ),
        "hist_gb": HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.05, class_weight="balanced", random_state=42
        ),
    }


def main() -> None:
    df = load()
    n_raw = len(df)
    uniq = df.drop_duplicates(subset=FEATURES + ["risk"]).reset_index(drop=True)
    X, y = uniq[FEATURES].to_numpy(dtype=float), uniq["risk"].to_numpy()
    print(f"rows: {n_raw} raw, {len(uniq)} unique  | class balance: "
          f"{uniq['risk'].value_counts().to_dict()}")

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    results = {}
    for name, model in candidates().items():
        pred = cross_val_predict(model, X, y, cv=cv)
        results[name] = {
            "macro_f1": round(float(f1_score(y, pred, average="macro")), 3),
            "high_risk_recall": round(
                float(recall_score(y, pred, labels=["high"], average="macro")), 3
            ),
            "report": classification_report(y, pred, output_dict=True, zero_division=0),
        }
        print(f"{name:14s} macroF1={results[name]['macro_f1']}  "
              f"high-risk recall={results[name]['high_risk_recall']}")

    # Choose by high-risk recall first (missing a high-risk woman is the costly error),
    # then macro F1.
    best = max(results, key=lambda k: (results[k]["high_risk_recall"], results[k]["macro_f1"]))
    model = candidates()[best].fit(X, y)
    print(f"selected: {best}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "model_name": best,
        "features": FEATURES,
        "classes": [str(c) for c in model.classes_],
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": {
            "name": "UCI Maternal Health Risk (Bangladesh)",
            "url": "https://archive.ics.uci.edu/dataset/863/maternal+health+risk",
            "rows_raw": n_raw,
            "rows_unique": int(len(uniq)),
        },
        "cv": {k: {kk: vv for kk, vv in v.items() if kk != "report"} for k, v in results.items()},
        "cv_report_selected": results[best]["report"],
        "notes": (
            "Evaluated with 5-fold stratified CV on de-duplicated rows. Advisory only; "
            "not clinically validated; retrain on local registry data."
        ),
    }
    joblib.dump({"model": model, "meta": meta}, OUT_DIR / "maternal_risk.joblib")
    (OUT_DIR / "metrics.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"saved -> {OUT_DIR / 'maternal_risk.joblib'}")


if __name__ == "__main__":
    np.random.seed(42)
    main()
