"""Telegram bot — for WOMEN only (doctors use the website).

  /start -> share phone contact -> matched to the registry record her doctor created
         -> 7-day Premium trial starts automatically

  Free (always — safety first):  📝 Xavf belgilari, 🩺 Qon bosimi, 👶 Homila harakati, 🌡 Harorat, ⚖️ Vazn,
                                 🩸 Qand (only with diabetes), 💊 Temir/foliy kislota
  Premium (monthly subscription): 🤖 AI yordamchi — just write in your own words; the assistant extracts
                                 the data for your doctor and answers with general health information;
                                 📊 Haftalik hisobot
  ⭐ Obuna — status and payment (Click / Payme; demo payment in the prototype)

Even without Premium, free text is scanned for danger signs: an emergency is never behind a paywall.
"""
from __future__ import annotations

import asyncio
import logging
import re
import secrets
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select

from .. import models
from ..db import SessionLocal
from ..rules.engine import get_rules
from ..timeutil import utcnow
from . import ai_assistant
from . import subscriptions as subs
from .intake import add_observation, advice_for, find_patients_by_phone
from .notify import tg_call

log = logging.getLogger("perizone.bot")
ICON = {"red": "🔴", "yellow": "🟡", "green": "🟢"}
ZONE_UZ = {"red": "Qizil", "yellow": "Sariq", "green": "Yashil"}

BTN_REPORT = "📝 Xavf belgilari"
BTN_BP = "🩺 Qon bosimi"
BTN_KICKS = "👶 Homila harakati"
BTN_TEMP = "🌡 Harorat"
BTN_GLU = "🩸 Qand (glyukoza)"
BTN_WEIGHT = "⚖️ Vazn"
BTN_MEDS = "💊 Temir / foliy kislota"
BTN_AI = "🤖 AI yordamchi"
BTN_WEEKLY = "📊 Haftalik hisobot"
BTN_SUB = "⭐ Obuna"
BTN_SWITCH = "🔄 Boshqa bemor"

VALUE_BUTTONS = {  # button -> (field, prompt, (min, max))
    BTN_TEMP: ("temperature", "Haroratni kiriting, masalan: <code>36.8</code>", (30, 43)),
    BTN_GLU: ("glucose", "Och qoringa qanddagi glyukozani kiriting (mmol/L), masalan: <code>5.2</code>", (1, 35)),
    BTN_WEIGHT: ("weight", "Vaznni kiriting (kg), masalan: <code>64.5</code>", (0.5, 200)),
    BTN_KICKS: ("fetal_movements",
                "<b>«10 gacha sanash» usuli</b>\n"
                "Ovqatdan keyin chap yoningizga yotib, homila harakatlarini sanang. "
                "2 soat ichida <b>necha marta</b> harakatlandi? Raqam yuboring, masalan: <code>12</code>\n\n"
                "⚠️ Harakat umuman sezilmasa — kutmang, darhol 103 ga qo'ng'iroq qiling.", (0, 200)),
}
CONTACT_KB = {"keyboard": [[{"text": "📱 Telefon raqamni yuborish", "request_contact": True}]],
              "resize_keyboard": True, "one_time_keyboard": True}


@dataclass
class ChatState:
    patient_id: int | None = None
    awaiting: str | None = None
    symptoms: set[str] = field(default_factory=set)


STATE: dict[int, ChatState] = {}


def send(chat_id: int, text: str, kb: dict | None = None) -> None:
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if kb:
        payload["reply_markup"] = kb
    tg_call("sendMessage", payload)


def _patients_for_chat(db, chat_id: int) -> list[models.Patient]:
    return list(db.scalars(select(models.Patient).where(models.Patient.telegram_chat_id == chat_id,
                                                        models.Patient.active.is_(True))))


def _current_patient(db, chat_id: int) -> models.Patient | None:
    st = STATE.setdefault(chat_id, ChatState())
    pats = _patients_for_chat(db, chat_id)
    if st.patient_id and any(p.id == st.patient_id for p in pats):
        return db.get(models.Patient, st.patient_id)
    if pats:
        st.patient_id = pats[0].id
        return pats[0]
    return None


def _who(p: models.Patient) -> str:
    return ("🤰 " if p.kind == "mother" else "👶 ") + p.full_name


def _account_id(db, chat_id: int) -> int | None:
    """Subscription belongs to the mother's record (her baby shares it)."""
    pats = _patients_for_chat(db, chat_id)
    mother = next((p for p in pats if p.kind == "mother"), pats[0] if pats else None)
    return mother.id if mother else None


def patient_kb(db, chat_id: int, patient: models.Patient | None) -> dict:
    """Menu adapted to the patient: newborns never see BP/glucose; glucose only with (G)DM; kicks from 28 weeks."""
    from ..serializers import self_report_features

    f = self_report_features(patient) if patient else {"bp": True, "temperature": True, "weight": True}
    rows = [[{"text": BTN_REPORT}, {"text": BTN_AI}]]
    row = [{"text": b} for b, k in ((BTN_BP, "bp"), (BTN_KICKS, "fetal_movements")) if f.get(k)]
    if row:
        rows.append(row)
    rows.append([{"text": BTN_TEMP}, {"text": BTN_WEIGHT}] + ([{"text": BTN_GLU}] if f.get("glucose") else []))
    rows.append(([{"text": BTN_MEDS}] if f.get("meds") else []) + [{"text": BTN_WEEKLY}])
    rows.append([{"text": BTN_SUB}] + ([{"text": BTN_SWITCH}] if len(_patients_for_chat(db, chat_id)) > 1 else []))
    return {"keyboard": rows, "resize_keyboard": True}


def symptom_keyboard(kind: str, selected: set[str]) -> dict:
    rows = [[{"text": f"{'✅' if code in selected else '▫️'} {spec['label']}", "callback_data": f"sym:{code}"}]
            for code, spec in get_rules(kind).symptoms.items()]
    rows.append([{"text": "👍 Hammasi yaxshi", "callback_data": "sym_none"},
                 {"text": "📤 Yuborish", "callback_data": "sym_send"}])
    return {"inline_keyboard": rows}


def _sub_text(db, chat_id: int) -> tuple[str, dict]:
    acc = _account_id(db, chat_id)
    s = subs.status(db, acc)
    price = f"{subs.PRICE:,}".replace(",", " ")
    if s["active"]:
        text = (f"⭐ <b>{s['plan_uz']}</b> — faol, yana <b>{s['days_left']} kun</b>.\n\n"
                "Sizda: 🤖 AI yordamchi, 📊 haftalik hisobot va eslatmalar.")
        kb = {"inline_keyboard": [[{"text": f"➕ 1 oyga uzaytirish — {price} so'm", "callback_data": "pay:1"}]]}
    else:
        text = ("<b>Bepul tarif</b> faol: xavf belgilari, bosim, homila harakati — shifokoringiz baribir "
                "darhol xabardor qilinadi. Bu har doim bepul. 💙\n\n"
                f"<b>Premium — {price} so'm / oy</b>\n"
                "🤖 AI yordamchi: o'z so'zlaringiz bilan yozing — ma'lumot shifokoringizga yetkaziladi va "
                "sog'lig'ingiz haqida tushunarli maslahat olasiz\n📊 Haftalik shaxsiy hisobot\n⏰ Eslatmalar")
        kb = {"inline_keyboard": [[{"text": f"💳 Click / Payme orqali to'lash — {price} so'm", "callback_data": "pay:1"}],
                                  [{"text": f"💳 3 oy — {subs.PRICE * 3:,} so'm".replace(",", " "), "callback_data": "pay:3"}]]}
    return text, kb


# ---------------- data submission ----------------
def _submit(db, chat_id: int, patient: models.Patient, data: dict, note: str | None = None):
    if note:
        data = {**data, "note": note}
    obs, assessment = add_observation(db, patient, data, source="self", entered_by=f"telegram:{chat_id}")
    db.commit()
    return advice_for(patient, obs, assessment.zone), assessment


def _send_advice(db, chat_id: int, patient: models.Patient, data: dict) -> None:
    adv, _ = _submit(db, chat_id, patient, data)
    text = f"{ICON[adv['level']]} <b>{adv['title']}</b>\n{adv['text']}"
    if adv["reasons"]:
        text += "\n\n" + "\n".join(f"• {r}" for r in adv["reasons"])
    send(chat_id, text, patient_kb(db, chat_id, patient))


def _context(patient: models.Patient) -> str:
    """Minimal, de-identified context for the AI (no name, no phone)."""
    if patient.kind == "mother":
        ga = (utcnow().date() - patient.lmp_date).days // 7 if patient.lmp_date else None
        base = f"homilador ayol, {ga} hafta" if ga else "homilador ayol"
    else:
        days = (utcnow().date() - patient.birth_date).days if patient.birth_date else None
        base = f"chaqaloq, {days} kunlik (onasi yozmoqda)" if days is not None else "chaqaloq (onasi yozmoqda)"
    return f"{base}; joriy zona: {ZONE_UZ.get(patient.zone, patient.zone)}"


def _history(db, patient_id: int) -> list[dict]:
    rows = db.scalars(select(models.AiMessage).where(models.AiMessage.patient_id == patient_id)
                      .order_by(models.AiMessage.created_at.desc()).limit(8)).all()
    return [{"role": r.role, "content": r.text} for r in reversed(rows)]


def handle_free_text(db, chat_id: int, patient: models.Patient, text: str) -> None:
    premium = subs.is_premium(db, _account_id(db, chat_id))
    if premium:
        tg_call("sendChatAction", {"chat_id": chat_id, "action": "typing"})
        result = ai_assistant.analyze(text, patient.kind, _context(patient), _history(db, patient.id))
    else:
        # Free tier: no AI conversation, but the danger-sign safety scan still runs.
        result = ai_assistant._rules_reply(ai_assistant.keyword_scan(text, patient.kind), patient.kind)

    db.add(models.AiMessage(patient_id=patient.id, role="user", text=text, extracted=result.data,
                            urgency=result.urgency, engine=result.engine))
    has_data = bool(result.data.get("symptoms")) or any(k != "symptoms" for k in result.data)
    zone_line = ""
    if has_data:
        adv, assessment = _submit(db, chat_id, patient, dict(result.data), note=f"AI: {result.doctor_summary}"[:500])
        if adv["level"] == "red" and "103" not in result.reply:
            result.reply = adv["text"] + "\n\n" + result.reply
        zone_line = f"\n\n{ICON[assessment.zone]} Holatingiz: <b>{ZONE_UZ[assessment.zone]}</b> zona · ma'lumot shifokoringizga yuborildi."
    db.add(models.AiMessage(patient_id=patient.id, role="assistant", text=result.reply, engine=result.engine))
    db.commit()

    footer = "" if premium else (
        "\n\n<i>🤖 AI yordamchi bilan erkin suhbat — Premium'da. «⭐ Obuna» tugmasini bosing.</i>")
    send(chat_id, result.reply + zone_line + footer + "\n\n<i>Bu umumiy ma'lumot, shifokor maslahatining o'rnini bosmaydi.</i>",
         patient_kb(db, chat_id, patient))


def weekly_report(db, patient: models.Patient) -> str:
    since = utcnow() - timedelta(days=7)
    obs = [o for o in patient.observations if o.recorded_at >= since]
    bp = [(o.sbp, o.dbp) for o in obs if o.sbp and o.dbp]
    kicks = [o.fetal_movements for o in obs if o.fetal_movements is not None]
    temps = [o.temperature for o in obs if o.temperature is not None]
    meds = [o.meds_taken for o in obs if o.meds_taken is not None]
    sym = sorted({s for o in obs for s in (o.symptoms or [])})
    labels = get_rules(patient.kind).symptoms
    lines = [f"📊 <b>Haftalik hisobot</b> — {_who(patient)}", f"Joriy holat: {ICON[patient.zone]} <b>{ZONE_UZ[patient.zone]}</b>",
             f"Yuborilgan ma'lumotlar: {len(obs)} marta"]
    if bp:
        lines.append(f"🩺 Bosim: o'rtacha {round(sum(b[0] for b in bp) / len(bp))}/{round(sum(b[1] for b in bp) / len(bp))}, "
                     f"eng yuqori {int(max(b[0] for b in bp))}/{int(max(b[1] for b in bp))}")
    if kicks:
        lines.append(f"👶 Homila harakati: o'rtacha {round(sum(kicks) / len(kicks))} marta / 2 soat")
    if temps:
        lines.append(f"🌡 Harorat: eng yuqori {max(temps)} °C")
    if meds:
        lines.append(f"💊 Temir/foliy: {sum(meds)} / {len(meds)} kun ichildi")
    lines.append("⚠️ Belgilar: " + (", ".join(labels[s]["label"] for s in sym if s in labels) if sym else "yo'q 👍"))
    lines.append("\nHar kuni holatingizni yuborishda davom eting. Shifokoringiz ma'lumotlaringizni ko'rib turadi. 💙")
    return "\n".join(lines)


# ---------------- message entry ----------------
def handle_message(db, msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    st = STATE.setdefault(chat_id, ChatState())

    if "contact" in msg:
        contact = msg["contact"]
        if contact.get("user_id") != msg.get("from", {}).get("id"):
            send(chat_id, "Iltimos, o'zingizning raqamingizni tugma orqali yuboring.", CONTACT_KB)
            return
        pats = find_patients_by_phone(db, contact.get("phone_number", ""))
        if not pats:
            send(chat_id, "Siz hali ro'yxatda yo'qsiz. Shifokoringiz yoki patronaj hamshirangiz sizni ro'yxatga "
                          "olgandan keyin qayta urinib ko'ring. 💙")
            return
        for p in pats:
            p.telegram_chat_id = chat_id
        mother = next((p for p in pats if p.kind == "mother"), pats[0])
        trial = subs.start_trial(db, mother)
        db.commit()
        st.patient_id = pats[0].id
        doctor = pats[0].doctor.full_name if pats[0].doctor else None
        text_out = (f"Rahmat! Siz ulandingiz: <b>{', '.join(_who(p) for p in pats)}</b>."
                    + (f"\n👩‍⚕️ Shifokoringiz: {doctor}" if doctor else "")
                    + "\n\nHar kuni holatingizni yuboring — xavfli belgi bo'lsa, shifokoringiz darhol xabardor qilinadi."
                    + (f"\n\n🎁 Sizga <b>{subs.TRIAL_DAYS} kunlik Premium</b> sovg'a: 🤖 AI yordamchiga o'z so'zlaringiz "
                       "bilan yozishingiz mumkin, masalan: <i>«boshim og'riyapti, bosimim 140/90»</i>." if trial else ""))
        send(chat_id, text_out, patient_kb(db, chat_id, pats[0]))
        return

    if text.startswith("/start") or text == "/help":
        p = _current_patient(db, chat_id)
        if p:
            send(chat_id, f"Hozirgi bemor: <b>{_who(p)}</b>\nTugmalardan foydalaning yoki shunchaki yozing 👇",
                 patient_kb(db, chat_id, p))
        else:
            send(chat_id, "Assalomu alaykum! 💙 Bu — <b>PeriZone</b>: homiladorlik va chaqaloq salomatligini "
                          "kuzatish boti.\n\nDavom etish uchun pastdagi tugma orqali telefon raqamingizni yuboring.",
                 CONTACT_KB)
        return

    patient = _current_patient(db, chat_id)
    if not patient:
        send(chat_id, "Davom etish uchun telefon raqamingizni yuboring 👇", CONTACT_KB)
        return

    if text == BTN_SWITCH:
        send(chat_id, "Kim uchun ma'lumot yuborasiz?", {"inline_keyboard": [
            [{"text": _who(p), "callback_data": f"pick:{p.id}"}] for p in _patients_for_chat(db, chat_id)]})
        return
    if text in (BTN_REPORT, "/holat"):
        st.symptoms, st.awaiting = set(), None
        send(chat_id, f"<b>{_who(patient)}</b>: hozir quyidagilardan birortasi bormi? Belgilang va «Yuborish»ni "
                      "bosing.\n🔴 belgilardan biri bo'lsa — shifokoringizga darhol xabar boradi.",
             symptom_keyboard(patient.kind, st.symptoms))
        return
    if text == BTN_MEDS:
        send(chat_id, "Bugun temir / foliy kislota preparatini ichdingizmi?",
             {"inline_keyboard": [[{"text": "✅ Ha, ichdim", "callback_data": "meds:1"},
                                   {"text": "❌ Yo'q", "callback_data": "meds:0"}]]})
        return
    if text == BTN_BP:
        st.awaiting = "bp"
        send(chat_id, "Qon bosimini kiriting, masalan: <code>120/80</code>\n<i>5 daqiqa dam olib, o'tirgan holda o'lchang.</i>")
        return
    if text in VALUE_BUTTONS:
        st.awaiting, prompt, _ = VALUE_BUTTONS[text]
        send(chat_id, prompt)
        return
    if text == BTN_SUB or text == "/obuna":
        t, kb = _sub_text(db, chat_id)
        send(chat_id, t, kb)
        return
    if text == BTN_AI:
        st.awaiting = None
        premium = subs.is_premium(db, _account_id(db, chat_id))
        send(chat_id, "🤖 <b>AI yordamchi</b>\nO'z so'zlaringiz bilan yozing — nima bezovta qilyapti, qanday o'lchov "
                      "natijasi bor yoki qanday savolingiz bor. Masalan:\n<i>«Kecha kechqurundan beri boshim og'riyapti, "
                      "bosimim 145/95»</i>\n<i>«Homiladorlikda nima yeyish foydali?»</i>\n\n"
                      "Ma'lumotlaringiz shifokoringizga yetkaziladi."
                      + ("" if premium else "\n\n⭐ Bu Premium imkoniyat — «⭐ Obuna» orqali yoqing. "
                                            "Xavfli belgilarni yozsangiz, baribir shifokoringiz xabardor qilinadi."))
        return
    if text == BTN_WEEKLY:
        if not subs.is_premium(db, _account_id(db, chat_id)):
            send(chat_id, "📊 Haftalik shaxsiy hisobot — Premium imkoniyat. «⭐ Obuna» tugmasini bosing.")
            return
        send(chat_id, weekly_report(db, patient), patient_kb(db, chat_id, patient))
        return

    if st.awaiting == "bp":
        m = re.match(r"^\s*(\d{2,3})\s*[/\\\- ]\s*(\d{2,3})\s*$", text)
        if not m or not (60 <= int(m.group(1)) <= 260 and 30 <= int(m.group(2)) <= 180):
            send(chat_id, "Format: <code>120/80</code>. Qaytadan kiriting.")
            return
        st.awaiting = None
        _send_advice(db, chat_id, patient, {"sbp": float(m.group(1)), "dbp": float(m.group(2))})
        return
    limits = {key: lim for key, _, lim in VALUE_BUTTONS.values()}
    if st.awaiting in limits:
        try:
            value = float(text.replace(",", ".").strip())
        except ValueError:
            value = None
        lo, hi = limits[st.awaiting]
        if value is None or not lo <= value <= hi:
            send(chat_id, "Raqamni to'g'ri kiriting (masalan 36.8).")
            return
        field_name, st.awaiting = st.awaiting, None
        _send_advice(db, chat_id, patient, {field_name: value})
        return

    if text:
        handle_free_text(db, chat_id, patient, text)


def handle_callback(db, cb: dict) -> None:
    chat_id = cb["message"]["chat"]["id"]
    msg_id = cb["message"]["message_id"]
    data = cb.get("data", "")
    st = STATE.setdefault(chat_id, ChatState())

    def answer(text: str = "") -> None:
        tg_call("answerCallbackQuery", {"callback_query_id": cb["id"], "text": text})

    def clear_buttons() -> None:
        tg_call("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": msg_id, "reply_markup": {"inline_keyboard": []}})

    if data.startswith("pick:"):
        st.patient_id = int(data.split(":")[1])
        answer()
        p = _current_patient(db, chat_id)  # re-checks the chosen id belongs to this chat
        if p:
            st.symptoms, st.awaiting = set(), None
            send(chat_id, f"Tanlandi: <b>{_who(p)}</b>", patient_kb(db, chat_id, p))
        return
    patient = _current_patient(db, chat_id)
    if not patient:
        answer("Avval ro'yxatdan o'ting")
        return
    if data.startswith("pay:"):
        # PROTOTYPE: demo payment. Production: Telegram Payments (sendInvoice) with a Click or Payme
        # provider token, activating the subscription on successful_payment.
        months = int(data.split(":")[1])
        acc = db.get(models.Patient, _account_id(db, chat_id))
        sub = subs.pay_month(db, acc, provider="demo", payment_ref="demo-" + secrets.token_hex(4), months=months)
        db.commit()
        answer("To'lov qabul qilindi")
        clear_buttons()
        send(chat_id, f"✅ To'lov qabul qilindi (demo). Premium <b>{sub.expires_at:%d.%m.%Y}</b> gacha faol.\n"
                      "Endi 🤖 AI yordamchiga yozishingiz mumkin. Rahmat! 💙", patient_kb(db, chat_id, patient))
        return
    if data.startswith("sym:"):
        st.symptoms.symmetric_difference_update({data[4:]})
        tg_call("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": msg_id,
                                           "reply_markup": symptom_keyboard(patient.kind, st.symptoms)})
        answer()
        return
    if data.startswith("meds:"):
        clear_buttons()
        answer("Saqlandi")
        _send_advice(db, chat_id, patient, {"meds_taken": data == "meds:1"})
        return
    if data in ("sym_none", "sym_send"):
        symptoms = [] if data == "sym_none" else sorted(st.symptoms)
        st.symptoms = set()
        clear_buttons()
        answer("Yuborildi")
        _send_advice(db, chat_id, patient, {"symptoms": symptoms})


def handle_update(update: dict) -> None:
    db = SessionLocal()
    try:
        if "message" in update:
            handle_message(db, update["message"])
        elif "callback_query" in update:
            handle_callback(db, update["callback_query"])
    except Exception:
        log.exception("bot update failed")
        db.rollback()
    finally:
        db.close()


async def run_polling(stop: asyncio.Event) -> None:
    log.info("Telegram bot polling started")
    offset = 0
    while not stop.is_set():
        res = await asyncio.to_thread(tg_call, "getUpdates", {"offset": offset, "timeout": 25}, 35.0)
        if not res or not res.get("ok"):
            await asyncio.sleep(3)
            continue
        for upd in res["result"]:
            offset = upd["update_id"] + 1
            await asyncio.to_thread(handle_update, upd)
