"""Simulated Telegram conversations (no network): tg_call is replaced by a recorder. Bot is for women only."""
from datetime import timedelta

import pytest

from backend.app import models
from backend.app.db import Base, SessionLocal, engine
from backend.app.services import telegram_bot as bot
from backend.app.timeutil import utcnow

CHAT, USER = 555, 777


@pytest.fixture()
def sent(monkeypatch):
    calls = []
    rec = lambda method, payload, *a, **k: calls.append((method, payload)) or {"ok": True}  # noqa: E731
    monkeypatch.setattr(bot, "tg_call", rec)
    monkeypatch.setattr("backend.app.services.notify.tg_call", rec)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")  # tests use the rule-based engine, no network
    bot.STATE.clear()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    d = models.District(name="Yakkasaroy", region="Toshkent")
    db.add(d)
    db.flush()
    doc = models.Staff(full_name="Doktor Test", role="doctor", district_id=d.id, phone="+998900000002")
    db.add(doc)
    db.flush()
    mom = models.Patient(kind="mother", full_name="Test Ona", phone="+998901112233", district_id=d.id,
                         doctor_id=doc.id, lmp_date=(utcnow() - timedelta(weeks=32)).date())
    db.add(mom)
    db.flush()
    db.add(models.Patient(kind="newborn", full_name="Test Chaqaloq", phone="+998901112233", district_id=d.id,
                          doctor_id=doc.id, birth_weight_g=3300, gestational_age_at_birth=39, apgar5=9, mother_id=mom.id,
                          birth_date=utcnow().date() - timedelta(days=5)))
    db.commit()
    db.close()
    return calls


def msg(text=None, contact=None, chat=CHAT, user=USER):
    m = {"chat": {"id": chat}, "from": {"id": user}}
    if text is not None:
        m["text"] = text
    if contact:
        m["contact"] = contact
    bot.handle_update({"message": m})


def cb(data, chat=CHAT):
    bot.handle_update({"callback_query": {"id": "1", "data": data, "message": {"chat": {"id": chat}, "message_id": 9}}})


def join():
    msg(contact={"phone_number": "998901112233", "user_id": USER})


def last_buttons(calls):
    for m, p in reversed(calls):
        if m == "sendMessage" and "keyboard" in p.get("reply_markup", {}):
            return [b["text"] for row in p["reply_markup"]["keyboard"] for b in row]
    return []


def texts(calls):
    return [p.get("text", "") for m, p in calls if m == "sendMessage"]


def db_query(fn):
    db = SessionLocal()
    try:
        return fn(db)
    finally:
        db.close()


def test_join_starts_trial_and_shows_menu(sent):
    msg("/start")
    join()
    assert any("7 kunlik Premium" in t for t in texts(sent))
    b = last_buttons(sent)
    assert {bot.BTN_REPORT, bot.BTN_AI, bot.BTN_KICKS, bot.BTN_BP, bot.BTN_SUB, bot.BTN_SWITCH} <= set(b)
    assert bot.BTN_GLU not in b
    assert db_query(lambda db: db.query(models.Subscription).one().plan) == "trial"


def test_unknown_phone(sent):
    msg(contact={"phone_number": "998911111111", "user_id": 4343}, chat=4242, user=4343)
    assert any("ro'yxatda yo'qsiz" in t for t in texts(sent))


def test_newborn_menu(sent):
    join()
    baby = db_query(lambda db: db.query(models.Patient).filter_by(kind="newborn").one().id)
    cb(f"pick:{baby}")
    b = last_buttons(sent)
    assert bot.BTN_BP not in b and bot.BTN_KICKS not in b and bot.BTN_TEMP in b


def test_low_kicks_alerts_doctor(sent):
    join()
    msg(bot.BTN_KICKS)
    msg("4")
    assert any("Darhol tibbiy yordamga" in t for t in texts(sent))
    a = db_query(lambda db: db.query(models.Alert).one())
    assert a.zone == "red"


def test_ai_free_text_extracts_data_and_alerts(sent):
    join()  # trial -> premium
    msg("Kechadan beri boshim qattiq og'riyapti, ko'z oldim qorong'ilashyapti, bosimim 150/100")
    t = texts(sent)[-1]
    assert "103" in t and "Qizil" in t
    obs = db_query(lambda db: db.query(models.Observation).one())
    assert obs.sbp == 150 and {"severe_headache", "blurred_vision"} <= set(obs.symptoms) and obs.source == "self"
    msgs = db_query(lambda db: [(m.role, m.urgency) for m in db.query(models.AiMessage).order_by(models.AiMessage.id)])
    assert msgs[0] == ("user", "emergency") and msgs[1][0] == "assistant"
    assert db_query(lambda db: db.query(models.Alert).count()) >= 1


def test_general_question_saves_no_observation(sent):
    join()
    msg("Homiladorlikda nima yeyish foydali?")
    assert db_query(lambda db: db.query(models.Observation).count()) == 0
    assert db_query(lambda db: db.query(models.AiMessage).count()) == 2


def test_free_tier_still_catches_danger_signs(sent):
    join()
    db = SessionLocal()
    for s in db.query(models.Subscription).all():
        s.expires_at = utcnow() - timedelta(days=1)
    db.commit()
    db.close()
    msg("qon ketyapti")
    t = texts(sent)[-1]
    assert "103" in t and "Premium" in t
    assert db_query(lambda db: db.query(models.Alert).one().kind) == "danger_sign"


def test_weekly_report_requires_premium_and_payment_unlocks(sent):
    join()
    db = SessionLocal()
    for s in db.query(models.Subscription).all():
        s.expires_at = utcnow() - timedelta(days=1)
    db.commit()
    db.close()
    msg(bot.BTN_WEEKLY)
    assert "Premium imkoniyat" in texts(sent)[-1]
    msg(bot.BTN_SUB)
    cb("pay:1")
    assert any("To'lov qabul qilindi" in t for t in texts(sent))
    msg(bot.BTN_WEEKLY)
    assert "Haftalik hisobot" in texts(sent)[-1]


def test_meds_recorded(sent):
    join()
    msg(bot.BTN_MEDS)
    cb("meds:1")
    assert db_query(lambda db: db.query(models.Observation).one().meds_taken) is True
