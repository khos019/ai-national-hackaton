from __future__ import annotations

from . import models
from .rules.engine import PARAMS
from .services.assessment import age_years, gestational_weeks
from .timeutil import utcnow


def iso(dt):
    return dt.isoformat() if dt else None


def patient_summary(p: models.Patient) -> dict:
    today = utcnow().date()
    top = [r for r in (p.zone_reasons or []) if r["category"] != "risk_factor"][:3] or (p.zone_reasons or [])[:2]
    return {
        "id": p.id,
        "kind": p.kind,
        "full_name": p.full_name,
        "age": age_years(p.birth_date, today),
        "age_days": (today - p.birth_date).days if p.kind == "newborn" and p.birth_date else None,
        "gestational_weeks": gestational_weeks(p, today),
        "phone": p.phone,
        "district_id": p.district_id,
        "district": p.district.name if p.district else None,
        "lat": p.lat,
        "lon": p.lon,
        "zone": p.zone,
        "top_reasons": [r["label"] for r in top],
        "ml_high": (p.ml_risk or {}).get("high"),
        "last_observation_at": iso(p.last_observation_at),
        "zone_updated_at": iso(p.zone_updated_at),
        "telegram_linked": bool(p.telegram_chat_id),
        "active": p.active,
    }


def observation_dict(o: models.Observation) -> dict:
    d = {k: getattr(o, k) for k in PARAMS}
    d.update(id=o.id, recorded_at=iso(o.recorded_at), source=o.source, entered_by=o.entered_by,
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
