# PeriZone — Perinatal yuqori xavf guruhi registri

Homilador ayollar va chaqaloqlarni **Qizil / Sariq / Yashil** zonalar orqali real vaqtda monitoring qiluvchi tizim.
Tahlillar yomonlashganda OvaBMU mutaxassislariga **avtomatik xabarnoma** yuboradi va javob bo'lmasa **eskalatsiya** qiladi.

> Hackathon prototype. Clinical thresholds are demo values based on MEOWS / NEWTT2 / WHO danger signs and
> **must be validated by obstetricians and neonatologists** before real use. See [docs/RESEARCH.md](docs/RESEARCH.md).

## What it does

```
 Ayol (Telegram bot / ona ilovasi) ─┐   source=self
 Patronaj hamshira / klinika ───────┼─▶ Observation ─▶ Rules engine (YAML) ─▶ Zone ─▶ Alert ─▶ Telegram / panel
 Laboratoriya / DMED (keyin) ───────┘   source=clinic/lab      + trends            │        │
                                                               + ML (maslahat)      │        └─ no ack in N sec ─▶ bosh shifokor ─▶ viloyat
                                                                                    └─ export CSV (outcome labels) ─▶ ML retraining
```

* **Zone engine** (`backend/app/rules/`): parameter bands, danger-sign symptoms, combinations (BP + proteinuria = preeclampsia,
  fever + tachycardia = sepsis), worsening trends (BP rising, Hb falling), risk-factor floors (twins, prior CS, age…),
  MEOWS aggregation (3 yellow → red; newborns 2). Every reason is shown to the doctor with its data source.
* **Self-reporting** via Telegram bot or mobile web page: one-tap danger-sign checklist + home BP / temperature / glucose / weight.
  Immediate advice back to the woman (danger sign → "call 103").
  Self-reported reds create a *verify* alert; a clinic reading confirms and closes the loop.
* **Alerts**: de-duplicated, with buttons (acknowledged / called / home visit / referred / no risk), escalation timers, full audit log.
  Missed check-ins (no data for N days, by zone) also alert.
* **ML** (`ml/train.py`): baseline random forest on the UCI Maternal Health Risk dataset, honest CV (duplicates removed).
  Advisory only: can raise green → yellow, never creates red.
* **Dataset export** `/api/export/ml-dataset.csv`: pseudonymised per-observation rows + outcome labels for retraining on local data.

## Run it

```bash
pip install -r requirements.txt
python ml/train.py                 # trains ml/models/maternal_risk.joblib (dataset is in ml/data/raw)
python scripts/seed.py             # demo registry: 160 mothers + 40 newborns in 5 Tashkent districts
uvicorn backend.app.main:app --port 8000
```

Open http://127.0.0.1:8000 — dashboard. Other pages: Registr, patient card, *Qoidalar va ML*, *Ona ilovasi* (mobile self-report).
API docs: http://127.0.0.1:8000/docs

### Telegram (optional, recommended for the demo)
1. Create a bot with @BotFather, put the token into `.env` (`TELEGRAM_BOT_TOKEN=...`, see `.env.example`), restart.
2. **Specialist**: send `/staff YAK113` to the bot (codes are on the *Qoidalar va ML* page) → alerts for that district arrive in Telegram with action buttons.
3. **Mother**: `/start` → share contact. For the demo, edit Malika Karimova's phone to your own number first
   via `PATCH /api/patients/1` with `{"phone": "+998..."}` (e.g. from http://127.0.0.1:8000/docs).

### Live demo scenario (pitch)
```bash
python scripts/demo_scenario.py          # Enter between steps; watch the dashboard
```
1. Malika (32 weeks) sends normal home BP → green.
2. Next day: BP 148/94 + severe headache (self) → **red**, "please verify" alert; she is told to call 103.
3. Nurse home visit: 166/112, proteinuria 2+ → confirmed preeclampsia, the self-report alert is marked confirmed.
4. Nobody acknowledges → after 90 s escalates to head physician, after 180 s to region (`ESCALATION_SECONDS`).

## Tests
```bash
python -m pytest -q
```

## Project layout
```
backend/app/
  rules/maternal.yaml, newborn.yaml   clinical thresholds (edit here)
  rules/engine.py                     pure zone logic
  services/assessment.py              re-assess + decide if an alert is needed
  services/alerts.py                  dedupe, escalation, actions, missed check-ins
  services/telegram_bot.py            bot for mothers & staff (long polling, no extra deps)
  services/ml.py                      advisory ML layer
  api/routes.py                       REST API
frontend/                             static dashboard (vanilla JS, Chart.js, Leaflet)
ml/train.py                           baseline model training
scripts/seed.py, demo_scenario.py     demo data & pitch script
docs/RESEARCH.md                      evidence, design decisions, judge Q&A
```

## Roadmap
* DMED integration via FHIR R5 (Patient, Observation, RiskAssessment, Flag, Communication)
* SMS gateway (Eskiz / Play Mobile) + USSD for women without smartphones
* Auth & roles (nurse / specialist / head / region), on-prem deployment (data localisation law)
* Outcome-based ML on local data (BP/Hb slopes, adherence, symptom frequency), calibration, drift monitoring
* Daily digest for yellow zone, Russian UI
