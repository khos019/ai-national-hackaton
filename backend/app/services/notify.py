"""Outgoing notifications.

Channels:
  * Telegram (primary) — if TELEGRAM_BOT_TOKEN is set and the staff member linked their chat
  * SMS (fallback)     — stub; plug in a local gateway (e.g. Eskiz.uz / Play Mobile) here
  * in-app             — always: the dashboard polls /api/alerts
"""
from __future__ import annotations

import logging

import httpx

from .. import models
from ..config import settings

log = logging.getLogger("perizone.notify")
ZONE_ICON = {"red": "🔴", "yellow": "🟡", "green": "🟢"}


def telegram_enabled() -> bool:
    return bool(settings.telegram_bot_token)


def tg_call(method: str, payload: dict, timeout: float = 8.0) -> dict | None:
    if not telegram_enabled():
        return None
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"
    try:
        r = httpx.post(url, json=payload, timeout=timeout)
        data = r.json()
        if not data.get("ok"):
            log.warning("telegram %s failed: %s", method, data)
        return data
    except Exception as exc:  # network errors must never break the API
        log.warning("telegram %s error: %s", method, exc)
        return None


def alert_text(alert: models.Alert) -> str:
    p = alert.patient
    kind = "Homilador" if p.kind == "mother" else "Chaqaloq"
    return (
        f"{ZONE_ICON.get(alert.zone, '')} <b>{alert.title}</b>\n"
        f"{kind}: <b>{p.full_name}</b> (ID {p.id})\n"
        f"Tuman: {p.district.name if p.district else '-'} · Tel: {p.phone or '-'}\n\n"
        f"{alert.message}\n\n"
        f"Eskalatsiya darajasi: {alert.level}"
    )


def alert_keyboard(alert_id: int) -> dict:
    return {"inline_keyboard": [
        [{"text": "✅ Qabul qildim", "callback_data": f"ack:{alert_id}"}],
        [{"text": "📞 Qo'ng'iroq qildim", "callback_data": f"act:{alert_id}:called"},
         {"text": "🏠 Patronaj", "callback_data": f"act:{alert_id}:home_visit"}],
        [{"text": "🏥 Perinatal markazga", "callback_data": f"act:{alert_id}:referred"},
         {"text": "👌 Xavf yo'q", "callback_data": f"act:{alert_id}:verified_ok"}],
    ]}


def send_sms(phone: str | None, text: str) -> bool:
    """SMS gateway stub. Replace with Eskiz/Play Mobile HTTP API call."""
    if not phone:
        return False
    log.info("[SMS stub] to %s: %s", phone, text[:120])
    return True


def send_alert(alert: models.Alert, staff: models.Staff) -> str:
    log.info("ALERT #%s L%s -> %s (%s): %s", alert.id, alert.level, staff.full_name, staff.role, alert.title)
    if telegram_enabled() and staff.telegram_chat_id:
        res = tg_call("sendMessage", {
            "chat_id": staff.telegram_chat_id, "text": alert_text(alert), "parse_mode": "HTML",
            "reply_markup": alert_keyboard(alert.id),
        })
        if res and res.get("ok"):
            return "telegram"
    if alert.zone == "red" and send_sms(staff.phone, f"PeriZone: {alert.title} - {alert.patient.full_name}"):
        return "sms(stub)+in-app"
    return "in-app"


def remind_patient(p: models.Patient) -> None:
    if telegram_enabled() and p.telegram_chat_id:
        tg_call("sendMessage", {
            "chat_id": p.telegram_chat_id,
            "text": "Assalomu alaykum! Bugun o'zingizni qanday his qilyapsiz? "
                    "Iltimos, /holat buyrug'i orqali ma'lumot yuboring. 💙",
        })
