from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


class Vitals(BaseModel):
    sbp: float | None = Field(None, ge=40, le=260)
    dbp: float | None = Field(None, ge=20, le=180)
    heart_rate: float | None = Field(None, ge=20, le=260)
    resp_rate: float | None = Field(None, ge=5, le=120)
    temperature: float | None = Field(None, ge=30, le=43)
    spo2: float | None = Field(None, ge=50, le=100)
    glucose: float | None = Field(None, ge=0.5, le=40)
    hemoglobin: float | None = Field(None, ge=30, le=200)
    proteinuria: int | None = Field(None, ge=0, le=4)
    weight: float | None = Field(None, ge=0.3, le=250)
    fetal_movements: float | None = Field(None, ge=0, le=200)
    meds_taken: bool | None = None
    symptoms: list[str] = []
    note: str | None = None


class ObservationIn(Vitals):
    source: str = "clinic"
    entered_by: str | None = None
    recorded_at: datetime | None = None

    @field_validator("source")
    @classmethod
    def _source(cls, v: str) -> str:
        if v not in {"self", "clinic", "lab", "device"}:
            raise ValueError("source must be self|clinic|lab|device")
        return v


class SelfReportIn(Vitals):
    patient_id: int | None = None
    phone: str | None = None


class PatientIn(BaseModel):
    kind: str = Field(pattern="^(mother|newborn)$")
    full_name: str = Field(min_length=3)
    birth_date: date | None = None
    phone: str | None = None
    district_id: int | None = None  # defaults to the responsible doctor's district
    address: str | None = None
    lat: float | None = None
    lon: float | None = None
    lmp_date: date | None = None
    parity: int | None = None
    mother_id: int | None = None
    birth_weight_g: int | None = None
    gestational_age_at_birth: int | None = None
    apgar5: int | None = None
    risk_factors: list[str] = []
    doctor_id: int | None = None  # owner may assign; a doctor always registers to themself
    consent: bool = False
    # newborn registered from the mother's visit: how she delivered (marks the mother as postpartum)
    delivery: str | None = Field(None, pattern="^(normal_delivery|cesarean|preterm_birth)$")


class PatientPatch(BaseModel):
    phone: str | None = None
    address: str | None = None
    risk_factors: list[str] | None = None
    outcome: str | None = None
    outcome_date: date | None = None
    active: bool | None = None
    lmp_date: date | None = None
    doctor_id: int | None = None  # owner only: move patient to another doctor


class LoginIn(BaseModel):
    phone: str = Field(min_length=7)
    password: str = Field(min_length=1, max_length=200)


class ActivateIn(BaseModel):
    phone: str = Field(min_length=7)
    code: str = Field(min_length=4, max_length=16)
    password: str = Field(min_length=8, max_length=200)


class SubscriptionAction(BaseModel):
    action: str = Field(pattern="^(grant_free|pay_month|cancel)$")
    months: int = Field(1, ge=1, le=12)


class StaffIn(BaseModel):
    full_name: str = Field(min_length=3)
    phone: str = Field(min_length=7)
    district_id: int
    position: str | None = "Shifokor"
    role: str = Field("doctor", pattern="^(doctor|owner)$")


class StaffPatch(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    district_id: int | None = None
    position: str | None = None
    active: bool | None = None


class AckIn(BaseModel):
    actor: str = "OvaBMU mutaxassisi"


class ActionIn(BaseModel):
    action: str
    actor: str = "OvaBMU mutaxassisi"
    note: str | None = None
