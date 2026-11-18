"""Database models.

The shape loosely follows FHIR so it can later map to Uzbekistan's Digital
Health Platform (DMED, FHIR R5):  Patient -> Patient, Observation -> Observation,
Assessment -> RiskAssessment, Alert -> Flag + Communication.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .timeutil import utcnow


class District(Base):
    __tablename__ = "districts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    region: Mapped[str] = mapped_column(String(120))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)


class Staff(Base):
    """Health workers.

    role: doctor — doctor / patronage nurse; owns patients and sees only them
          owner  — health department / admin; sees all districts, manages doctors
    """

    __tablename__ = "staff"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(20))
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"))
    position: Mapped[str | None] = mapped_column(String(80))  # e.g. "Akusher-ginekolog", "Patronaj hamshirasi"
    phone: Mapped[str | None] = mapped_column(String(32))
    password_hash: Mapped[str | None] = mapped_column(String(200))  # set by the doctor on first activation
    link_code: Mapped[str | None] = mapped_column(String(16), unique=True)  # one-time activation (invite) code
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    active: Mapped[bool | None] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)

    district: Mapped[District | None] = relationship()


class Session(Base):
    """Website login session (cookie)."""

    __tablename__ = "sessions"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class Subscription(Base):
    """Monthly premium subscription of a woman (one row per paid/granted period)."""

    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    plan: Mapped[str] = mapped_column(String(20))  # trial | monthly | free (social, granted by owner)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    amount: Mapped[int] = mapped_column(Integer, default=0)  # so'm
    provider: Mapped[str | None] = mapped_column(String(20))  # click | payme | demo | owner
    payment_ref: Mapped[str | None] = mapped_column(String(64))
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)


class AiMessage(Base):
    """Telegram AI-assistant conversation (visible to the woman's doctor)."""

    __tablename__ = "ai_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    role: Mapped[str] = mapped_column(String(10))  # user | assistant
    text: Mapped[str] = mapped_column(Text)
    extracted: Mapped[dict | None] = mapped_column(JSON)  # structured data pulled from the message
    urgency: Mapped[str | None] = mapped_column(String(12))  # none | routine | urgent | emergency
    engine: Mapped[str | None] = mapped_column(String(30))  # claude model id | rules


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))  # mother | newborn
    full_name: Mapped[str] = mapped_column(String(160))
    birth_date: Mapped[date | None] = mapped_column(Date)
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"))
    doctor_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), index=True)  # responsible doctor
    consent: Mapped[bool | None] = mapped_column(Boolean)  # agreed to data processing & Telegram monitoring
    address: Mapped[str | None] = mapped_column(String(255))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)

    # Pregnancy
    lmp_date: Mapped[date | None] = mapped_column(Date)  # last menstrual period -> gestational age
    parity: Mapped[int | None] = mapped_column(Integer)

    # Newborn
    mother_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"))
    birth_weight_g: Mapped[int | None] = mapped_column(Integer)
    gestational_age_at_birth: Mapped[int | None] = mapped_column(Integer)
    apgar5: Mapped[int | None] = mapped_column(Integer)

    risk_factors: Mapped[list] = mapped_column(JSON, default=list)

    # Current state (denormalised from the latest Assessment for fast dashboards)
    zone: Mapped[str] = mapped_column(String(10), default="green", index=True)
    zone_reasons: Mapped[list] = mapped_column(JSON, default=list)
    ml_risk: Mapped[dict | None] = mapped_column(JSON)
    zone_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_observation_at: Mapped[datetime | None] = mapped_column(DateTime)

    telegram_chat_id: Mapped[int | None] = mapped_column(Integer)
    # Outcome labels -> future supervised ML training
    outcome: Mapped[str | None] = mapped_column(String(60))
    outcome_date: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    district: Mapped[District] = relationship()
    doctor: Mapped[Staff | None] = relationship(foreign_keys=[doctor_id])
    observations: Mapped[list[Observation]] = relationship(
        back_populates="patient", order_by="Observation.recorded_at", cascade="all, delete-orphan"
    )


class Observation(Base):
    """One measurement session. Wide format on purpose: easy to export for ML."""

    __tablename__ = "observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    # self = the woman herself (bot / app), clinic = nurse/doctor, lab = laboratory, device = connected device
    source: Mapped[str] = mapped_column(String(10), default="clinic")
    entered_by: Mapped[str | None] = mapped_column(String(160))

    sbp: Mapped[float | None] = mapped_column(Float)
    dbp: Mapped[float | None] = mapped_column(Float)
    heart_rate: Mapped[float | None] = mapped_column(Float)
    resp_rate: Mapped[float | None] = mapped_column(Float)
    temperature: Mapped[float | None] = mapped_column(Float)
    spo2: Mapped[float | None] = mapped_column(Float)
    glucose: Mapped[float | None] = mapped_column(Float)  # mmol/L
    hemoglobin: Mapped[float | None] = mapped_column(Float)  # g/L
    proteinuria: Mapped[int | None] = mapped_column(Integer)  # 0 neg, 1 trace, 2 = 1+, 3 = 2+, 4 = 3+
    weight: Mapped[float | None] = mapped_column(Float)  # kg (mother) / kg (newborn)
    fetal_movements: Mapped[float | None] = mapped_column(Float)  # kick count in 2 h ("count to 10")
    meds_taken: Mapped[bool | None] = mapped_column(Boolean)  # iron / folic acid taken today
    symptoms: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(Text)

    patient: Mapped[Patient] = relationship(back_populates="observations")


class Assessment(Base):
    __tablename__ = "assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    zone: Mapped[str] = mapped_column(String(10))
    prev_zone: Mapped[str | None] = mapped_column(String(10))
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    ml: Mapped[dict | None] = mapped_column(JSON)
    trigger_observation_id: Mapped[int | None] = mapped_column(ForeignKey("observations.id"))


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    assessment_id: Mapped[int | None] = mapped_column(ForeignKey("assessments.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # zone_worsened | danger_sign | verify_self_report | missed_checkin
    kind: Mapped[str] = mapped_column(String(24))
    zone: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    level: Mapped[int] = mapped_column(Integer, default=0)  # 0 specialist, 1 head physician, 2 region
    status: Mapped[str] = mapped_column(String(14), default="open", index=True)  # open | acknowledged | resolved
    acknowledged_by: Mapped[str | None] = mapped_column(String(160))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_escalation_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)  # last new information from the patient

    patient: Mapped[Patient] = relationship()
    events: Mapped[list[AlertEvent]] = relationship(
        back_populates="alert", order_by="AlertEvent.at", cascade="all, delete-orphan"
    )


class AlertEvent(Base):
    """Audit log: who was notified, when, how, and what they did."""

    __tablename__ = "alert_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    type: Mapped[str] = mapped_column(String(20))  # created | notified | escalated | acknowledged | action | resolved
    actor: Mapped[str | None] = mapped_column(String(160))
    detail: Mapped[str | None] = mapped_column(Text)

    alert: Mapped[Alert] = relationship(back_populates="events")
