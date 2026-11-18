"""Colour-zone rules engine.

Pure logic: takes a patient profile + observations, returns zone + reasons.
No database access, so it is easy to unit-test and to explain to clinicians.

Zone = worst of:
  * each vital/lab parameter (latest fresh value vs. bands)
  * reported danger-sign symptoms (last `symptom_window_hours`)
  * dangerous combinations (e.g. high BP + proteinuria = preeclampsia)
  * worsening trends (e.g. BP rising 15 mmHg in 3 weeks)
  * background risk-factor floors (e.g. twins -> at least yellow)
  * aggregation (MEOWS-style: N yellow findings -> red)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import yaml

ZONES = ("green", "yellow", "red")
ZONE_RANK = {z: i for i, z in enumerate(ZONES)}
PARAMS = ("sbp", "dbp", "heart_rate", "resp_rate", "temperature", "spo2",
          "glucose", "hemoglobin", "proteinuria", "weight")
SYMPTOM_WINDOW_HOURS = 72
SOURCE_LABELS = {"self": "o'zi kiritgan", "clinic": "klinika", "lab": "laboratoriya", "device": "qurilma"}


def worst(*zones: str) -> str:
    return max(zones, key=lambda z: ZONE_RANK[z]) if zones else "green"


@dataclass
class Finding:
    code: str
    category: str  # parameter | symptom | combo | trend | risk_factor | aggregation | ml
    zone: str
    label: str
    value: Any = None
    source: str | None = None
    observed_at: str | None = None

    @property
    def self_reported(self) -> bool:
        return self.source == "self"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["self_reported"] = self.self_reported
        return d


@dataclass
class EvalResult:
    zone: str
    findings: list[Finding] = field(default_factory=list)
    latest: dict[str, dict] = field(default_factory=dict)
    active_symptoms: list[str] = field(default_factory=list)

    @property
    def red_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.zone == "red"]


def _match(value: float, cond: dict) -> bool:
    ops = {"lt": value.__lt__, "lte": value.__le__, "gt": value.__gt__, "gte": value.__ge__}
    return all(ops[k](float(v)) for k, v in cond.items() if k in ops)


def _get(obj: Any, name: str) -> Any:
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


class RuleSet:
    def __init__(self, spec: dict):
        self.spec = spec
        self.kind = spec["kind"]
        self.parameters: dict = spec.get("parameters", {})
        self.symptoms: dict = spec.get("symptoms", {})
        self.combos: list = spec.get("combos", [])
        self.risk_factors: dict = spec.get("risk_factors", {})
        self.trends: dict = spec.get("trends", {})
        self.checkin_days: dict = spec.get("checkin_days", {})
        self.red_if_yellow = spec.get("aggregation", {}).get("red_if_yellow_count_gte")

    @classmethod
    def load(cls, path: Path) -> RuleSet:
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")))

    # ---------- helpers ----------
    def format_value(self, param: str, value: Any) -> str:
        p = self.parameters.get(param, {})
        labels = p.get("value_labels")
        if labels and value is not None and int(value) in labels:
            return str(labels[int(value)])
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return f"{value} {p.get('unit', '')}".strip()

    def auto_risk_factors(self, profile: dict) -> list[str]:
        out: list[str] = []
        if self.kind == "mother":
            age = profile.get("age_years")
            if age is not None and age < 18:
                out.append("age_under_18")
            if age is not None and age > 35:
                out.append("age_over_35")
        else:
            bw, ga, apgar = profile.get("birth_weight_g"), profile.get("gestational_age_at_birth"), profile.get("apgar5")
            if bw is not None:
                if bw < 1500:
                    out.append("very_low_birth_weight")
                elif bw < 2500:
                    out.append("low_birth_weight")
            if ga is not None:
                if ga < 32:
                    out.append("very_preterm")
                elif ga < 37:
                    out.append("preterm")
            if apgar is not None and apgar < 7:
                out.append("low_apgar")
        return out

    def latest_values(self, observations: list, now: datetime) -> dict[str, dict]:
        latest: dict[str, dict] = {}
        for obs in sorted(observations, key=lambda o: _get(o, "recorded_at"), reverse=True):
            at = _get(obs, "recorded_at")
            for param in PARAMS:
                if param in latest:
                    continue
                value = _get(obs, param)
                if value is None:
                    continue
                fresh = self.parameters.get(param, {}).get("freshness_days", 30)
                if now - at <= timedelta(days=fresh):
                    latest[param] = {"value": value, "source": _get(obs, "source"), "at": at}
        return latest

    def active_symptoms(self, observations: list, now: datetime) -> dict[str, dict]:
        active: dict[str, dict] = {}
        for obs in sorted(observations, key=lambda o: _get(o, "recorded_at"), reverse=True):
            at = _get(obs, "recorded_at")
            if now - at > timedelta(hours=SYMPTOM_WINDOW_HOURS):
                break
            for s in _get(obs, "symptoms") or []:
                if s in self.symptoms and s not in active:
                    active[s] = {"source": _get(obs, "source"), "at": at}
        return active

    # ---------- main ----------
    def evaluate(self, profile: dict, observations: Iterable, now: datetime) -> EvalResult:
        observations = [o for o in observations if _get(o, "recorded_at") <= now]
        findings: list[Finding] = []
        latest = self.latest_values(observations, now)
        symptoms = self.active_symptoms(observations, now)

        # 1. Parameters
        for param, info in latest.items():
            spec = self.parameters.get(param)
            if not spec:
                continue
            for band in spec.get("bands", []):
                if _match(float(info["value"]), band):
                    findings.append(Finding(
                        code=f"param:{param}", category="parameter", zone=band["zone"],
                        label=f"{spec['label']}: {self.format_value(param, info['value'])} — {band.get('text', '')}".rstrip(" —"),
                        value=info["value"], source=info["source"], observed_at=info["at"].isoformat(),
                    ))
                    break

        # 2. Symptoms
        for code, info in symptoms.items():
            spec = self.symptoms[code]
            findings.append(Finding(
                code=f"symptom:{code}", category="symptom", zone=spec["zone"], label=spec["label"],
                source=info["source"], observed_at=info["at"].isoformat(),
            ))

        # 3. Combinations
        for combo in self.combos:
            ok = all(
                c["param"] in latest and _match(float(latest[c["param"]]["value"]), c)
                for c in combo.get("params", [])
            )
            if ok and combo.get("any_symptom"):
                ok = any(s in symptoms for s in combo["any_symptom"])
            if ok:
                srcs = {latest[c["param"]]["source"] for c in combo.get("params", [])}
                # Only "self" if every value behind the combo was self-reported.
                verified = sorted(srcs - {"self"})
                findings.append(Finding(
                    code=f"combo:{combo['code']}", category="combo", zone=combo["zone"], label=combo["label"],
                    source=verified[0] if verified else ("self" if srcs else None),
                ))

        # 4. Trends
        for code, t in self.trends.items():
            pts = sorted(
                ((_get(o, "recorded_at"), _get(o, t["param"])) for o in observations
                 if _get(o, t["param"]) is not None and now - _get(o, "recorded_at") <= timedelta(days=t["window_days"])),
                key=lambda p: p[0],
            )
            if len(pts) < t.get("min_points", 2):
                continue
            # Robust to single noisy (e.g. home) readings: compare the mean of the most
            # recent third of points with the mean of the earliest third.
            vals = [v for _, v in pts]
            k = max(1, len(vals) // 3)
            baseline, recent = sum(vals[:k]) / k, sum(vals[-k:]) / k
            change = recent - baseline if t["direction"] == "up" else baseline - recent
            if change >= t["delta"]:
                unit = self.parameters.get(t["param"], {}).get("unit", "")
                sign = "+" if t["direction"] == "up" else "−"
                findings.append(Finding(
                    code=f"trend:{code}", category="trend", zone=t["zone"],
                    label=f"{t['label']} ({sign}{round(change, 1)} {unit}, {t['window_days']} kun ichida)".replace("  ", " "),
                    value=round(change, 2),
                ))

        zone = worst(*(f.zone for f in findings)) if findings else "green"

        # 5. Aggregation (MEOWS-style)
        yellow_count = sum(1 for f in findings if f.zone == "yellow")
        if self.red_if_yellow and zone == "yellow" and yellow_count >= self.red_if_yellow:
            findings.append(Finding(
                code="aggregation:yellow_count", category="aggregation", zone="red",
                label=f"{yellow_count} ta sariq ko'rsatkich bir vaqtda — eskalatsiya",
            ))
            zone = "red"

        # 6. Background risk factors (floor)
        factors = list(dict.fromkeys(list(profile.get("risk_factors") or []) + self.auto_risk_factors(profile)))
        for rf in factors:
            spec = self.risk_factors.get(rf)
            if not spec:
                continue
            floor = spec.get("zone_floor", "green")
            findings.append(Finding(code=f"risk:{rf}", category="risk_factor", zone=floor, label=spec["label"]))
            zone = worst(zone, floor)

        order = {"red": 0, "yellow": 1, "green": 2}
        findings.sort(key=lambda f: (order[f.zone], f.category == "risk_factor"))
        return EvalResult(zone=zone, findings=findings, latest=latest, active_symptoms=list(symptoms))

    def evaluate_single(self, observation: Any, now: datetime) -> list[Finding]:
        """Red findings produced by one observation alone (used to detect new danger signs)."""
        res = self.evaluate({"risk_factors": []}, [observation], now)
        return [f for f in res.findings if f.zone == "red"]


@lru_cache
def get_rules(kind: str) -> RuleSet:
    from ..config import settings

    name = "maternal.yaml" if kind == "mother" else "newborn.yaml"
    return RuleSet.load(settings.rules_dir / name)
