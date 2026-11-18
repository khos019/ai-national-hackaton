from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import models
from backend.app.db import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.services import alerts as alert_svc
from backend.app.timeutil import utcnow


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    d = models.District(name="Chilonzor", region="Toshkent", lat=41.27, lon=69.20)
    db.add(d)
    db.flush()
    db.add_all([
        models.Staff(full_name="Mutaxassis", role="specialist", district_id=d.id, link_code="CHI1"),
        models.Staff(full_name="Bosh shifokor", role="head", district_id=d.id, link_code="CHI2"),
        models.Staff(full_name="Viloyat", role="regional", link_code="REG1"),
    ])
    db.commit()
    db.close()
    with TestClient(app) as c:
        yield c


def register(client, **kw):
    body = {"kind": "mother", "full_name": "Test Ona", "birth_date": "1998-05-01", "phone": "+998 90 111 22 33",
            "district_id": 1, "lmp_date": str((utcnow() - timedelta(weeks=30)).date()), **kw}
    r = client.post("/api/patients", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_self_report_danger_sign_creates_alert_and_advice(client):
    p = register(client)
    assert p["zone"] == "green"
    r = client.post("/api/self-report", json={"phone": "901112233", "symptoms": ["vaginal_bleeding"]})
    assert r.status_code == 201
    out = r.json()
    assert out["zone"] == "red"
    assert out["advice"]["level"] == "red" and "103" in out["advice"]["text"]

    alerts = client.get("/api/alerts?status=active").json()
    assert len(alerts) == 1 and alerts[0]["kind"] == "danger_sign" and alerts[0]["zone"] == "red"


def test_self_reported_high_bp_requires_verification(client):
    register(client)
    client.post("/api/self-report", json={"phone": "+998901112233", "sbp": 168, "dbp": 112})
    alerts = client.get("/api/alerts?status=active").json()
    assert alerts[0]["kind"] == "verify_self_report"


def test_escalation_and_acknowledgement(client):
    p = register(client)
    client.post(f"/api/patients/{p['id']}/observations", json={"sbp": 170, "dbp": 115, "proteinuria": 3})
    alert = client.get("/api/alerts?status=active").json()[0]
    assert alert["level"] == 0

    db = SessionLocal()
    alert_svc.run_escalations(db, now=utcnow() + timedelta(seconds=61))
    db.commit()
    db.close()
    a = client.get(f"/api/alerts/{alert['id']}").json()
    assert a["level"] == 1
    assert any(e["type"] == "escalated" for e in a["events"])

    r = client.post(f"/api/alerts/{alert['id']}/action", json={"action": "referred", "actor": "Dr. Test"})
    assert r.json()["status"] == "resolved"
    assert r.json()["acknowledged_by"] == "Dr. Test"


def test_no_duplicate_alerts_for_same_problem(client):
    p = register(client)
    client.post(f"/api/patients/{p['id']}/observations", json={"sbp": 145, "dbp": 92})
    client.post(f"/api/patients/{p['id']}/observations", json={"sbp": 147, "dbp": 93})
    active = client.get("/api/alerts?status=active").json()
    assert len(active) == 1


def test_dashboard_and_export(client):
    p = register(client)
    client.post(f"/api/patients/{p['id']}/observations", json={"sbp": 120, "dbp": 80, "hemoglobin": 95})
    d = client.get("/api/dashboard").json()
    assert d["counts"]["mother"]["yellow"] == 1
    csv = client.get("/api/export/ml-dataset.csv").text
    assert csv.splitlines()[0].startswith("patient_id,kind")
    assert "Test Ona" not in csv  # pseudonymised


def test_unknown_phone_self_report_404(client):
    r = client.post("/api/self-report", json={"phone": "+998000000000", "symptoms": []})
    assert r.status_code == 404
