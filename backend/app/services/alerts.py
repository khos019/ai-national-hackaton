"""Alert lifecycle: create (with de-duplication), notify, escalate, acknowledge, act, resolve."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..timeutil import utcnow
from . import notify as notifier

LEVEL_ROLE = {0: "specialist", 1: "head", 2: "regional"}
LEVEL_UZ = {0: "OvaBMU mutaxassisi", 1: "Tuman bosh shifokori", 2: "Viloyat"}
ACTIONS = {
    "called": "Bemorga qo'ng'iroq qilindi",
    "home_visit": "Uyga patronaj yuborildi",
    "referred": "Perinatal markazga yo'naltirildi",
    "ambulance": "Tez yordam (103) chaqirildi",
    "verified_ok": "Tekshirildi — xavf tasdiqlanmadi",
}


def _escalation_delay(level: int) -> timedelta | None:
    if level >= len(settings.escalation_seconds):
        return None
    return timedelta(seconds=settings.escalation_seconds[level])


def log_event(db: Session, alert: models.Alert, type_: str, actor: str | None = None,
              detail: str | None = None, at: datetime | None = None) -> None:
    db.add(models.AlertEvent(alert_id=alert.id, type=type_, actor=actor, detail=detail, at=at or utcnow()))


def recipients(db: Session, alert: models.Alert) -> list[models.Staff]:
    role = LEVEL_ROLE[alert.level]
    q = select(models.Staff).where(models.Staff.role == role)
    if role != "regional":
        q = q.where(models.Staff.district_id == alert.patient.district_id)
    return list(db.scalars(q))


def dispatch(db: Session, alert: models.Alert, now: datetime | None = None) -> None:
    for staff in recipients(db, alert):
        channel = notifier.send_alert(alert, staff)
        log_event(db, alert, "notified", actor=staff.full_name,
                  detail=f"{LEVEL_UZ[alert.level]} · kanal: {channel}", at=now)


def create_alert(db: Session, patient: models.Patient, *, kind: str, zone: str, title: str,
                 message: str, assessment_id: int | None = None, now: datetime | None = None,
                 notify: bool = True) -> models.Alert:
    now = now or utcnow()

    # De-duplicate: one open alert per patient & kind (except danger signs, which always page).
    if kind != "danger_sign":
        existing = db.scalar(
            select(models.Alert).where(
                models.Alert.patient_id == patient.id,
                models.Alert.kind == kind,
                models.Alert.status != "resolved",
            )
        )
        if existing:
            existing.message = message
            if zone == "red" and existing.zone != "red":
                existing.zone, existing.title = "red", title
                log_event(db, existing, "updated", detail="Zona QIZILga ko'tarildi\n" + message, at=now)
                if notify:
                    dispatch(db, existing, now)
            else:
                log_event(db, existing, "updated", detail=message, at=now)
            return existing

    delay = _escalation_delay(0)
    alert = models.Alert(
        patient_id=patient.id, assessment_id=assessment_id, created_at=now, kind=kind, zone=zone,
        title=title, message=message, level=0, status="open",
        next_escalation_at=(now + delay) if (delay and zone == "red") else None,
    )
    alert.patient = patient
    db.add(alert)
    db.flush()
    log_event(db, alert, "created", detail=title, at=now)
    if notify:
        dispatch(db, alert, now)
    return alert


def acknowledge(db: Session, alert: models.Alert, actor: str) -> models.Alert:
    if alert.status == "open":
        alert.status = "acknowledged"
        alert.acknowledged_by = actor
        alert.acknowledged_at = utcnow()
        alert.next_escalation_at = None
        log_event(db, alert, "acknowledged", actor=actor)
    return alert


def record_action(db: Session, alert: models.Alert, action: str, actor: str, note: str | None = None) -> models.Alert:
    acknowledge(db, alert, actor)
    text = ACTIONS.get(action, action)
    log_event(db, alert, "action", actor=actor, detail=text + (f" — {note}" if note else ""))
    if action in ("verified_ok", "referred", "ambulance"):
        resolve(db, alert, actor)
    return alert


def resolve(db: Session, alert: models.Alert, actor: str) -> models.Alert:
    if alert.status != "resolved":
        alert.status = "resolved"
        alert.resolved_at = utcnow()
        alert.next_escalation_at = None
        log_event(db, alert, "resolved", actor=actor)
    return alert


def run_escalations(db: Session, now: datetime | None = None) -> int:
    """Escalate unacknowledged red alerts whose timer expired. Returns count escalated."""
    now = now or utcnow()
    due = db.scalars(
        select(models.Alert).where(
            models.Alert.status == "open",
            models.Alert.next_escalation_at.is_not(None),
            models.Alert.next_escalation_at <= now,
        )
    ).all()
    for alert in due:
        if alert.level >= 2:
            alert.next_escalation_at = None
            continue
        alert.level += 1
        delay = _escalation_delay(alert.level)
        alert.next_escalation_at = now + delay if delay else None
        log_event(db, alert, "escalated", detail=f"Javob berilmadi → {LEVEL_UZ[alert.level]}", at=now)
        dispatch(db, alert, now)
    return len(due)


def run_missed_checkins(db: Session, now: datetime | None = None) -> int:
    from .assessment import stale_patients

    now = now or utcnow()
    n = 0
    for p in stale_patients(db, now):
        if p.zone == "green":
            continue  # green patients get a reminder (bot), not a staff alert
        already = db.scalar(select(models.Alert.id).where(
            models.Alert.patient_id == p.id, models.Alert.kind == "missed_checkin",
            models.Alert.status != "resolved"))
        if already:
            continue
        days = (now - p.last_observation_at).days
        create_alert(
            db, p, kind="missed_checkin", zone="yellow",
            title="Ma'lumot kelmayapti", now=now,
            message=f"• {days} kundan beri ma'lumot yo'q (zona: {p.zone}). Bog'laning.",
        )
        notifier.remind_patient(p)
        n += 1
    return n
