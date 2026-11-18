"""Authentication and access control for the website (doctors and the owner).

Roles
  doctor — sees and manages only patients where patient.doctor_id == doctor.id
  owner  — sees everything, manages doctors and subscriptions

Onboarding: the owner adds a doctor and gets a one-time activation code (DR-XXXXXX).
The doctor opens /activate.html, enters phone + code and chooses a password.
After that: phone + password. The Telegram bot is for women only.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict
from datetime import timedelta

from fastapi import Cookie, Depends, Header, HTTPException
from sqlalchemy import Select, select
from sqlalchemy.orm import Session as DbSession

from . import models
from .db import get_db
from .timeutil import utcnow

COOKIE = "pz_session"
SESSION_DAYS = 7
MAX_FAILS, FAIL_WINDOW = 5, 15 * 60  # 5 wrong passwords per 15 minutes per phone
ROLE_UZ = {"doctor": "Shifokor", "owner": "Administrator"}
_fails: dict[str, list[float]] = defaultdict(list)


# ---------------- passwords ----------------
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return f"pbkdf2${salt}${dk.hex()}"


def check_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("pbkdf2$"):
        return False
    _, salt, digest = stored.split("$", 2)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return hmac.compare_digest(dk.hex(), digest)


def new_invite_code(db: DbSession, prefix: str = "DR") -> str:
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I confusion
    while True:
        code = prefix + "".join(secrets.choice(alphabet) for _ in range(6))
        if not db.scalar(select(models.Staff.id).where(models.Staff.link_code == code)):
            return code


def find_staff_by_phone(db: DbSession, phone: str, include_inactive: bool = False) -> models.Staff | None:
    from .services.intake import normalize_phone

    key = normalize_phone(phone)
    if not key:
        return None
    q = select(models.Staff)
    if not include_inactive:
        q = q.where(models.Staff.active.is_not(False))
    for s in db.scalars(q):
        if normalize_phone(s.phone) == key:
            return s
    return None


def _throttled(key: str) -> bool:
    now = time.time()
    _fails[key] = [t for t in _fails[key] if now - t < FAIL_WINDOW]
    return len(_fails[key]) >= MAX_FAILS


def _new_session(db: DbSession, staff: models.Staff) -> models.Session:
    sess = models.Session(token=secrets.token_urlsafe(32), staff_id=staff.id,
                          expires_at=utcnow() + timedelta(days=SESSION_DAYS))
    staff.last_login_at = utcnow()
    db.add(sess)
    db.commit()
    return sess


def login(db: DbSession, phone: str, password: str) -> models.Session:
    from .services.intake import normalize_phone

    key = normalize_phone(phone) or phone
    if _throttled(key):
        raise HTTPException(429, "Juda ko'p urinish. 15 daqiqadan keyin qayta urinib ko'ring.")
    staff = find_staff_by_phone(db, phone)
    if not staff or not check_password(password, staff.password_hash):
        _fails[key].append(time.time())
        if staff and not staff.password_hash:
            raise HTTPException(400, "Hisob hali faollashtirilmagan. «Birinchi kirish» orqali taklif kodini kiriting.")
        raise HTTPException(400, "Telefon raqam yoki parol noto'g'ri")
    _fails.pop(key, None)
    return _new_session(db, staff)


def activate(db: DbSession, phone: str, code: str, password: str) -> models.Session:
    from .services.intake import normalize_phone

    key = "act:" + (normalize_phone(phone) or phone)
    if _throttled(key):
        raise HTTPException(429, "Juda ko'p urinish. 15 daqiqadan keyin qayta urinib ko'ring.")
    if len(password) < 8:
        raise HTTPException(400, "Parol kamida 8 belgidan iborat bo'lsin")
    staff = db.scalar(select(models.Staff).where(models.Staff.link_code == code.strip().upper(),
                                                 models.Staff.active.is_not(False)))
    if not staff or normalize_phone(staff.phone) != normalize_phone(phone):
        _fails[key].append(time.time())
        raise HTTPException(400, "Taklif kodi yoki telefon raqam mos kelmadi")
    staff.password_hash = hash_password(password)
    staff.link_code = None  # one-time
    return _new_session(db, staff)


# ---------------- request dependencies ----------------
def current_staff(
    db: DbSession = Depends(get_db),
    pz_session: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
) -> models.Staff:
    token = pz_session
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:]
    if not token:
        raise HTTPException(401, "Tizimga kiring")
    sess = db.get(models.Session, token)
    if not sess or sess.expires_at < utcnow():
        raise HTTPException(401, "Sessiya tugagan, qayta kiring")
    staff = db.get(models.Staff, sess.staff_id)
    if not staff or staff.active is False:
        raise HTTPException(401, "Hisob faol emas")
    return staff


def require_owner(staff: models.Staff = Depends(current_staff)) -> models.Staff:
    if staff.role != "owner":
        raise HTTPException(403, "Faqat administrator uchun")
    return staff


# ---------------- scoping ----------------
def scope_patients(stmt: Select, staff: models.Staff) -> Select:
    """Restrict a Patient query to what this staff member may see."""
    if staff.role == "owner":
        return stmt
    return stmt.where(models.Patient.doctor_id == staff.id)


def can_access(staff: models.Staff, patient: models.Patient) -> bool:
    return staff.role == "owner" or patient.doctor_id == staff.id


def get_patient_for(db: DbSession, staff: models.Staff, pid: int) -> models.Patient:
    p = db.get(models.Patient, pid)
    if not p or not can_access(staff, p):
        raise HTTPException(404, "Bemor topilmadi")  # 404, not 403: don't reveal other doctors' patients
    return p


def staff_public(s: models.Staff) -> dict:
    return {"id": s.id, "full_name": s.full_name, "role": s.role, "role_uz": ROLE_UZ.get(s.role, s.role),
            "position": s.position, "district_id": s.district_id,
            "district": s.district.name if s.district else None, "phone": s.phone,
            "activated": bool(s.password_hash), "active": s.active is not False,
            "last_login_at": s.last_login_at.isoformat() if s.last_login_at else None}
