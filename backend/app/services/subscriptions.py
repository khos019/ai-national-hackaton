"""Monthly subscription for women.

Design principle (safety first): reporting DANGER SIGNS and the emergency advice are ALWAYS FREE —
nobody should be unprotected because she didn't pay. Premium adds comfort and engagement:
the AI assistant, personal weekly reports and reminders.

  Bepul (free)   : xavf belgilari, qon bosimi, homila harakati, harorat, vazn -> shifokorga xabarnoma
  Premium        : 🤖 AI yordamchi (erkin yozish, savol-javob), haftalik shaxsiy hisobot, eslatmalar
  Trial          : 7 kun Premium — Telegram'ga ulanganda avtomatik
  Free (social)  : administrator kam ta'minlangan oilalarga bepul Premium beradi
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..timeutil import utcnow

PRICE = int(os.getenv("SUBSCRIPTION_PRICE", "19900"))  # so'm / month
TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "7"))
PLAN_UZ = {"trial": "Sinov (7 kun)", "monthly": "Premium (oylik)", "free": "Bepul Premium (ijtimoiy)"}


def current(db: Session, patient_id: int, now: datetime | None = None) -> models.Subscription | None:
    now = now or utcnow()
    return db.scalar(select(models.Subscription).where(
        models.Subscription.patient_id == patient_id, models.Subscription.cancelled.is_(False),
        models.Subscription.expires_at > now).order_by(models.Subscription.expires_at.desc()))


def is_premium(db: Session, patient_id: int) -> bool:
    return current(db, patient_id) is not None


def status(db: Session, patient_id: int) -> dict:
    sub = current(db, patient_id)
    last = db.scalar(select(models.Subscription).where(models.Subscription.patient_id == patient_id)
                     .order_by(models.Subscription.expires_at.desc()))
    if sub:
        days = max(0, (sub.expires_at - utcnow()).days)
        return {"active": True, "plan": sub.plan, "plan_uz": PLAN_UZ[sub.plan], "expires_at": sub.expires_at.isoformat(),
                "days_left": days, "price": PRICE}
    return {"active": False, "plan": None, "plan_uz": "Bepul (asosiy)",
            "expired_at": last.expires_at.isoformat() if last else None, "had_trial": bool(last), "price": PRICE}


def _extend_from(db: Session, patient_id: int) -> datetime:
    sub = current(db, patient_id)
    return sub.expires_at if sub else utcnow()


def start_trial(db: Session, patient: models.Patient) -> models.Subscription | None:
    """Once per patient, when she first links Telegram."""
    if db.scalar(select(models.Subscription.id).where(models.Subscription.patient_id == patient.id)):
        return None
    sub = models.Subscription(patient_id=patient.id, plan="trial", started_at=utcnow(),
                              expires_at=utcnow() + timedelta(days=TRIAL_DAYS), amount=0, provider="auto")
    db.add(sub)
    return sub


def pay_month(db: Session, patient: models.Patient, provider: str = "demo", payment_ref: str | None = None,
              months: int = 1) -> models.Subscription:
    start = _extend_from(db, patient.id)
    sub = models.Subscription(patient_id=patient.id, plan="monthly", started_at=utcnow(),
                              expires_at=start + timedelta(days=30 * months), amount=PRICE * months,
                              provider=provider, payment_ref=payment_ref)
    db.add(sub)
    return sub


def grant_free(db: Session, patient: models.Patient, months: int = 3) -> models.Subscription:
    start = _extend_from(db, patient.id)
    sub = models.Subscription(patient_id=patient.id, plan="free", started_at=utcnow(),
                              expires_at=start + timedelta(days=30 * months), amount=0, provider="owner")
    db.add(sub)
    return sub


def cancel(db: Session, patient: models.Patient) -> int:
    n = 0
    for s in db.scalars(select(models.Subscription).where(models.Subscription.patient_id == patient.id,
                                                          models.Subscription.expires_at > utcnow(),
                                                          models.Subscription.cancelled.is_(False))):
        s.cancelled = True
        n += 1
    return n


def summary(db: Session, patient_ids: list[int] | None = None) -> dict:
    now = utcnow()
    q = select(models.Subscription)
    subs = db.scalars(q).all()
    if patient_ids is not None:
        allowed = set(patient_ids)
        subs = [s for s in subs if s.patient_id in allowed]
    active: dict[int, models.Subscription] = {}
    for s in subs:
        if not s.cancelled and s.expires_at > now:
            if s.patient_id not in active or s.expires_at > active[s.patient_id].expires_at:
                active[s.patient_id] = s
    by_plan = {"trial": 0, "monthly": 0, "free": 0}
    for s in active.values():
        by_plan[s.plan] += 1
    month_ago = now - timedelta(days=30)
    revenue_30d = sum(s.amount for s in subs if s.started_at >= month_ago)
    ever_trial = {s.patient_id for s in subs if s.plan == "trial"}
    converted = {s.patient_id for s in subs if s.plan == "monthly"} & ever_trial
    return {
        "price": PRICE, "trial_days": TRIAL_DAYS,
        "active_total": len(active), "by_plan": by_plan,
        "mrr": by_plan["monthly"] * PRICE,
        "revenue_30d": revenue_30d,
        "trial_conversion": round(len(converted) / len(ever_trial), 3) if ever_trial else None,
        "expiring_7d": sum(1 for s in active.values() if s.expires_at - now < timedelta(days=7)),
    }
