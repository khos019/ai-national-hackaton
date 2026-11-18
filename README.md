# PeriZone — Perinatal yuqori xavf guruhi registri

Homilador ayollar va chaqaloqlarni **Qizil / Sariq / Yashil** zonalar orqali real vaqtda kuzatuvchi tizim.
Tahlillar yomonlashganda **shifokorga darhol xabarnoma**, javob bo'lmasa — **administratorga eskalatsiya**.
Ayollar **Telegram bot** orqali holatini yuboradi, **AI yordamchi** erkin matndan ma'lumot ajratib shifokorga yetkazadi.

> Hackathon prototype (AI National Hackathon). Clinical thresholds are demo values based on MEOWS / NEWTT2 / WHO
> danger signs and **must be validated by obstetricians and neonatologists** before real use. See [docs/RESEARCH.md](docs/RESEARCH.md).

## Three roles

| Role | Where | Can |
|---|---|---|
| **Woman / mother** | Telegram bot (+ public mother page) | report danger signs, BP, fetal movements, temperature, weight; chat with the AI assistant (Premium) |
| **Doctor / patronage nurse** | Website | register patients, see **only their own** patients, answer alerts, enter clinic measurements |
| **Owner (administrator)** | Website | see all districts, add/deactivate doctors, reassign patients, manage subscriptions, export data |

Doctors are onboarded by the owner with a **one-time activation code** → they set their own password (`/activate.html`).

## Features

* **Zone engine** (`backend/app/rules/*.yaml`, doctor-editable): parameter bands, WHO danger signs, combinations
  (BP + proteinuria = preeclampsia, fever + tachycardia = sepsis, headache + blurred vision), trends (BP rising, Hb falling),
  risk-factor floors, MEOWS aggregation, fetal-movement "count to 10". Every reason is shown with its data source.
* **Telegram bot for women**: adaptive menu (newborns don't see BP; glucose only with (gestational) diabetes; kick counting from
  28 weeks), iron/folic-acid adherence, instant advice ("call 103" on danger signs), mother+baby on one phone.
* **AI assistant** (`backend/app/services/ai_assistant.py`): a woman writes in her own words → Claude (structured outputs)
  extracts symptoms and measurements → saved as a self-reported observation → zone/alerts; she gets a short general-information
  reply; her doctor sees the conversation on the patient card. A keyword safety net (Uzbek Latin/Cyrillic + Russian) always runs,
  and the assistant falls back to rules if the API is unavailable — an emergency never depends on the model.
* **Subscription**: danger-sign reporting and alerts are **always free**; Premium (19 900 so'm/month, 7-day trial) adds the AI assistant,
  weekly personal report and reminders. Owner can grant free Premium to low-income families. Payments: demo in the prototype
  (production: Telegram Payments with Click / Payme).
* **Alerts**: routed to the patient's own doctor (website sound + desktop notification + SMS stub), escalate to the owner,
  de-duplicated, full audit log, red-first feed, missed check-in alerts.
* **Website**: role-aware dashboard, registry, patient card (zone action plan, charts, AI chat, history, subscription, outcome labels),
  doctors management, subscriptions & revenue, "How it works" guide.
* **ML**: advisory baseline model (UCI Maternal Health Risk, honest CV) + pseudonymised dataset export for local retraining.

## Run

```bash
pip install -r requirements.txt
python ml/train.py            # baseline model
python scripts/seed.py        # demo data: 1 owner, 10 doctors, 162 mothers, 40 newborns, subscriptions
uvicorn backend.app.main:app --port 8000
```

Open http://127.0.0.1:8000 — demo logins (password `perizone2026`):

| Phone | Role |
|---|---|
| `+998900000001` | Owner (all districts) |
| `+998900000002` | Doctor — Chilonzor |
| `+998900000010` | Doctor — Yakkasaroy (has demo patient Malika Karimova, `+998901234567`) |
| `+998900000011` | Doctor — **not activated**: use the code printed by `seed.py` on `/activate.html` |

### `.env`
```
TELEGRAM_BOT_TOKEN=...          # bot for women
TELEGRAM_BOT_USERNAME=...
ANTHROPIC_API_KEY=...           # optional: Claude AI assistant (otherwise rule-based)
AI_MODEL=claude-opus-5-5        # optional
ESCALATION_SECONDS=120          # doctor -> owner escalation (production e.g. 1800)
SUBSCRIPTION_PRICE=19900
SECRET_KEY=change-me
```

## Tests
```bash
python -m pytest -q     # 41 tests: rules engine, roles & access control, auth, subscriptions, bot conversations, AI fallback
```

## Layout
```
backend/app/auth.py                    login, activation, role scoping (doctor sees only own patients)
backend/app/rules/                     maternal.yaml, newborn.yaml, engine.py
backend/app/services/telegram_bot.py   women-only bot
backend/app/services/ai_assistant.py   Claude structured extraction + keyword safety net
backend/app/services/subscriptions.py  trial / monthly / free Premium
backend/app/services/alerts.py         routing, escalation, audit
backend/app/api/routes.py              REST API
frontend/                              login, activate, dashboard, patients, patient, doctors, subscriptions, guide, mother
```

## Privacy notes
* Doctors see only their own patients (enforced server-side; other patients return 404).
* The AI receives only pregnancy week and zone as context — never name or phone.
* Uzbekistan's personal-data law requires citizens' data on servers in Uzbekistan: deploy on local infrastructure;
  for the AI assistant use a provider/region approved for health data or the rule-based engine.
