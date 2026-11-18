from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import models
from backend.app.auth import hash_password
from backend.app.db import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.services import alerts as alert_svc
from backend.app.timeutil import utcnow

OWNER, DOC_A, DOC_B = "+998900000001", "+998900000002", "+998900000003"
PW = "testpass123"


@pytest.fixture()
def db_setup():
    from backend.app import auth
    auth._fails.clear()  # login throttle is in-memory; reset between tests
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    d = models.District(name="Chilonzor", region="Toshkent", lat=41.27, lon=69.20)
    db.add(d)
    db.flush()
    db.add_all([
        models.Staff(full_name="Admin", role="owner", phone=OWNER, password_hash=hash_password(PW)),
        models.Staff(full_name="Doktor A", role="doctor", district_id=d.id, phone=DOC_A, password_hash=hash_password(PW)),
        models.Staff(full_name="Doktor B", role="doctor", district_id=d.id, phone=DOC_B, password_hash=hash_password(PW)),
    ])
    db.commit()
    db.close()


def login(phone: str) -> TestClient:
    c = TestClient(app)
    c.__enter__()
    r = c.post("/api/auth/login", json={"phone": phone, "password": PW})
    assert r.status_code == 200, r.text
    return c


def register(c, **kw):
    body = {"kind": "mother", "full_name": "Test Ona", "birth_date": "1998-05-01", "phone": "+998 90 111 22 33",
            "lmp_date": str((utcnow() - timedelta(weeks=30)).date()), "consent": True,
            "initial": {"sbp": 112, "dbp": 72, "hemoglobin": 120, "weight": 64, "temperature": 36.6}, **kw}
    r = c.post("/api/patients", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_requires_login(db_setup):
    with TestClient(app) as c:
        assert c.get("/api/patients").status_code == 401
        assert c.get("/api/meta").status_code == 200  # public catalogs


def test_wrong_password_rejected_then_throttled(db_setup):
    with TestClient(app) as c:
        for _ in range(5):
            assert c.post("/api/auth/login", json={"phone": "+998 90 000 00 03", "password": "nope"}).status_code == 400
        assert c.post("/api/auth/login", json={"phone": DOC_B, "password": PW}).status_code == 429


def test_activation_with_one_time_code(db_setup):
    owner = login(OWNER)
    r = owner.post("/api/staff", json={"full_name": "Yangi Doktor", "phone": "+998900000009", "district_id": 1})
    code = r.json()["link_code"]
    assert r.json()["activation_path"] == f"/activate.html?code={code}" and not r.json()["activated"]
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"phone": "+998900000009", "password": "whatever1"}).status_code == 400
        assert c.post("/api/auth/activate", json={"phone": "+998900000008", "code": code, "password": "secret123"}).status_code == 400
        assert c.post("/api/auth/activate", json={"phone": "+998900000009", "code": code, "password": "secret123"}).status_code == 200
        assert c.get("/api/me").json()["full_name"] == "Yangi Doktor"
    with TestClient(app) as c2:  # code is one-time
        assert c2.post("/api/auth/activate", json={"phone": "+998900000009", "code": code, "password": "other1234"}).status_code == 400
        assert c2.post("/api/auth/login", json={"phone": "+998900000009", "password": "secret123"}).status_code == 200


def test_doctor_sees_only_own_patients(db_setup):
    a, b, owner = login(DOC_A), login(DOC_B), login(OWNER)
    p = register(a)
    assert p["doctor"] == "Doktor A"
    assert [x["id"] for x in a.get("/api/patients").json()] == [p["id"]]
    assert b.get("/api/patients").json() == []
    assert b.get(f"/api/patients/{p['id']}").status_code == 404   # not even its existence is revealed
    assert b.post(f"/api/patients/{p['id']}/observations", json={"sbp": 120}).status_code == 404
    assert len(owner.get("/api/patients").json()) == 1


def test_consent_and_duplicate_phone(db_setup):
    a = login(DOC_A)
    r = a.post("/api/patients", json={"kind": "mother", "full_name": "Rozisiz", "phone": "+998901112299", "consent": False})
    assert r.status_code == 400
    register(a)
    r = a.post("/api/patients", json={"kind": "mother", "full_name": "Dublikat", "phone": "901112233", "consent": True,
                                      "initial": {"sbp": 110, "dbp": 70, "hemoglobin": 120, "weight": 60, "temperature": 36.6}})
    assert r.status_code == 409


def test_alert_goes_to_own_doctor_then_owner(db_setup):
    a, b = login(DOC_A), login(DOC_B)
    p = register(a)
    a.post(f"/api/patients/{p['id']}/observations", json={"sbp": 170, "dbp": 115, "proteinuria": 3})
    alert = a.get("/api/alerts?status=active").json()[0]
    assert b.get("/api/alerts?status=active").json() == []
    ev = a.get(f"/api/alerts/{alert['id']}").json()["events"]
    assert [e["actor"] for e in ev if e["type"] == "notified"] == ["Doktor A"]

    db = SessionLocal()
    alert_svc.run_escalations(db, now=utcnow() + timedelta(seconds=61))
    db.commit()
    db.close()
    ev = a.get(f"/api/alerts/{alert['id']}").json()["events"]
    assert "Admin" in [e["actor"] for e in ev if e["type"] == "notified"]

    r = a.post(f"/api/alerts/{alert['id']}/action", json={"action": "referred"})
    assert r.json()["status"] == "resolved" and r.json()["acknowledged_by"] == "Doktor A"


def test_self_report_public_and_advice(db_setup):
    a = login(DOC_A)
    register(a)
    with TestClient(app) as anon:
        lk = anon.get("/api/self-report/lookup", params={"phone": "901112233"}).json()
        assert lk["display_name"] == "Test O."  # masked
        out = anon.post("/api/self-report", json={"phone": "901112233", "symptoms": ["vaginal_bleeding"]}).json()
        assert out["zone"] == "red" and "103" in out["advice"]["text"]
    assert a.get("/api/alerts?status=active").json()[0]["kind"] == "danger_sign"


def test_owner_manages_doctors_and_transfers_patient(db_setup):
    a, owner = login(DOC_A), login(OWNER)
    assert a.get("/api/staff").status_code == 403
    r = owner.post("/api/staff", json={"full_name": "Yangi Doktor", "phone": "+998900000009", "district_id": 1})
    assert r.status_code == 201 and r.json()["link_code"].startswith("DR")
    p = register(a)
    assert a.patch(f"/api/patients/{p['id']}", json={"doctor_id": 3}).status_code == 403
    assert owner.patch(f"/api/patients/{p['id']}", json={"doctor_id": 3}).json()["doctor"] == "Doktor B"
    assert a.get(f"/api/patients/{p['id']}").status_code == 404
    # deactivated doctor is logged out of an existing session and can't log in again
    b = login(DOC_B)
    assert b.get("/api/me").status_code == 200
    owner.patch("/api/staff/3", json={"active": False})
    assert b.get("/api/me").status_code == 401
    assert TestClient(app).post("/api/auth/login", json={"phone": DOC_B, "password": PW}).status_code == 400


def test_dashboard_scoped(db_setup):
    a, owner = login(DOC_A), login(OWNER)
    p = register(a)
    a.post(f"/api/patients/{p['id']}/observations", json={"hemoglobin": 95})
    assert a.get("/api/dashboard").json()["counts"]["mother"]["yellow"] == 1
    assert "by_doctor" not in a.get("/api/dashboard").json()
    d = owner.get("/api/dashboard").json()
    assert d["by_doctor"][0]["patients"] in (0, 1)
    csv = owner.get("/api/export/ml-dataset.csv").text
    assert "Test Ona" not in csv and a.get("/api/export/ml-dataset.csv").status_code == 403


def test_subscriptions_owner_only_and_summary(db_setup):
    a, owner = login(DOC_A), login(OWNER)
    p = register(a)
    assert a.post(f"/api/patients/{p['id']}/subscription", json={"action": "grant_free"}).status_code == 403
    st = owner.post(f"/api/patients/{p['id']}/subscription", json={"action": "pay_month", "months": 2}).json()
    assert st["active"] and st["plan"] == "monthly" and st["days_left"] >= 59
    ov = owner.get("/api/subscriptions").json()
    assert ov["summary"]["by_plan"]["monthly"] == 1 and ov["summary"]["mrr"] == ov["summary"]["price"]
    assert a.get(f"/api/patients/{p['id']}").json()["subscription"]["active"]
    owner.post(f"/api/patients/{p['id']}/subscription", json={"action": "cancel"})
    assert not a.get(f"/api/patients/{p['id']}").json()["subscription"]["active"]


def test_newborn_registered_separately_and_linked_to_mother(db_setup):
    a, b = login(DOC_A), login(DOC_B)
    mom = register(a, risk_factors=["gestational_diabetes"])
    r = a.post("/api/patients", json={"kind": "newborn", "full_name": "Chaqaloq Test", "birth_date": str(utcnow().date()),
                                      "mother_id": mom["id"], "birth_weight_g": 3100, "gestational_age_at_birth": 39,
                                      "apgar5": 9, "consent": True, "delivery": "cesarean",
                                      "initial": {"weight": 3.1, "temperature": 36.8}})
    assert r.status_code == 201, r.text
    baby = a.get(f"/api/patients/{r.json()['id']}").json()
    assert baby["phone"] == mom["phone"] and baby["mother"]["id"] == mom["id"]
    assert "maternal_diabetes" in baby["risk_factors"]          # inherited -> hypoglycaemia risk
    m = a.get(f"/api/patients/{mom['id']}").json()
    assert [c["id"] for c in m["children"]] == [baby["id"]]
    assert m["outcome"] == "cesarean" and m["postpartum_days"] == 0
    assert m["self_report"]["fetal_movements"] is False          # no kick counting after delivery
    # another doctor cannot attach a baby to someone else's patient
    r = b.post("/api/patients", json={"kind": "newborn", "full_name": "Boshqa Chaqaloq", "mother_id": mom["id"], "consent": True})
    assert r.status_code == 400


def test_registration_requires_baseline_exam_and_sets_zone(db_setup):
    a = login(DOC_A)
    r = a.post("/api/patients", json={"kind": "mother", "full_name": "Ko'riksiz Ona", "phone": "+998901119999", "consent": True})
    assert r.status_code == 400 and "gemoglobin" in r.json()["detail"]
    p = register(a, phone="+998901118888", initial={"sbp": 165, "dbp": 112, "hemoglobin": 95, "weight": 70, "temperature": 36.7})
    assert p["zone"] == "red"                                    # zone from the first exam
    obs = a.get(f"/api/patients/{p['id']}").json()["observations"]
    assert len(obs) == 1 and obs[0]["source"] == "clinic" and obs[0]["hemoglobin"] == 95
    assert a.get("/api/alerts?status=active").json()[0]["patient_id"] == p["id"]
