from __future__ import annotations

from . import models
from .rules.engine import PARAMS
from .services.assessment import age_years, gestational_weeks
from .timeutil import utcnow


def iso(dt):
    return dt.isoformat() if dt else None


def _premium(p: models.Patient) -> bool:
    from sqlalchemy.orm import object_session

    from .services.subscriptions import is_premium
    db = object_session(p)
    acc = p.mother_id if p.kind == "newborn" and p.mother_id else p.id
    return bool(db and is_premium(db, acc))


DELIVERY_OUTCOMES = {"normal_delivery", "cesarean", "preterm_birth"}


def postpartum_days(p: models.Patient) -> int | None:
    if p.kind == "mother" and p.outcome in DELIVERY_OUTCOMES and p.outcome_date:
        return (utcnow().date() - p.outcome_date).days
    return None


GLUCOSE_FACTORS = {"diabetes", "gestational_diabetes", "maternal_diabetes"}


def self_report_features(p: models.Patient) -> dict:
    """Which self-report inputs make clinical sense for this patient (bot menu + mother page)."""
    if p.kind == "newborn":
        return {"bp": False, "glucose": False, "fetal_movements": False, "meds": False,
                "temperature": True, "weight": True}
    ga = gestational_weeks(p, utcnow().date())
    return {
        "bp": True, "temperature": True, "weight": True, "meds": True,
        # Glucose only for women with (gestational) diabetes — others have no glucometer and no indication.
        "glucose": bool(GLUCOSE_FACTORS & set(p.risk_factors or [])),
        # Kick counting is meaningful from 28 weeks (unknown GA -> show) and not after delivery.
        "fetal_movements": postpartum_days(p) is None and (ga is None or ga >= 28),
    }


def patient_summary(p: models.Patient) -> dict:
    today = utcnow().date()
    top = [r for r in (p.zone_reasons or []) if r["category"] != "risk_factor"][:3] or (p.zone_reasons or [])[:2]
    return {
        "id": p.id,
        "kind": p.kind,
        "full_name": p.full_name,
        "age": age_years(p.birth_date, today),
        "age_days": (today - p.birth_date).days if p.kind == "newborn" and p.birth_date else None,
        "gestational_weeks": gestational_weeks(p, today) if postpartum_days(p) is None else None,
        "postpartum_days": postpartum_days(p),
        "mother_id": p.mother_id,
        "phone": p.phone,
        "district_id": p.district_id,
        "district": p.district.name if p.district else None,
        "doctor_id": p.doctor_id,
        "doctor": p.doctor.full_name if p.doctor else None,
        "lat": p.lat,
        "lon": p.lon,
        "zone": p.zone,
        "top_reasons": [r["label"] for r in top],
        "ml_high": (p.ml_risk or {}).get("high"),
        "last_observation_at": iso(p.last_observation_at),
        "zone_updated_at": iso(p.zone_updated_at),
        "telegram_linked": bool(p.telegram_chat_id),
        "premium": _premium(p),
        "self_report": self_report_features(p),
        "active": p.active,
    }


def observation_dict(o: models.Observation) -> dict:
    d = {k: getattr(o, k) for k in PARAMS}
    d.update(id=o.id, recorded_at=iso(o.recorded_at), source=o.source, entered_by=o.entered_by, meds_taken=o.meds_taken,
             symptoms=o.symptoms or [], note=o.note)
    return d


def alert_dict(a: models.Alert, with_events: bool = False) -> dict:
    d = {
        "id": a.id, "patient_id": a.patient_id, "patient_name": a.patient.full_name if a.patient else None,
        "patient_kind": a.patient.kind if a.patient else None,
        "district": a.patient.district.name if a.patient and a.patient.district else None,
        "kind": a.kind, "zone": a.zone, "title": a.title, "message": a.message, "level": a.level,
        "status": a.status, "created_at": iso(a.created_at), "acknowledged_by": a.acknowledged_by,
        "acknowledged_at": iso(a.acknowledged_at), "resolved_at": iso(a.resolved_at),
        "next_escalation_at": iso(a.next_escalation_at),
    }
    if with_events:
        d["events"] = [{"at": iso(e.at), "type": e.type, "actor": e.actor, "detail": e.detail} for e in a.events]
    return d
