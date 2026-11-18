from __future__ import annotations

import csv
import io
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..db import get_db
from ..rules.engine import PARAMS, get_rules
from ..serializers import alert_dict, iso, observation_dict, patient_summary
from ..services import alerts as alert_svc
from ..services import ml, notify
from ..services.assessment import age_years, gestational_weeks, reassess
from ..services.intake import add_observation, advice_for, find_patient_by_phone
from ..timeutil import utcnow

router = APIRouter(prefix="/api")


def _patient(db: Session, pid: int) -> models.Patient:
    p = db.get(models.Patient, pid)
    if not p:
        raise HTTPException(404, "Bemor topilmadi")
    return p


def _alert(db: Session, aid: int) -> models.Alert:
    a = db.get(models.Alert, aid)
    if not a:
        raise HTTPException(404, "Xabarnoma topilmadi")
    return a


# ---------------- reference data ----------------
@router.get("/meta")
def meta(db: Session = Depends(get_db)):
    def catalog(kind):
        r = get_rules(kind)
        return {
            "parameters": {k: {"label": v["label"], "unit": v.get("unit", ""), "value_labels": v.get("value_labels")}
                           for k, v in r.parameters.items()},
            "symptoms": {k: {"label": v["label"], "zone": v["zone"]} for k, v in r.symptoms.items()},
            "risk_factors": {k: {"label": v["label"], "zone_floor": v.get("zone_floor", "green"),
                                 "auto": v.get("auto", False)} for k, v in r.risk_factors.items()},
        }

    districts = db.scalars(select(models.District).order_by(models.District.name)).all()
    return {
        "districts": [{"id": d.id, "name": d.name, "region": d.region, "lat": d.lat, "lon": d.lon} for d in districts],
        "mother": catalog("mother"),
        "newborn": catalog("newborn"),
        "actions": alert_svc.ACTIONS,
        "telegram_enabled": notify.telegram_enabled(),
        "escalation_seconds": settings.escalation_seconds,
        "model": ml.model_info(),
    }


@router.get("/rules/{kind}")
def rules(kind: str):
    if kind not in ("mother", "newborn"):
        raise HTTPException(404)
    return get_rules(kind).spec


# ---------------- dashboard ----------------
@router.get("/dashboard")
def dashboard(district_id: int | None = None, db: Session = Depends(get_db)):
    pq = select(models.Patient.kind, models.Patient.zone, func.count()).where(models.Patient.active.is_(True))
    if district_id:
        pq = pq.where(models.Patient.district_id == district_id)
    counts = {"mother": {"green": 0, "yellow": 0, "red": 0}, "newborn": {"green": 0, "yellow": 0, "red": 0}}
    for kind, zone, n in db.execute(pq.group_by(models.Patient.kind, models.Patient.zone)):
        counts[kind][zone] = n

    aq = select(models.Alert).join(models.Patient)
    if district_id:
        aq = aq.where(models.Patient.district_id == district_id)
    alerts = db.scalars(aq).all()
    open_alerts = [a for a in alerts if a.status == "open"]
    acked = [a for a in alerts if a.acknowledged_at]
    mean_ack = (sum((a.acknowledged_at - a.created_at).total_seconds() for a in acked) / len(acked)) if acked else None

    by_district = []
    dq = select(models.District.id, models.District.name, models.Patient.zone, func.count()).join(
        models.Patient, models.Patient.district_id == models.District.id).where(models.Patient.active.is_(True))
    rows: dict[int, dict] = {}
    for did, name, zone, n in db.execute(dq.group_by(models.District.id, models.Patient.zone)):
        rows.setdefault(did, {"id": did, "name": name, "green": 0, "yellow": 0, "red": 0})[zone] = n
    by_district = sorted(rows.values(), key=lambda r: (-r["red"], -r["yellow"]))

    return {
        "counts": counts,
        "open_alerts": len(open_alerts),
        "open_red_alerts": sum(1 for a in open_alerts if a.zone == "red"),
        "escalated_alerts": sum(1 for a in alerts if a.level > 0 and a.status != "resolved"),
        "mean_ack_seconds": round(mean_ack) if mean_ack is not None else None,
        "by_district": by_district,
        "now": iso(utcnow()),
    }


# ---------------- patients ----------------
@router.get("/patients")
def list_patients(
    zone: str | None = None, kind: str | None = None, district_id: int | None = None,
    q: str | None = None, limit: int = Query(500, le=2000), db: Session = Depends(get_db),
):
    stmt = select(models.Patient).where(models.Patient.active.is_(True))
    if zone:
        stmt = stmt.where(models.Patient.zone == zone)
    if kind:
        stmt = stmt.where(models.Patient.kind == kind)
    if district_id:
        stmt = stmt.where(models.Patient.district_id == district_id)
    if q:
        stmt = stmt.where(models.Patient.full_name.ilike(f"%{q}%") | models.Patient.phone.ilike(f"%{q}%"))
    patients = db.scalars(stmt).all()
    rank = {"red": 0, "yellow": 1, "green": 2}
    patients = sorted(patients, key=lambda p: (rank[p.zone], -(p.zone_updated_at.timestamp() if p.zone_updated_at else 0)))
    return [patient_summary(p) for p in patients[:limit]]


@router.post("/patients", status_code=201)
def create_patient(body: schemas.PatientIn, db: Session = Depends(get_db)):
    if not db.get(models.District, body.district_id):
        raise HTTPException(400, "Tuman topilmadi")
    p = models.Patient(**body.model_dump())
    db.add(p)
    db.flush()
    reassess(db, p, notify=False)
    db.commit()
    return patient_summary(p)


@router.get("/patients/{pid}")
def get_patient(pid: int, db: Session = Depends(get_db)):
    p = _patient(db, pid)
    today = utcnow().date()
    assessments = db.scalars(select(models.Assessment).where(models.Assessment.patient_id == pid)
                             .order_by(models.Assessment.created_at.desc()).limit(30)).all()
    alerts = db.scalars(select(models.Alert).where(models.Alert.patient_id == pid)
                        .order_by(models.Alert.created_at.desc())).all()
    data = patient_summary(p)
    data.update(
        birth_date=iso(p.birth_date), address=p.address, lmp_date=iso(p.lmp_date), parity=p.parity,
        edd=iso(p.lmp_date + timedelta(days=280)) if p.lmp_date else None,
        mother_id=p.mother_id, birth_weight_g=p.birth_weight_g,
        gestational_age_at_birth=p.gestational_age_at_birth, apgar5=p.apgar5,
        risk_factors=p.risk_factors or [], outcome=p.outcome, outcome_date=iso(p.outcome_date),
        reasons=p.zone_reasons or [], ml=p.ml_risk,
        observations=[observation_dict(o) for o in reversed(p.observations)],
        zone_history=[{"at": iso(a.created_at), "zone": a.zone} for a in reversed(assessments)],
        alerts=[alert_dict(a, with_events=True) for a in alerts],
        age=age_years(p.birth_date, today), gestational_weeks=gestational_weeks(p, today),
    )
    return data


@router.patch("/patients/{pid}")
def patch_patient(pid: int, body: schemas.PatientPatch, db: Session = Depends(get_db)):
    p = _patient(db, pid)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    if body.risk_factors is not None:
        reassess(db, p)
    db.commit()
    return patient_summary(p)


@router.post("/patients/{pid}/observations", status_code=201)
def create_observation(pid: int, body: schemas.ObservationIn, db: Session = Depends(get_db)):
    p = _patient(db, pid)
    data = body.model_dump()
    obs, assessment = add_observation(db, p, data, source=body.source, entered_by=body.entered_by,
                                      recorded_at=body.recorded_at)
    db.commit()
    return {"observation": observation_dict(obs), "zone": assessment.zone, "prev_zone": assessment.prev_zone,
            "reasons": assessment.reasons, "ml": assessment.ml}


# ---------------- self-report (the woman herself) ----------------
@router.post("/self-report", status_code=201)
def self_report(body: schemas.SelfReportIn, db: Session = Depends(get_db)):
    p = db.get(models.Patient, body.patient_id) if body.patient_id else None
    if not p and body.phone:
        p = find_patient_by_phone(db, body.phone)
    if not p:
        raise HTTPException(404, "Ro'yxatda topilmadingiz. Oilaviy poliklinikangizga murojaat qiling.")
    data = body.model_dump(exclude={"patient_id", "phone"})
    obs, assessment = add_observation(db, p, data, source="self", entered_by=p.full_name)
    db.commit()
    return {"zone": assessment.zone, "advice": advice_for(p, obs, assessment.zone), "patient_name": p.full_name}


@router.get("/self-report/lookup")
def self_report_lookup(phone: str, db: Session = Depends(get_db)):
    p = find_patient_by_phone(db, phone)
    if not p:
        raise HTTPException(404, "Ro'yxatda topilmadingiz. Oilaviy poliklinikangizga murojaat qiling.")
    return {"id": p.id, "full_name": p.full_name, "kind": p.kind}


# ---------------- alerts ----------------
@router.get("/alerts")
def list_alerts(status: str | None = None, district_id: int | None = None, limit: int = 100,
                db: Session = Depends(get_db)):
    stmt = select(models.Alert).join(models.Patient)
    if status == "active":
        stmt = stmt.where(models.Alert.status != "resolved")
    elif status:
        stmt = stmt.where(models.Alert.status == status)
    if district_id:
        stmt = stmt.where(models.Patient.district_id == district_id)
    stmt = stmt.order_by(models.Alert.created_at.desc())
    if status == "active":  # red & unacknowledged first, so missed check-ins never bury emergencies
        alerts = sorted(db.scalars(stmt).all(),
                        key=lambda a: (a.zone != "red", a.status != "open", -a.created_at.timestamp()))[:limit]
    else:
        alerts = db.scalars(stmt.limit(limit)).all()
    return [alert_dict(a) for a in alerts]


@router.get("/alerts/{aid}")
def get_alert(aid: int, db: Session = Depends(get_db)):
    return alert_dict(_alert(db, aid), with_events=True)


@router.post("/alerts/{aid}/ack")
def ack_alert(aid: int, body: schemas.AckIn, db: Session = Depends(get_db)):
    a = alert_svc.acknowledge(db, _alert(db, aid), body.actor)
    db.commit()
    return alert_dict(a, with_events=True)


@router.post("/alerts/{aid}/action")
def alert_action(aid: int, body: schemas.ActionIn, db: Session = Depends(get_db)):
    if body.action not in alert_svc.ACTIONS:
        raise HTTPException(400, f"action must be one of {list(alert_svc.ACTIONS)}")
    a = alert_svc.record_action(db, _alert(db, aid), body.action, body.actor, body.note)
    db.commit()
    return alert_dict(a, with_events=True)


@router.post("/alerts/{aid}/resolve")
def resolve_alert(aid: int, body: schemas.AckIn, db: Session = Depends(get_db)):
    a = alert_svc.resolve(db, _alert(db, aid), body.actor)
    db.commit()
    return alert_dict(a, with_events=True)


# ---------------- staff ----------------
@router.get("/staff")
def list_staff(db: Session = Depends(get_db)):
    rows = db.scalars(select(models.Staff).order_by(models.Staff.role, models.Staff.full_name)).all()
    return [{"id": s.id, "full_name": s.full_name, "role": s.role, "district_id": s.district_id,
             "link_code": s.link_code, "telegram_linked": bool(s.telegram_chat_id)} for s in rows]


# ---------------- ML ----------------
@router.get("/model")
def model():
    return ml.model_info() or {"error": "model not trained — run python ml/train.py"}


@router.get("/export/ml-dataset.csv")
def export_dataset(db: Session = Depends(get_db)):
    """One row per observation with patient context, current zone and outcome label.

    This is the dataset for retraining the ML model on *local* data. Names and
    phones are excluded (pseudonymised by patient id).
    """
    buf = io.StringIO()
    w = csv.writer(buf)
    sym_m = list(get_rules("mother").symptoms)
    sym_n = list(get_rules("newborn").symptoms)
    symptom_cols = list(dict.fromkeys(sym_m + sym_n))
    header = ["patient_id", "kind", "district_id", "age_years", "gestational_weeks", "parity",
              "birth_weight_g", "ga_at_birth", "apgar5", "risk_factors", "recorded_at", "source",
              *PARAMS, *[f"sym_{s}" for s in symptom_cols], "zone_now", "outcome"]
    w.writerow(header)
    for p in db.scalars(select(models.Patient)):
        for o in p.observations:
            d = o.recorded_at.date()
            w.writerow([
                p.id, p.kind, p.district_id, age_years(p.birth_date, d),
                (d - p.lmp_date).days // 7 if p.lmp_date else None, p.parity, p.birth_weight_g,
                p.gestational_age_at_birth, p.apgar5, "|".join(p.risk_factors or []), iso(o.recorded_at),
                o.source, *[getattr(o, k) for k in PARAMS],
                *[int(s in (o.symptoms or [])) for s in symptom_cols], p.zone, p.outcome or "",
            ])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=perizone_ml_dataset.csv"})
