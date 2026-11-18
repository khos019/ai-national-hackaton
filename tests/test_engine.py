from datetime import datetime, timedelta

from backend.app.rules.engine import get_rules

NOW = datetime(2026, 11, 18, 12, 0)


def obs(days_ago=0, source="clinic", symptoms=None, **vals):
    return {"recorded_at": NOW - timedelta(days=days_ago), "source": source, "symptoms": symptoms or [], **vals}


M = {"kind": "mother", "age_years": 27, "risk_factors": []}
mother = get_rules("mother")
newborn = get_rules("newborn")


def test_normal_is_green():
    r = mother.evaluate(M, [obs(sbp=115, dbp=72, hemoglobin=122, temperature=36.6)], NOW)
    assert r.zone == "green" and r.findings == []


def test_severe_hypertension_is_red():
    r = mother.evaluate(M, [obs(sbp=165, dbp=100)], NOW)
    assert r.zone == "red"
    assert any(f.code == "param:sbp" and f.zone == "red" for f in r.findings)


def test_preeclampsia_combo():
    r = mother.evaluate(M, [obs(sbp=145, dbp=92, proteinuria=2)], NOW)
    assert r.zone == "red"
    assert any(f.code == "combo:preeclampsia_protein" for f in r.findings)


def test_hypertension_plus_headache_symptom_combo():
    r = mother.evaluate(M, [obs(sbp=142, dbp=88), obs(source="self", symptoms=["severe_headache"])], NOW)
    assert any(f.code == "combo:preeclampsia_symptoms" for f in r.findings)
    assert r.zone == "red"


def test_self_reported_danger_sign_is_red_and_marked_self():
    r = mother.evaluate(M, [obs(source="self", symptoms=["vaginal_bleeding"])], NOW)
    assert r.zone == "red"
    assert r.red_findings[0].self_reported


def test_old_values_expire():
    r = mother.evaluate(M, [obs(days_ago=30, sbp=170, dbp=112)], NOW)
    assert r.zone == "green"


def test_symptoms_expire_after_window():
    r = mother.evaluate(M, [obs(days_ago=5, source="self", symptoms=["vaginal_bleeding"])], NOW)
    assert r.zone == "green"


def test_risk_factor_floor():
    r = mother.evaluate({**M, "risk_factors": ["multiple_pregnancy"]}, [obs(sbp=110, dbp=70)], NOW)
    assert r.zone == "yellow"


def test_auto_age_risk_factor():
    r = mother.evaluate({**M, "age_years": 38}, [], NOW)
    assert r.zone == "yellow"
    assert any(f.code == "risk:age_over_35" for f in r.findings)


def test_rising_bp_trend_while_still_normal():
    series = [obs(days_ago=20, sbp=108), obs(days_ago=18, sbp=110), obs(days_ago=12, sbp=118),
              obs(days_ago=8, sbp=124), obs(days_ago=3, sbp=128), obs(days_ago=0, sbp=132)]
    r = mother.evaluate(M, series, NOW)
    assert any(f.code == "trend:sbp_rise" for f in r.findings)
    assert r.zone == "yellow"


def test_single_noisy_reading_does_not_trigger_trend():
    series = [obs(days_ago=14, sbp=112), obs(days_ago=10, sbp=104), obs(days_ago=6, sbp=113), obs(days_ago=0, sbp=119)]
    r = mother.evaluate(M, series, NOW)
    assert not any(f.code == "trend:sbp_rise" for f in r.findings)


def test_meows_aggregation_three_yellows_red():
    r = mother.evaluate(M, [obs(sbp=145, dbp=92, heart_rate=105)], NOW)
    assert r.zone == "red"
    assert any(f.category == "aggregation" for f in r.findings)


def test_newborn_auto_risk_and_danger_sign():
    nb = {"kind": "newborn", "birth_weight_g": 1400, "gestational_age_at_birth": 31, "apgar5": 8, "risk_factors": []}
    r = newborn.evaluate(nb, [], NOW)
    assert r.zone == "red"  # very low birth weight / very preterm floor
    healthy = {"kind": "newborn", "birth_weight_g": 3400, "gestational_age_at_birth": 39, "apgar5": 9, "risk_factors": []}
    r2 = newborn.evaluate(healthy, [obs(source="self", symptoms=["poor_feeding"], temperature=36.8)], NOW)
    assert r2.zone == "red"


def test_newborn_fast_breathing_red():
    healthy = {"kind": "newborn", "birth_weight_g": 3400, "gestational_age_at_birth": 39, "apgar5": 9}
    r = newborn.evaluate(healthy, [obs(resp_rate=64, temperature=36.9)], NOW)
    assert r.zone == "red"


def test_fetal_movements_count_to_ten():
    assert mother.evaluate(M, [obs(source="self", fetal_movements=12)], NOW).zone == "green"
    assert mother.evaluate(M, [obs(source="self", fetal_movements=8)], NOW).zone == "yellow"
    r = mother.evaluate(M, [obs(source="self", fetal_movements=3)], NOW)
    assert r.zone == "red" and r.red_findings[0].code == "param:fetal_movements"


def test_headache_plus_blurred_vision_is_red_danger_sign():
    r = mother.evaluate(M, [obs(source="self", symptoms=["severe_headache", "blurred_vision"])], NOW)
    assert r.zone == "red"
    combo = next(f for f in r.findings if f.code == "combo:severe_headache_vision")
    assert combo.category == "symptom" and combo.self_reported


def test_headache_alone_stays_yellow():
    assert mother.evaluate(M, [obs(source="self", symptoms=["severe_headache"])], NOW).zone == "yellow"
