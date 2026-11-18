"""Single entry point for new data — used by the web API, the mother's web form and the Telegram bot."""
from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..rules.engine import PARAMS, get_rules
from ..timeutil import utcnow
from .assessment import reassess


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    return digits[-9:] if len(digits) >= 9 else None


def find_patients_by_phone(db: Session, phone: str) -> list[models.Patient]:
    """A mother and her newborn usually share the mother's phone number."""
    key = normalize_phone(phone)
    if not key:
        return []
    rows = db.scalars(select(models.Patient).where(models.Patient.active.is_(True))).all()
    return sorted((p for p in rows if normalize_phone(p.phone) == key), key=lambda p: p.kind != "mother")


def find_patient_by_phone(db: Session, phone: str) -> models.Patient | None:
    found = find_patients_by_phone(db, phone)
    return found[0] if found else None


def add_observation(db: Session, patient: models.Patient, data: dict, *, source: str,
                    entered_by: str | None = None, recorded_at: datetime | None = None,
                    notify: bool = True):
    rules = get_rules(patient.kind)
    symptoms = [s for s in data.get("symptoms") or [] if s in rules.symptoms]
    obs = models.Observation(
        patient_id=patient.id, recorded_at=recorded_at or utcnow(), source=source,
        entered_by=entered_by, symptoms=symptoms, note=data.get("note"),
        **{k: data.get(k) for k in PARAMS},
    )
    db.add(obs)
    patient.observations.append(obs)
    db.flush()
    assessment = reassess(db, patient, trigger=obs, now=obs.recorded_at if recorded_at else None, notify=notify)
    return obs, assessment


def advice_for(patient: models.Patient, obs: models.Observation, zone: str) -> dict:
    """What we tell the woman right after she reports. Safety first: danger signs -> call 103."""
    red_now = get_rules(patient.kind).evaluate_single(obs, obs.recorded_at)
    if red_now:
        return {
            "level": "red",
            "title": "Darhol tibbiy yordamga murojaat qiling!",
            "text": (f"Siz kiritgan belgilar xavfli bo'lishi mumkin. Hoziroq {settings.emergency_phone} ga "
                     "qo'ng'iroq qiling yoki eng yaqin tug'ruq kompleksiga boring. "
                     "Mutaxassisingizga avtomatik xabar yuborildi."),
            "reasons": [f.label for f in red_now],
        }
    if zone in ("yellow", "red"):
        return {
            "level": "yellow",
            "title": "Mutaxassis siz bilan bog'lanadi",
            "text": ("Ma'lumotingiz qabul qilindi va shifokoringizga ko'rsatildi. Yaqin vaqt ichida siz bilan "
                     f"bog'lanishadi. Ahvolingiz yomonlashsa — {settings.emergency_phone}."),
            "reasons": [],
        }
    return {
        "level": "green",
        "title": "Rahmat! Ko'rsatkichlaringiz me'yorda",
        "text": "Har kuni o'zingizni kuzatishda davom eting. Belgilar paydo bo'lsa, darhol xabar bering.",
        "reasons": [],
    }
