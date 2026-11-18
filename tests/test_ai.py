from backend.app.services import ai_assistant as ai


def test_keyword_scan_uzbek_latin_cyrillic_russian():
    d = ai.keyword_scan("boshim qattiq og'riyapti, bosimim 145/95, isitma 38,2", "mother")
    assert {"severe_headache", "fever"} <= set(d["symptoms"]) and d["sbp"] == 145 and d["temperature"] == 38.2
    assert "vaginal_bleeding" in ai.keyword_scan("қон кетяпти", "mother")["symptoms"]
    assert "vaginal_bleeding" in ai.keyword_scan("у меня кровотечение", "mother")["symptoms"]
    assert ai.keyword_scan("bola 5 marta qimirladi", "mother")["fetal_movements"] == 5


def test_newborn_keywords():
    assert {"poor_feeding", "jaundice"} <= set(ai.keyword_scan("chaqaloq emmayapti, terisi sarg'aygan", "newborn")["symptoms"])


def test_rules_engine_emergency_reply(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    r = ai.analyze("qon ketyapti", "mother")
    assert r.urgency == "emergency" and r.reply.startswith("Darhol 103") and r.engine == "rules"


def test_model_output_is_merged_with_safety_net(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(ai, "_claude", lambda *a, **k: ai.AiResult(reply="Dam oling.", data={"symptoms": []},
                                                                 urgency="none", engine="claude-opus-5-5"))
    r = ai.analyze("qon ketyapti", "mother")
    assert "vaginal_bleeding" in r.data["symptoms"] and r.urgency == "emergency" and "103" in r.reply


def test_claude_failure_falls_back_to_rules(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(ai, "_claude", lambda *a, **k: None)
    assert ai.analyze("boshim og'riyapti", "mother").engine == "rules"
