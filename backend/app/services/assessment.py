"""Re-assess a patient after new data and raise alerts when things get worse."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..rules.engine import ZONE_RANK, Finding, get_rules, worst
from ..timeutil import utcnow
from . import ml

ZONE_UZ = {"green": "YASHIL", "yellow": "SARIQ", "red": "QIZIL"}


def age_years(birth: date | None, on: date) -> int | None:
    if not birth:
        return None
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


def gestational_weeks(p: models.Patient, on: date) -> int | None:
    if p.kind != "mother" or not p.lmp_date:
        return None
    return (on - p.lmp_date).days // 7


def profile_of(p: models.Patient, now: datetime) -> dict:
    return {
        "kind": p.kind,
        "age_years": age_years(p.birth_date, now.date()),
        "risk_factors": p.risk_factors or [],
        "birth_weight_g": p.birth_weight_g,
        "gestational_age_at_birth": p.gestational_age_at_birth,
        "apgar5": p.apgar5,
    }


def reassess(
    db: Session,
    patient: models.Patient,
    trigger: models.Observation | None = None,
    now: datetime | None = None,
    notify: bool = True,
) -> models.Assessment:
    now = now or utcnow()
    rules = get_rules(patient.kind)
    result = rules.evaluate(profile_of(patient, now), patient.observations, now)
    findings = list(result.findings)
    zone = result.zone

    # ML advisory layer (mothers only — the model is trained on maternal data)
    ml_out = None
    if patient.kind == "mother":
        lv = {k: v["value"] for k, v in result.latest.items()}
        ml_out = ml.predict({
            "age": age_years(patient.birth_date, now.date()),
            "sbp": lv.get("sbp"), "dbp": lv.get("dbp"), "glucose": lv.get("glucose"),
            "temp_c": lv.get("temperature"), "heart_rate": lv.get("heart_rate"),
        })
        if ml_out and ml_out["high"] >= settings.ml_high_threshold:
            findings.append(Finding(
                code="ml:high_risk", category="ml", zone="yellow",
                label=f"ML model: yuqori xavf ehtimoli {round(ml_out['high'] * 100)}% (maslahat)",
                value=ml_out["high"],
            ))
            zone = worst(zone, "yellow")

    prev_zone = patient.zone if patient.zone_updated_at else None
    assessment = models.Assessment(
        patient_id=patient.id, created_at=now, zone=zone, prev_zone=prev_zone,
        reasons=[f.to_dict() for f in findings], ml=ml_out,
        trigger_observation_id=trigger.id if trigger else None,
    )
    db.add(assessment)
    patient.zone = zone
    patient.zone_reasons = assessment.reasons
    patient.ml_risk = ml_out
    patient.zone_updated_at = now
    if patient.observations:
        patient.last_observation_at = max(o.recorded_at for o in patient.observations)
    db.flush()

    _maybe_alert(db, patient, assessment, prev_zone, findings, trigger, now, notify)
    return assessment


def _maybe_alert(db, patient, assessment, prev_zone, findings, trigger, now, notify):
    from .alerts import create_alert

    new_red_from_trigger: list[Finding] = []
    if trigger is not None:
        new_red_from_trigger = get_rules(patient.kind).evaluate_single(trigger, now)

    worsened = prev_zone is not None and ZONE_RANK[assessment.zone] > ZONE_RANK[prev_zone]
    first_time_bad = prev_zone is None and assessment.zone != "green" and trigger is not None
    if not (worsened or first_time_bad or new_red_from_trigger):
        # Zone unchanged, but the woman herself reported complaints (e.g. fever again): the doctor
        # must still see it — attach to her open alert (re-notify) or open a new one.
        if trigger is not None and trigger.source == "self" and assessment.zone != "green":
            own = [f for f in get_rules(patient.kind).evaluate({"risk_factors": []}, [trigger], now).findings
                   if f.zone in ("yellow", "red")]
            if own:
                from .alerts import report_from_patient
                msg = "\n".join(f"• {f.label} (o‘zi kiritgan)" for f in own[:6])
                report_from_patient(db, patient, msg, zone=assessment.zone, now=now, notify=notify)
        return

    active = [f for f in findings if f.zone == assessment.zone and f.category != "risk_factor"] or \
             [f for f in findings if f.zone == assessment.zone]
    sourced = [f for f in active if f.source]
    all_self = bool(sourced) and all(f.self_reported for f in sourced)
    has_symptom = any(f.category == "symptom" and f.zone == "red" for f in new_red_from_trigger)

    if has_symptom:
        kind = "danger_sign"
    elif all_self and assessment.zone == "red":
        kind = "verify_self_report"
    else:
        kind = "zone_worsened"

    titles = {
        "danger_sign": "Xavfli belgi xabar qilindi",
        "verify_self_report": "O'zi kiritgan ma'lumot qizil zonada — tasdiqlang",
        "zone_worsened": (
            f"Zona yomonlashdi: {ZONE_UZ.get(prev_zone or 'green')} → {ZONE_UZ[assessment.zone]}"
            if worsened or first_time_bad else f"Yangi xavfli ko'rsatkich (zona {ZONE_UZ[assessment.zone]})"
        ),
    }
    # A clinic/lab reading that confirms an earlier self-reported red: close the loop on that alert.
    if trigger is not None and trigger.source != "self" and assessment.zone == "red":
        from .alerts import log_event
        for pending in db.scalars(select(models.Alert).where(
                models.Alert.patient_id == patient.id, models.Alert.kind == "verify_self_report",
                models.Alert.status != "resolved")):
            pending.title = "O'zi kiritgan ma'lumot klinik o'lchov bilan TASDIQLANDI"
            log_event(db, pending, "updated", actor=trigger.entered_by,
                      detail="Klinik o'lchov bilan tasdiqlandi", at=now)

    reasons = "\n".join(
        f"• {f.label}{' (o‘zi kiritgan)' if f.self_reported else ''}" for f in (new_red_from_trigger or active)[:6]
    )
    create_alert(
        db, patient, kind=kind, zone=assessment.zone, title=titles[kind], message=reasons,
        assessment_id=assessment.id, now=now, notify=notify,
    )


def stale_patients(db: Session, now: datetime) -> list[models.Patient]:
    """Active patients who have not sent data within the expected check-in interval for their zone."""
    out = []
    for p in db.scalars(select(models.Patient).where(models.Patient.active.is_(True))):
        expected = get_rules(p.kind).checkin_days.get(p.zone)
        if expected and p.last_observation_at and now - p.last_observation_at > timedelta(days=expected):
            out.append(p)
    return out
