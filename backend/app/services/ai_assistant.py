"""AI assistant for women in Telegram.

A woman writes freely ("boshim qattiq og'riyapti, bosimim 150/95") and the assistant:
  1. extracts structured data (danger signs, BP, temperature, kicks, weight...) -> saved as a
     self-reported Observation -> the normal rules engine decides the zone and alerts her doctor;
  2. writes a short, warm, general-information reply in Uzbek (never a diagnosis or a dosage);
  3. writes a one-line summary for the doctor.

Engine: Claude (Anthropic API) via structured outputs when ANTHROPIC_API_KEY is configured;
otherwise a rule-based Uzbek/Russian keyword analyser. The keyword safety scan ALWAYS runs too,
so a danger sign is never missed because of a model outage, a refusal or a parsing problem.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

log = logging.getLogger("perizone.ai")

AI_MODEL = os.getenv("AI_MODEL", "claude-opus-5-5")

MOTHER_SYMPTOMS = Literal[
    "vaginal_bleeding", "convulsions", "severe_abdominal_pain", "reduced_fetal_movement", "water_leaking",
    "breathing_difficulty", "severe_headache", "blurred_vision", "swelling_face_hands", "fever",
    "painful_urination", "persistent_vomiting", "low_mood",
]
NEWBORN_SYMPTOMS = Literal[
    "poor_feeding", "convulsions", "lethargy", "fast_breathing", "chest_indrawing", "blue_lips",
    "jaundice_early", "jaundice", "umbilical_redness", "vomiting", "diarrhea", "skin_pustules",
]


class Extraction(BaseModel):
    """What the model must return. All fields required; unknown values are null / empty."""

    reply: str = Field(description="Javob ayolga: o'zbek lotin, 2-5 gap, iliq, tushunarli.")
    symptoms: List[str] = Field(description="Faqat ruxsat etilgan kodlar")
    sbp: Optional[float] = Field(description="Sistolik bosim, mmHg")
    dbp: Optional[float] = Field(description="Diastolik bosim, mmHg")
    temperature: Optional[float] = Field(description="Harorat, °C")
    weight: Optional[float] = Field(description="Vazn, kg")
    fetal_movements: Optional[float] = Field(description="2 soatdagi homila harakati soni")
    glucose: Optional[float] = Field(description="Glyukoza, mmol/L")
    urgency: Literal["none", "routine", "urgent", "emergency"]
    doctor_summary: str = Field(description="Shifokor uchun 1 gaplik xulosa (o'zbek)")


@dataclass
class AiResult:
    reply: str
    data: dict = field(default_factory=dict)  # observation fields incl. symptoms
    urgency: str = "none"
    doctor_summary: str = ""
    engine: str = "rules"


SYSTEM = """Siz PeriZone tizimining homilador ayollar va yosh onalar uchun yordamchisisiz (Telegram).
Siz shifokor EMASSIZ: tashxis qo'ymaysiz, dori va dozani tavsiya qilmaysiz, shifokor ko'rigini almashtirmaysiz.
Vazifangiz:
1) Ayol yozganidan tibbiy ma'lumotni ajratib oling (faqat aniq aytilganini; taxmin qilmang).
   Belgilar uchun faqat ruxsat etilgan kodlardan foydalaning: {codes}.
2) Qisqa (2-5 gap), iliq, sodda o'zbek (lotin) tilida umumiy ma'lumot bering: nima uchun bu muhim,
   uyda nima qilish xavfsiz (dam olish, suv ichish, yonboshlab yotish kabi umumiy maslahatlar).
3) Xavf belgisi bo'lsa (qon ketishi, tutqanoq, kuchli qorin og'rig'i, homila harakati yo'qolishi, suv ketishi,
   nafas qisishi, kuchli bosh og'rig'i bilan ko'rish buzilishi, chaqaloq emmasligi/holsizligi/tez nafasi) —
   urgency="emergency" va javobning birinchi gapida: "Darhol 103 ga qo'ng'iroq qiling yoki tug'ruqxonaga boring."
4) Xavotirli, lekin shoshilinch bo'lmasa — urgency="urgent": shifokoringiz bog'lanishini ayting.
5) Savol umumiy bo'lsa (ovqatlanish, uyqu, mashqlar) — urgency="none", foydali umumiy javob bering.
Har doim ayolni o'z shifokori bilan maslahatlashishga undang. Tibbiy bo'lmagan mavzularda muloyimlik bilan rad eting."""


# ------------------------------------------------------------------ keyword safety net
KEYWORDS = {  # (regex, symptom code). Latin + Cyrillic Uzbek + common Russian.
    "mother": [
        (r"qon\s*ket|qonash|qon\s*kel|кровотеч|кровь|қон кет", "vaginal_bleeding"),
        (r"tutqanoq|talvasa|тутқаноқ|судорог|припад", "convulsions"),
        (r"qorin\w*\s*(qattiq|kuchli)?\s*og.?ri|qornim\s*(qattiq\s*)?og.?ri|боли?т? живот|қорин", "severe_abdominal_pain"),
        (r"(bola|homila|чақалоқ|ребен)\w*\s*(qimirla|harakat|тепк|шевел)\w*\s*(yo.?q|kam|sezilma|to.?xta|нет|перест)", "reduced_fetal_movement"),
        (r"suv\s*ket|qog.?onoq|воды отош|подтека", "water_leaking"),
        (r"nafas\s*(qis|ololma|yetish)|задыха|одышк", "breathing_difficulty"),
        (r"bosh\w*\s*(qattiq|kuchli|juda)?\s*og.?ri|boshim\s*og.?ri|голова\s*бол|болит голова|бош оғри", "severe_headache"),
        (r"ko.?z\w*\s*(old\w*\s*)?(qorong|xira|tinda|yaltira)|ko.?rish|в глазах|мушк", "blurred_vision"),
        (r"shish|отек|опух|шиш", "swelling_face_hands"),
        (r"isitma|titra|титроқ|температур|жар|лихорад", "fever"),
        (r"siy\w*\s*(da\s*)?(og.?ri|achish)|больно писать|жжение", "painful_urination"),
        (r"qus(ay|yap|ish)\w*\s*(to.?xtama|ko.?p)|рвот", "persistent_vomiting"),
        (r"tushkun|yig.?la|xavotir|depress|тревог|плач", "low_mood"),
    ],
    "newborn": [
        (r"emma(yap|di|y)|ko.?krak\s*olma|не сосет|не ест", "poor_feeding"),
        (r"tutqanoq|talvasa|судорог", "convulsions"),
        (r"holsiz|uyquchan|вял|сонлив", "lethargy"),
        (r"tez\s*nafas|часто дыш", "fast_breathing"),
        (r"ko.?kar|синеет|синие губы", "blue_lips"),
        (r"sarg.?ay|sariq|желт", "jaundice"),
        (r"kindik|пупок|пупоч", "umbilical_redness"),
        (r"qus(ay|di|yap)|рвот|срыг", "vomiting"),
        (r"ich\s*ket|понос|диаре", "diarrhea"),
    ],
}
RED = {"vaginal_bleeding", "convulsions", "severe_abdominal_pain", "reduced_fetal_movement", "water_leaking",
       "breathing_difficulty", "poor_feeding", "lethargy", "fast_breathing", "chest_indrawing", "blue_lips", "jaundice_early"}


def keyword_scan(text: str, kind: str) -> dict:
    t = text.lower()
    data: dict = {"symptoms": sorted({code for rx, code in KEYWORDS[kind] if re.search(rx, t)})}
    m = re.search(r"(\d{2,3})\s*[/\\]\s*(\d{2,3})", t)
    if m and 60 <= int(m.group(1)) <= 260 and 30 <= int(m.group(2)) <= 180:
        data["sbp"], data["dbp"] = float(m.group(1)), float(m.group(2))
    m = re.search(r"(3[4-9]|4[0-2])[.,](\d)", t)
    if m:
        data["temperature"] = float(f"{m.group(1)}.{m.group(2)}")
    m = re.search(r"(\d{1,3})\s*(marta|раз)", t)
    if m and kind == "mother" and re.search(r"qimirla|harakat|тепк|шевел", t):
        data["fetal_movements"] = float(m.group(1))
    m = re.search(r"(\d{2,3}(?:[.,]\d)?)\s*(kg|кг)", t)
    if m:
        data["weight"] = float(m.group(1).replace(",", "."))
    return data


def _rules_reply(data: dict, kind: str) -> AiResult:
    sy = set(data.get("symptoms", []))
    if sy & RED or ("severe_headache" in sy and "blurred_vision" in sy):
        reply = ("Darhol 103 ga qo'ng'iroq qiling yoki eng yaqin tug'ruqxonaga boring. "
                 "Siz yozgan belgilar xavfli bo'lishi mumkin. Shifokoringizga avtomatik xabar yuborildi.")
        urgency = "emergency"
    elif sy or data.get("sbp") or data.get("temperature"):
        reply = ("Rahmat, ma'lumotingiz shifokoringizga yetkazildi. Dam oling, suv iching va ahvolingizni kuzating. "
                 "Belgilar kuchaysa yoki yangi belgi paydo bo'lsa — darhol 103 ga qo'ng'iroq qiling.")
        urgency = "urgent" if sy else "routine"
    else:
        reply = ("Rahmat! Savolingizni shifokoringizga ham yetkazishim mumkin. Agar biror bezovtalik bo'lsa — "
                 "qaysi belgi borligini yozing (masalan: «boshim og'riyapti», «bosimim 140/90»).")
        urgency = "none"
    labels = ", ".join(sorted(sy)) or "belgilar yo'q"
    return AiResult(reply=reply, data=data, urgency=urgency, engine="rules",
                    doctor_summary=f"Ayol yozdi: {labels}" + (f"; QB {int(data['sbp'])}/{int(data['dbp'])}" if data.get("sbp") else ""))


# ------------------------------------------------------------------ Claude
def claude_enabled() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


def _claude(text: str, kind: str, context: str, history: list[dict]) -> AiResult | None:
    import anthropic

    codes = list((MOTHER_SYMPTOMS if kind == "mother" else NEWBORN_SYMPTOMS).__args__)
    client = anthropic.Anthropic(timeout=40.0, max_retries=1)
    messages = [*history[-8:], {"role": "user", "content": f"[Kontekst: {context}]\n\n{text}"}]
    try:
        resp = client.beta.messages.parse(
            model=AI_MODEL,
            max_tokens=2000,
            system=SYSTEM.format(codes=", ".join(codes)),
            messages=messages,
            output_format=Extraction,
            output_config={"effort": "low"},  # short chat turns: low effort keeps latency and cost down
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # on a safety-classifier refusal, re-run on a fallback model in the same call
        )
    except anthropic.RateLimitError:
        log.warning("Claude rate limited — using rules")
        return None
    except anthropic.APIStatusError as e:
        log.warning("Claude API error %s — using rules", e.status_code)
        return None
    except anthropic.APIConnectionError:
        log.warning("Claude unreachable — using rules")
        return None
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        return None
    out: Extraction = resp.parsed_output
    data = {"symptoms": [s for s in out.symptoms if s in codes]}
    for k in ("sbp", "dbp", "temperature", "weight", "fetal_movements", "glucose"):
        v = getattr(out, k)
        if v is not None:
            data[k] = float(v)
    return AiResult(reply=out.reply.strip(), data=data, urgency=out.urgency,
                    doctor_summary=out.doctor_summary.strip(), engine=resp.model)


def analyze(text: str, kind: str, context: str = "", history: list[dict] | None = None) -> AiResult:
    """Never raises. Keyword safety scan is merged into whatever the model returns."""
    safety = keyword_scan(text, kind)
    result = None
    if claude_enabled():
        try:
            result = _claude(text, kind, context, history or [])
        except Exception:  # pragma: no cover — any unexpected SDK/parse issue must not break the bot
            log.exception("AI assistant failed — using rules")
    if result is None:
        return _rules_reply(safety, kind)
    # merge: model data + anything the safety net caught that the model missed
    result.data["symptoms"] = sorted(set(result.data.get("symptoms", [])) | set(safety["symptoms"]))
    for k, v in safety.items():
        if k != "symptoms":
            result.data.setdefault(k, v)
    if set(result.data["symptoms"]) & RED and result.urgency != "emergency":
        result.urgency = "emergency"
        if "103" not in result.reply:
            result.reply = "Darhol 103 ga qo'ng'iroq qiling yoki tug'ruqxonaga boring. " + result.reply
    return result
