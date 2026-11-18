"""Telegram bot (long polling, no extra dependencies).

For women (self-reporting):
  /start  -> share phone contact -> linked to registry record(s)
  "📝 Holatimni yuborish" -> danger-sign checklist (toggle buttons) -> submit
  "🩺 Qon bosimi" / "🌡 Harorat" / "🩸 Qand" / "⚖️ Vazn" -> type a value
  After every report she gets immediate advice (103 for danger signs).

For staff:
  /staff <CODE>  -> links the chat to a Staff record (code shown in dashboard "Xodimlar")
  Alert messages have buttons: acknowledge / called / home visit / referred / no risk.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import select

from .. import models
from ..db import SessionLocal
from ..rules.engine import get_rules
from . import alerts as alert_svc
from .intake import add_observation, advice_for, find_patients_by_phone
from .notify import tg_call

log = logging.getLogger("perizone.bot")
ICON = {"red": "🔴", "yellow": "🟡", "green": "🟢"}

BTN_REPORT = "📝 Holatimni yuborish"
BTN_BP = "🩺 Qon bosimi"
BTN_TEMP = "🌡 Harorat"
BTN_GLU = "🩸 Qand (glyukoza)"
BTN_WEIGHT = "⚖️ Vazn"
MAIN_KB = {"keyboard": [[{"text": BTN_REPORT}], [{"text": BTN_BP}, {"text": BTN_TEMP}],
                        [{"text": BTN_GLU}, {"text": BTN_WEIGHT}]], "resize_keyboard": True}
CONTACT_KB = {"keyboard": [[{"text": "📱 Telefon raqamni yuborish", "request_contact": True}]],
              "resize_keyboard": True, "one_time_keyboard": True}


@dataclass
class ChatState:
    patient_id: int | None = None
    awaiting: str | None = None  # bp | temperature | glucose | weight
    symptoms: set[str] = field(default_factory=set)


STATE: dict[int, ChatState] = {}


def send(chat_id: int, text: str, kb: dict | None = None) -> None:
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if kb:
        payload["reply_markup"] = kb
    tg_call("sendMessage", payload)


def symptom_keyboard(kind: str, selected: set[str]) -> dict:
    rows = []
    for code, spec in get_rules(kind).symptoms.items():
        mark = "✅" if code in selected else "▫️"
        rows.append([{"text": f"{mark} {spec['label']}", "callback_data": f"sym:{code}"}])
    rows.append([{"text": "👍 Hammasi yaxshi", "callback_data": "sym_none"},
                 {"text": "📤 Yuborish", "callback_data": "sym_send"}])
    return {"inline_keyboard": rows}


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


def _submit(db, chat_id: int, patient: models.Patient, data: dict) -> None:
    obs, assessment = add_observation(db, patient, data, source="self", entered_by=f"telegram:{chat_id}")
    db.commit()
    adv = advice_for(patient, obs, assessment.zone)
    text = f"{ICON[adv['level']]} <b>{adv['title']}</b>\n{adv['text']}"
    if adv["reasons"]:
        text += "\n\n" + "\n".join(f"• {r}" for r in adv["reasons"])
    send(chat_id, text, MAIN_KB)


def _choose_patient_kb(pats) -> dict:
    return {"inline_keyboard": [[{"text": ("🤰 " if p.kind == "mother" else "👶 ") + p.full_name,
                                  "callback_data": f"pick:{p.id}"}] for p in pats]}


# ---------------- message handlers ----------------
def handle_message(db, msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    st = STATE.setdefault(chat_id, ChatState())

    # Staff linking
    m = re.match(r"^/(?:start|staff)\s+(?:staff_)?([A-Za-z0-9]{4,16})$", text)
    if m:
        staff = db.scalar(select(models.Staff).where(models.Staff.link_code == m.group(1).upper()))
        if staff:
            staff.telegram_chat_id = chat_id
            db.commit()
            send(chat_id, f"✅ {staff.full_name}, siz xabarnomalarni shu chatda olasiz "
                          f"(rol: {staff.role}).")
            return

    if "contact" in msg:
        contact = msg["contact"]
        if contact.get("user_id") != msg.get("from", {}).get("id"):
            send(chat_id, "Iltimos, o'zingizning raqamingizni yuboring.", CONTACT_KB)
            return
        pats = find_patients_by_phone(db, contact.get("phone_number", ""))
        if not pats:
            send(chat_id, "Siz ro'yxatda topilmadingiz. Oilaviy poliklinikangizdagi patronaj hamshirasiga "
                          "murojaat qiling — ular sizni ro'yxatga olishadi.")
            return
        for p in pats:
            p.telegram_chat_id = chat_id
        db.commit()
        st.patient_id = pats[0].id
        names = ", ".join(p.full_name for p in pats)
        send(chat_id, f"Rahmat! Siz ulandingiz: <b>{names}</b>.\n\n"
                      "Har kuni o'z holatingizni yuboring. Xavfli belgi bo'lsa, mutaxassisingiz darhol "
                      "xabardor qilinadi.", MAIN_KB)
        return

    if text.startswith("/start") or text == "/help":
        if _patients_for_chat(db, chat_id):
            send(chat_id, "Quyidagi tugmalardan foydalaning 👇", MAIN_KB)
        else:
            send(chat_id, "Assalomu alaykum! Bu — perinatal monitoring boti.\n"
                          "Davom etish uchun telefon raqamingizni yuboring 👇", CONTACT_KB)
        return

    patient = _current_patient(db, chat_id)
    if not patient:
        send(chat_id, "Avval telefon raqamingizni yuboring 👇", CONTACT_KB)
        return

    if text in (BTN_REPORT, "/holat"):
        pats = _patients_for_chat(db, chat_id)
        if len(pats) > 1 and text == BTN_REPORT:
            send(chat_id, "Kim uchun ma'lumot yuborasiz?", _choose_patient_kb(pats))
            return
        st.symptoms = set()
        st.awaiting = None
        send(chat_id, f"<b>{patient.full_name}</b>: hozir quyidagilardan qaysi biri bor? Belgilang va "
                      "«Yuborish»ni bosing.", symptom_keyboard(patient.kind, st.symptoms))
        return

    prompts = {BTN_BP: ("bp", "Qon bosimini kiriting, masalan: <code>120/80</code>"),
               BTN_TEMP: ("temperature", "Haroratni kiriting, masalan: <code>36.8</code>"),
               BTN_GLU: ("glucose", "Qanddagi glyukozani kiriting (mmol/L), masalan: <code>5.2</code>"),
               BTN_WEIGHT: ("weight", "Vazningizni kiriting (kg), masalan: <code>64.5</code>")}
    if text in prompts:
        st.awaiting, prompt = prompts[text]
        send(chat_id, prompt)
        return

    if st.awaiting == "bp":
        m = re.match(r"^\s*(\d{2,3})\s*[/\\\- ]\s*(\d{2,3})\s*$", text)
        if not m or not (60 <= int(m.group(1)) <= 260 and 30 <= int(m.group(2)) <= 180):
            send(chat_id, "Format: <code>120/80</code>. Qaytadan kiriting.")
            return
        st.awaiting = None
        _submit(db, chat_id, patient, {"sbp": float(m.group(1)), "dbp": float(m.group(2))})
        return

    if st.awaiting in ("temperature", "glucose", "weight"):
        limits = {"temperature": (30, 43), "glucose": (1, 35), "weight": (0.5, 200)}
        try:
            value = float(text.replace(",", "."))
        except ValueError:
            value = None
        lo, hi = limits[st.awaiting]
        if value is None or not lo <= value <= hi:
            send(chat_id, "Raqamni to'g'ri kiriting (masalan 36.8).")
            return
        field_name, st.awaiting = st.awaiting, None
        _submit(db, chat_id, patient, {field_name: value})
        return

    send(chat_id, "Tugmalardan birini tanlang 👇", MAIN_KB)


# ---------------- callback handlers ----------------
def handle_callback(db, cb: dict) -> None:
    chat_id = cb["message"]["chat"]["id"]
    msg_id = cb["message"]["message_id"]
    data = cb.get("data", "")
    st = STATE.setdefault(chat_id, ChatState())

    def answer(text: str = "") -> None:
        tg_call("answerCallbackQuery", {"callback_query_id": cb["id"], "text": text})

    # Staff actions
    if data.startswith(("ack:", "act:")):
        staff = db.scalar(select(models.Staff).where(models.Staff.telegram_chat_id == chat_id))
        if not staff:
            answer("Siz xodim sifatida ulanmagansiz")
            return
        parts = data.split(":")
        alert = db.get(models.Alert, int(parts[1]))
        if not alert:
            answer("Topilmadi")
            return
        if parts[0] == "ack":
            alert_svc.acknowledge(db, alert, staff.full_name)
            note = "Qabul qilindi ✅"
        else:
            alert_svc.record_action(db, alert, parts[2], staff.full_name)
            note = alert_svc.ACTIONS.get(parts[2], parts[2])
        db.commit()
        answer(note)
        send(chat_id, f"#{alert.id} · {alert.patient.full_name}: {note} — {staff.full_name}")
        return

    patient = _current_patient(db, chat_id)
    if data.startswith("pick:"):
        st.patient_id = int(data.split(":")[1])
        answer()
        patient = _current_patient(db, chat_id)  # re-checks the chosen id belongs to this chat
        if not patient:
            return
        st.symptoms, st.awaiting = set(), None
        send(chat_id, f"<b>{patient.full_name}</b>: belgilarni tanlang va «Yuborish»ni bosing.",
             symptom_keyboard(patient.kind, st.symptoms))
        return
    if not patient:
        answer("Avval ro'yxatdan o'ting")
        return

    if data.startswith("sym:"):
        code = data[4:]
        st.symptoms.symmetric_difference_update({code})
        tg_call("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": msg_id,
                                           "reply_markup": symptom_keyboard(patient.kind, st.symptoms)})
        answer()
        return
    if data in ("sym_none", "sym_send"):
        symptoms = [] if data == "sym_none" else sorted(st.symptoms)
        st.symptoms = set()
        tg_call("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": msg_id, "reply_markup": {"inline_keyboard": []}})
        answer("Yuborildi")
        _submit(db, chat_id, patient, {"symptoms": symptoms})


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
