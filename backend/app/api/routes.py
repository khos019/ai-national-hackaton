from __future__ import annotations

import csv
import io
import threading
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import auth, models, schemas
from ..auth import current_staff, get_patient_for, require_owner, scope_patients, staff_public
from ..config import settings
from ..db import get_db
from ..rules.engine import PARAMS, get_rules
from ..serializers import alert_dict, iso, observation_dict, patient_summary, self_report_features
from ..services import ai_assistant, ml, notify
from ..services import alerts as alert_svc
from ..services import subscriptions as subs
from ..services.assessment import age_years, gestational_weeks, reassess
from ..services.intake import add_observation, advice_for, find_patient_by_phone, normalize_phone
from ..timeutil import utcnow

router = APIRouter(prefix="/api")
Staff = models.Staff


def _alert_for(db: Session, staff: Staff, aid: int) -> models.Alert:
    a = db.get(models.Alert, aid)
    if not a or not auth.can_access(staff, a.patient):
        raise HTTPException(404, "Xabarnoma topilmadi")
    return a


def _activation(code: str | None) -> dict:
    return {"link_code": code, "activation_path": f"/activate.html?code={code}" if code else None}


# ======================= public (patients, login) =======================
@router.get("/meta")
def meta(db: Session = Depends(get_db)):
    """Catalogs for forms (symptoms, parameters, risk factors) + districts. Not patient data."""
    def catalog(kind):
        r = get_rules(kind)
        return {
            "parameters": {k: {"label": v["label"], "unit": v.get("unit", ""), "value_labels": v.get("value_labels")}
                           for k, v in r.parameters.items()},
            "symptoms": {k: {"label": v["label"], "zone": v["zone"]} for k, v in r.symptoms.items()},
            "risk_factors": {k: {"label": v["label"], "zone_floor": v.get("zone_floor", "green"),
                                 "auto": v.get("auto", False)} for k, v in r.risk_factors.items()},
            "checkin_days": r.checkin_days,
        }

    districts = db.scalars(select(models.District).order_by(models.District.name)).all()
    return {
        "districts": [{"id": d.id, "name": d.name, "region": d.region, "lat": d.lat, "lon": d.lon} for d in districts],
        "mother": catalog("mother"),
        "newborn": catalog("newborn"),
        "actions": alert_svc.ACTIONS,
        "telegram_enabled": notify.telegram_enabled(),
        "bot_username": settings.bot_username,
        "escalation_seconds": settings.escalation_seconds,
        "emergency_phone": settings.emergency_phone,
        "subscription": {"price": subs.PRICE, "trial_days": subs.TRIAL_DAYS},
        "ai": {"engine": ai_assistant.AI_MODEL if ai_assistant.claude_enabled() else "rules"},
    }


@router.post("/auth/login")
def auth_login(body: schemas.LoginIn, response: Response, db: Session = Depends(get_db)):
    sess = auth.login(db, body.phone, body.password)
    response.set_cookie(auth.COOKIE, sess.token, httponly=True, samesite="lax", max_age=auth.SESSION_DAYS * 86400)
    return {"ok": True, "user": staff_public(db.get(Staff, sess.staff_id))}


@router.post("/auth/activate")
def auth_activate(body: schemas.ActivateIn, response: Response, db: Session = Depends(get_db)):
    sess = auth.activate(db, body.phone, body.code, body.password)
    response.set_cookie(auth.COOKIE, sess.token, httponly=True, samesite="lax", max_age=auth.SESSION_DAYS * 86400)
    return {"ok": True, "user": staff_public(db.get(Staff, sess.staff_id))}


@router.post("/auth/logout")
def auth_logout(response: Response, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    for s in db.scalars(select(models.Session).where(models.Session.staff_id == staff.id)):
        db.delete(s)
    db.commit()
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


@router.get("/me")
def me(staff: Staff = Depends(current_staff)):
    return staff_public(staff)


@router.post("/self-report", status_code=201)
def self_report(body: schemas.SelfReportIn, db: Session = Depends(get_db)):
    p = db.get(models.Patient, body.patient_id) if body.patient_id else None
    if p and body.phone and normalize_phone(p.phone) != normalize_phone(body.phone):
        p = None  # the id must match the phone the woman entered
    if not p and body.phone:
        p = find_patient_by_phone(db, body.phone)
    if not p:
        raise HTTPException(404, "Ro'yxatda topilmadingiz. Shifokoringiz yoki patronaj hamshirangizga murojaat qiling.")
    data = body.model_dump(exclude={"patient_id", "phone"})
    obs, assessment = add_observation(db, p, data, source="self", entered_by=p.full_name)
    db.commit()
    return {"zone": assessment.zone, "advice": advice_for(p, obs, assessment.zone)}


@router.get("/self-report/lookup")
def self_report_lookup(phone: str, db: Session = Depends(get_db)):
    p = find_patient_by_phone(db, phone)
    if not p:
        raise HTTPException(404, "Ro'yxatda topilmadingiz. Shifokoringiz yoki patronaj hamshirangizga murojaat qiling.")
    parts = p.full_name.split()
    masked = parts[0] + (f" {parts[1][0]}." if len(parts) > 1 else "")  # don't leak full names by phone
    return {"id": p.id, "display_name": masked, "kind": p.kind, "self_report": self_report_features(p),
            "doctor": p.doctor.full_name if p.doctor else None, "bot_username": settings.bot_username}


# ======================= staff area =======================
@router.get("/rules/{kind}")
def rules(kind: str, staff: Staff = Depends(current_staff)):
    if kind not in ("mother", "newborn"):
        raise HTTPException(404)
    return get_rules(kind).spec


@router.get("/dashboard")
def dashboard(district_id: int | None = None, doctor_id: int | None = None,
              db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    def patient_filter(stmt):
        stmt = scope_patients(stmt.where(models.Patient.active.is_(True)), staff)
        if staff.role == "owner" and district_id:
            stmt = stmt.where(models.Patient.district_id == district_id)
        if staff.role == "owner" and doctor_id:
            stmt = stmt.where(models.Patient.doctor_id == doctor_id)
        return stmt

    counts = {"mother": {"green": 0, "yellow": 0, "red": 0}, "newborn": {"green": 0, "yellow": 0, "red": 0}}
    pq = patient_filter(select(models.Patient.kind, models.Patient.zone, func.count()))
    for kind, zone, n in db.execute(pq.group_by(models.Patient.kind, models.Patient.zone)):
        counts[kind][zone] = n

    alerts = db.scalars(patient_filter(select(models.Alert).join(models.Patient))).all()
    open_alerts = [a for a in alerts if a.status == "open"]
    acked = [a for a in alerts if a.acknowledged_at]
    mean_ack = (sum((a.acknowledged_at - a.created_at).total_seconds() for a in acked) / len(acked)) if acked else None

    out = {
        "counts": counts,
        "open_alerts": len(open_alerts),
        "open_red_alerts": sum(1 for a in open_alerts if a.zone == "red"),
        "escalated_alerts": sum(1 for a in alerts if a.level > 0 and a.status != "resolved"),
        "mean_ack_seconds": round(mean_ack) if mean_ack is not None else None,
        "now": iso(utcnow()),
    }
    if staff.role == "owner":
        rows: dict[int, dict] = {}
        dq = select(models.District.id, models.District.name, models.Patient.zone, func.count()).join(
            models.Patient, models.Patient.district_id == models.District.id).where(models.Patient.active.is_(True))
        for did, name, zone, n in db.execute(dq.group_by(models.District.id, models.Patient.zone)):
            rows.setdefault(did, {"id": did, "name": name, "green": 0, "yellow": 0, "red": 0})[zone] = n
        out["by_district"] = sorted(rows.values(), key=lambda r: (-r["red"], -r["yellow"]))
        out["by_doctor"] = _doctor_stats(db, district_id)
    return out


def _doctor_stats(db: Session, district_id: int | None = None) -> list[dict]:
    q = select(Staff).where(Staff.role == "doctor")
    if district_id:
        q = q.where(Staff.district_id == district_id)
    rows = []
    for d in db.scalars(q):
        pats = db.scalars(select(models.Patient).where(models.Patient.doctor_id == d.id,
                                                       models.Patient.active.is_(True))).all()
        alerts = db.scalars(select(models.Alert).join(models.Patient).where(models.Patient.doctor_id == d.id)).all()
        acked = [a for a in alerts if a.acknowledged_at]
        rows.append({
            **staff_public(d),
            "patients": len(pats), "newborns": sum(p.kind == "newborn" for p in pats),
            "red": sum(p.zone == "red" for p in pats), "yellow": sum(p.zone == "yellow" for p in pats),
            "open_alerts": sum(a.status == "open" for a in alerts),
            "mean_ack_seconds": round(sum((a.acknowledged_at - a.created_at).total_seconds() for a in acked) / len(acked)) if acked else None,
        })
    return sorted(rows, key=lambda r: (-r["open_alerts"], -r["red"], r["full_name"]))


# ---------------- patients ----------------
@router.get("/patients")
def list_patients(
    zone: str | None = None, kind: str | None = None, district_id: int | None = None, doctor_id: int | None = None,
    q: str | None = None, limit: int = Query(1000, le=5000),
    db: Session = Depends(get_db), staff: Staff = Depends(current_staff),
):
    stmt = scope_patients(select(models.Patient).where(models.Patient.active.is_(True)), staff)
    if zone:
        stmt = stmt.where(models.Patient.zone == zone)
    if kind:
        stmt = stmt.where(models.Patient.kind == kind)
    if district_id:
        stmt = stmt.where(models.Patient.district_id == district_id)
    if doctor_id and staff.role == "owner":
        stmt = stmt.where(models.Patient.doctor_id == doctor_id)
    if q:
        stmt = stmt.where(models.Patient.full_name.ilike(f"%{q}%") | models.Patient.phone.ilike(f"%{q}%"))
    patients = db.scalars(stmt).all()
    rank = {"red": 0, "yellow": 1, "green": 2}
    patients = sorted(patients, key=lambda p: (rank[p.zone], -(p.zone_updated_at.timestamp() if p.zone_updated_at else 0)))
    return [patient_summary(p) for p in patients[:limit]]


@router.post("/patients", status_code=201)
def create_patient(body: schemas.PatientIn, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    return register_patient(db, staff, body)


MATERNAL_DIABETES = {"diabetes", "gestational_diabetes"}
# Baseline exam required before a patient can be registered (field -> label)
REQUIRED_BASELINE = {
    "mother": {"sbp": "sistolik bosim", "dbp": "diastolik bosim", "hemoglobin": "gemoglobin", "weight": "vazn",
               "temperature": "harorat"},
    "newborn": {"weight": "hozirgi vazn", "temperature": "harorat"},
}


_register_lock = threading.Lock()


def register_patient(db: Session, staff: Staff, body: schemas.PatientIn) -> dict:
    """Serialized: two simultaneous submits (double click) must not both pass the duplicate check."""
    with _register_lock:
        return _register_patient(db, staff, body)


def _register_patient(db: Session, staff: Staff, body: schemas.PatientIn) -> dict:
    if not body.consent:
        raise HTTPException(400, "Bemorning ma'lumotlarni qayta ishlashga roziligi kerak")
    initial = body.initial.model_dump() if body.initial else {}
    missing = [label for f, label in REQUIRED_BASELINE[body.kind].items() if initial.get(f) is None]
    if missing:
        raise HTTPException(400, "Avval boshlang'ich ko'rik natijalarini kiriting: " + ", ".join(missing))
    mother = None
    if body.kind == "newborn" and body.mother_id:
        mother = db.get(models.Patient, body.mother_id)
        if not mother or mother.kind != "mother" or not auth.can_access(staff, mother):
            raise HTTPException(400, "Ona topilmadi")
        body.phone = body.phone or mother.phone  # the baby is reported from the mother's Telegram
        if MATERNAL_DIABETES & set(mother.risk_factors or []) and "maternal_diabetes" not in body.risk_factors:
            body.risk_factors = [*body.risk_factors, "maternal_diabetes"]
        if body.delivery and body.birth_date:
            mother.outcome, mother.outcome_date = body.delivery, body.birth_date
    elif body.kind == "newborn":
        body.mother_id = None
    if staff.role == "doctor":
        doctor = staff
    else:
        doctor = db.get(Staff, body.doctor_id) if body.doctor_id else (mother.doctor if mother else None)
        if not doctor or doctor.role != "doctor":
            raise HTTPException(400, "Mas'ul shifokorni tanlang")
    if body.phone and body.kind == "mother":
        key = normalize_phone(body.phone)
        if not key:
            raise HTTPException(400, "Telefon raqam noto'g'ri")
        for other in db.scalars(select(models.Patient).where(models.Patient.kind == "mother",
                                                             models.Patient.active.is_(True))):
            if normalize_phone(other.phone) == key:
                raise HTTPException(409, f"Bu raqam bilan homilador ayol allaqachon ro'yxatda (ID {other.id})")
    data = body.model_dump(exclude={"doctor_id", "district_id", "delivery", "initial"})
    p = models.Patient(**data, doctor_id=doctor.id, district_id=doctor.district_id or body.district_id)
    db.add(p)
    db.flush()
    initial["note"] = initial.get("note") or "Ro'yxatga olishdagi boshlang'ich ko'rik"
    add_observation(db, p, initial, source="clinic", entered_by=staff.full_name)  # zone from day one
    db.commit()
    return patient_summary(p)


@router.get("/patients/{pid}")
def get_patient(pid: int, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    p = get_patient_for(db, staff, pid)
    today = utcnow().date()
    assessments = db.scalars(select(models.Assessment).where(models.Assessment.patient_id == pid)
                             .order_by(models.Assessment.created_at.desc()).limit(30)).all()
    alerts = db.scalars(select(models.Alert).where(models.Alert.patient_id == pid)
                        .order_by(models.Alert.created_at.desc())).all()
    data = patient_summary(p)
    data.update(
        birth_date=iso(p.birth_date), address=p.address, lmp_date=iso(p.lmp_date), parity=p.parity,
        edd=iso(p.lmp_date + timedelta(days=280)) if p.lmp_date else None,
        mother_id=p.mother_id, birth_weight_g=p.birth_weight_g, consent=p.consent,
        gestational_age_at_birth=p.gestational_age_at_birth, apgar5=p.apgar5,
        risk_factors=p.risk_factors or [], outcome=p.outcome, outcome_date=iso(p.outcome_date),
        reasons=p.zone_reasons or [], ml=p.ml_risk,
        observations=[observation_dict(o) for o in reversed(p.observations)],
        zone_history=[{"at": iso(a.created_at), "zone": a.zone} for a in reversed(assessments)],
        alerts=[alert_dict(a, with_events=True) for a in alerts],
        age=age_years(p.birth_date, today), gestational_weeks=gestational_weeks(p, today),
        subscription=subs.status(db, _account_patient_id(db, p)),
        mother=_linked_mother(db, staff, p),
        children=[patient_summary(c) for c in db.scalars(select(models.Patient).where(
            models.Patient.mother_id == p.id, models.Patient.active.is_(True))) if auth.can_access(staff, c)]
        if p.kind == "mother" else [],
        ai_messages=[{"at": iso(m.created_at), "role": m.role, "text": m.text, "urgency": m.urgency,
                      "extracted": m.extracted, "engine": m.engine}
                     for m in db.scalars(select(models.AiMessage).where(models.AiMessage.patient_id == pid)
                                         .order_by(models.AiMessage.created_at.desc()).limit(40))][::-1],
    )
    return data


def _linked_mother(db: Session, staff: Staff, p: models.Patient) -> dict | None:
    """Mother's summary on a newborn's card — only if this staff member may see her too."""
    if p.kind != "newborn" or not p.mother_id:
        return None
    m = db.get(models.Patient, p.mother_id)
    return patient_summary(m) if m and auth.can_access(staff, m) else None


def _account_patient_id(db: Session, p: models.Patient) -> int:
    """A newborn shares the mother's subscription."""
    return p.mother_id if p.kind == "newborn" and p.mother_id else p.id


@router.post("/patients/{pid}/subscription")
def subscription_action(pid: int, body: schemas.SubscriptionAction, db: Session = Depends(get_db),
                        owner: Staff = Depends(require_owner)):
    p = get_patient_for(db, owner, pid)
    acc = db.get(models.Patient, _account_patient_id(db, p))
    if body.action == "grant_free":
        subs.grant_free(db, acc, body.months)
    elif body.action == "pay_month":  # cash / bank transfer recorded by the administrator
        subs.pay_month(db, acc, provider="owner", months=body.months)
    else:
        subs.cancel(db, acc)
    db.commit()
    return subs.status(db, acc.id)


@router.get("/subscriptions")
def subscriptions_overview(db: Session = Depends(get_db), owner: Staff = Depends(require_owner)):
    rows = []
    for p in db.scalars(select(models.Patient).where(models.Patient.active.is_(True), models.Patient.kind == "mother")):
        st = subs.status(db, p.id)
        last_pay = db.scalar(select(models.Subscription).where(models.Subscription.patient_id == p.id)
                             .order_by(models.Subscription.started_at.desc()))
        rows.append({"patient_id": p.id, "full_name": p.full_name, "phone": p.phone, "zone": p.zone,
                     "doctor": p.doctor.full_name if p.doctor else None, "telegram_linked": bool(p.telegram_chat_id),
                     **st, "last_provider": last_pay.provider if last_pay else None,
                     "last_amount": last_pay.amount if last_pay else None})
    rank = {"monthly": 0, "free": 1, "trial": 2, None: 3}
    rows.sort(key=lambda r: (rank.get(r["plan"], 3), r["full_name"]))
    return {"summary": subs.summary(db), "rows": rows}


@router.patch("/patients/{pid}")
def patch_patient(pid: int, body: schemas.PatientPatch, db: Session = Depends(get_db),
                  staff: Staff = Depends(current_staff)):
    p = get_patient_for(db, staff, pid)
    changes = body.model_dump(exclude_unset=True)
    if "doctor_id" in changes:
        if staff.role != "owner":
            raise HTTPException(403, "Bemorni boshqa shifokorga faqat administrator o'tkaza oladi")
        doctor = db.get(Staff, changes["doctor_id"])
        if not doctor or doctor.role != "doctor":
            raise HTTPException(400, "Shifokor topilmadi")
        p.district_id = doctor.district_id or p.district_id
    for k, v in changes.items():
        setattr(p, k, v)
    if body.risk_factors is not None or body.lmp_date is not None:
        reassess(db, p)
    db.commit()
    return patient_summary(p)


@router.post("/patients/{pid}/observations", status_code=201)
def create_observation(pid: int, body: schemas.ObservationIn, db: Session = Depends(get_db),
                       staff: Staff = Depends(current_staff)):
    p = get_patient_for(db, staff, pid)
    data = body.model_dump()
    obs, assessment = add_observation(db, p, data, source=body.source, entered_by=staff.full_name,
                                      recorded_at=body.recorded_at)
    db.commit()
    return {"observation": observation_dict(obs), "zone": assessment.zone, "prev_zone": assessment.prev_zone,
            "reasons": assessment.reasons, "ml": assessment.ml}


# ---------------- alerts ----------------
@router.get("/alerts")
def list_alerts(status: str | None = None, district_id: int | None = None, limit: int = 100,
                db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    stmt = scope_patients(select(models.Alert).join(models.Patient), staff)
    if status == "active":
        stmt = stmt.where(models.Alert.status != "resolved")
    elif status:
        stmt = stmt.where(models.Alert.status == status)
    if district_id:
        stmt = stmt.where(models.Patient.district_id == district_id)
    stmt = stmt.order_by(models.Alert.created_at.desc())
    if status == "active":  # red & unacknowledged first, so missed check-ins never bury emergencies
        alerts = sorted(db.scalars(stmt).all(),
                        key=lambda a: (a.zone != "red", a.status != "open", -(a.updated_at or a.created_at).timestamp()))[:limit]
    else:
        alerts = db.scalars(stmt.limit(limit)).all()
    return [alert_dict(a) for a in alerts]


@router.get("/alerts/{aid}")
def get_alert(aid: int, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    return alert_dict(_alert_for(db, staff, aid), with_events=True)


@router.post("/alerts/{aid}/ack")
def ack_alert(aid: int, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    a = alert_svc.acknowledge(db, _alert_for(db, staff, aid), staff.full_name)
    db.commit()
    return alert_dict(a, with_events=True)


@router.post("/alerts/{aid}/action")
def alert_action(aid: int, body: schemas.ActionIn, db: Session = Depends(get_db),
                 staff: Staff = Depends(current_staff)):
    if body.action not in alert_svc.ACTIONS:
        raise HTTPException(400, f"action must be one of {list(alert_svc.ACTIONS)}")
    a = alert_svc.record_action(db, _alert_for(db, staff, aid), body.action, staff.full_name, body.note)
    db.commit()
    return alert_dict(a, with_events=True)


@router.post("/alerts/{aid}/resolve")
def resolve_alert(aid: int, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    a = alert_svc.resolve(db, _alert_for(db, staff, aid), staff.full_name)
    db.commit()
    return alert_dict(a, with_events=True)


# ---------------- staff management (owner) ----------------
@router.get("/staff")
def list_staff(db: Session = Depends(get_db), owner: Staff = Depends(require_owner)):
    out = []
    for s in db.scalars(select(Staff).order_by(Staff.role.desc(), Staff.full_name)):
        d = staff_public(s)
        d.update(_activation(s.link_code))
        out.append(d)
    stats = {r["id"]: r for r in _doctor_stats(db)}
    for d in out:
        st = stats.get(d["id"], {})
        d.update(patients=st.get("patients", 0), newborns=st.get("newborns", 0), red=st.get("red", 0), yellow=st.get("yellow", 0),
                 open_alerts=st.get("open_alerts", 0), mean_ack_seconds=st.get("mean_ack_seconds"))
    return out


@router.get("/doctors")
def list_doctors(db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    """Short list for dropdowns (owner) — a doctor only sees themself."""
    q = select(Staff).where(Staff.role == "doctor", Staff.active.is_not(False)).order_by(Staff.full_name)
    if staff.role != "owner":
        q = q.where(Staff.id == staff.id)
    return [staff_public(s) for s in db.scalars(q)]


@router.post("/staff", status_code=201)
def create_staff(body: schemas.StaffIn, db: Session = Depends(get_db), owner: Staff = Depends(require_owner)):
    if not db.get(models.District, body.district_id):
        raise HTTPException(400, "Tuman topilmadi")
    if auth.find_staff_by_phone(db, body.phone):
        raise HTTPException(409, "Bu telefon raqamli xodim allaqachon mavjud")
    s = Staff(full_name=body.full_name, phone=body.phone, district_id=body.district_id, position=body.position,
              role=body.role, link_code=auth.new_invite_code(db, "AD" if body.role == "owner" else "DR"))
    db.add(s)
    db.commit()
    d = staff_public(s)
    d.update(_activation(s.link_code))
    return d


@router.patch("/staff/{sid}")
def patch_staff(sid: int, body: schemas.StaffPatch, db: Session = Depends(get_db),
                owner: Staff = Depends(require_owner)):
    s = db.get(Staff, sid)
    if not s:
        raise HTTPException(404)
    if s.id == owner.id and body.active is False:
        raise HTTPException(400, "O'zingizni o'chira olmaysiz")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    if body.active is False:  # log out everywhere
        for sess in db.scalars(select(models.Session).where(models.Session.staff_id == s.id)):
            db.delete(sess)
    db.commit()
    return staff_public(s)


@router.post("/staff/{sid}/new-code")
def regenerate_code(sid: int, db: Session = Depends(get_db), owner: Staff = Depends(require_owner)):
    """Reset access (forgotten password / new phone): new one-time activation code, old password and sessions removed."""
    s = db.get(Staff, sid)
    if not s:
        raise HTTPException(404)
    s.link_code = auth.new_invite_code(db, "AD" if s.role == "owner" else "DR")
    s.password_hash = None
    for sess in db.scalars(select(models.Session).where(models.Session.staff_id == s.id)):
        db.delete(sess)
    db.commit()
    return _activation(s.link_code)


# ---------------- ML & export (owner) ----------------
@router.get("/model")
def model(staff: Staff = Depends(current_staff)):
    return ml.model_info() or {"error": "model not trained — run python ml/train.py"}


@router.get("/export/ml-dataset.csv")
def export_dataset(db: Session = Depends(get_db), owner: Staff = Depends(require_owner)):
    """One row per observation with patient context, current zone and outcome label.
    Names and phones are excluded (pseudonymised by patient id)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    symptom_cols = list(dict.fromkeys(list(get_rules("mother").symptoms) + list(get_rules("newborn").symptoms)))
    w.writerow(["patient_id", "kind", "district_id", "doctor_id", "age_years", "gestational_weeks", "parity",
                "birth_weight_g", "ga_at_birth", "apgar5", "risk_factors", "recorded_at", "source",
                *PARAMS, "meds_taken", *[f"sym_{s}" for s in symptom_cols], "zone_now", "outcome"])
    for p in db.scalars(select(models.Patient)):
        for o in p.observations:
            d = o.recorded_at.date()
            w.writerow([
                p.id, p.kind, p.district_id, p.doctor_id, age_years(p.birth_date, d),
                (d - p.lmp_date).days // 7 if p.lmp_date else None, p.parity, p.birth_weight_g,
                p.gestational_age_at_birth, p.apgar5, "|".join(p.risk_factors or []), iso(o.recorded_at),
                o.source, *[getattr(o, k) for k in PARAMS], "" if o.meds_taken is None else int(o.meds_taken),
                *[int(s in (o.symptoms or [])) for s in symptom_cols], p.zone, p.outcome or "",
            ])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=perizone_ml_dataset.csv"})
