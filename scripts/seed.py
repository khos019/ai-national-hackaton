"""Generate a realistic demo registry (fictional people).

  python scripts/seed.py            # 160 mothers + 40 newborns, Tashkent districts
  python scripts/seed.py --mothers 300 --newborns 80

Each mother follows a clinical "archetype" (normal, gestational hypertension,
preeclampsia, anaemia, GDM, infection) so the dashboard shows meaningful zones
and the exported dataset has learnable patterns + outcome labels.
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import models  # noqa: E402
from backend.app.db import Base, SessionLocal, engine  # noqa: E402
from backend.app.services import ml  # noqa: E402
from backend.app.services.assessment import reassess  # noqa: E402
from backend.app.services.intake import add_observation  # noqa: E402
from backend.app.timeutil import utcnow  # noqa: E402

DISTRICTS = [
    ("Chilonzor", 41.2756, 69.2034), ("Yunusobod", 41.3640, 69.2870),
    ("Mirzo Ulug'bek", 41.3380, 69.3350), ("Sergeli", 41.2240, 69.2190),
    ("Yakkasaroy", 41.2870, 69.2560),
]
FIRST = ["Malika", "Dilnoza", "Gulnora", "Shahnoza", "Madina", "Nilufar", "Zarina", "Mohira", "Sevara",
         "Feruza", "Kamola", "Nodira", "Dildora", "Gulshan", "Mahliyo", "Sabina", "Umida", "Barno",
         "Lola", "Ziyoda", "Munisa", "Hilola", "Shoira", "Nargiza", "Durdona", "Yulduz", "Oydin", "Iroda"]
LAST = ["Karimova", "Rahimova", "Tosheva", "Yusupova", "Aliyeva", "Ergasheva", "Nazarova", "Saidova",
        "Qodirova", "Mirzayeva", "Abdullayeva", "Hasanova", "Jo'rayeva", "Sobirova", "Islomova",
        "Ismoilova", "Xolmatova", "Normatova", "Usmonova", "Raximova", "To'xtayeva", "Bakirova"]
BOY = ["Muhammad", "Abdulloh", "Amir", "Umar", "Ali", "Yusuf", "Sardor", "Jasur"]
GIRL = ["Oisha", "Asal", "Zahro", "Mubina", "Soliha", "Robiya", "Imona", "Fotima"]
STREETS = ["Bunyodkor", "Qatortol", "Amir Temur", "Bog'ishamol", "Chilonzor-9", "Kichik halqa yo'li", "Yangi Sergeli"]

ARCHETYPES = [("normal", 0.58), ("gest_hypertension", 0.12), ("preeclampsia", 0.06),
              ("anemia", 0.12), ("gdm", 0.08), ("infection", 0.04)]
OUTCOME = {"normal": "normal_delivery", "gest_hypertension": "gestational_hypertension",
           "preeclampsia": "preeclampsia", "anemia": "anemia", "gdm": "gestational_diabetes",
           "infection": "infection"}

DEMO_PHONE = "+998901234567"


def phone(rng):
    return f"+998{rng.choice([90, 91, 93, 94, 95, 97, 99, 33, 88])}{rng.randint(1000000, 9999999)}"


def jitter(rng, lat, lon, km=2.5):
    return lat + rng.uniform(-km, km) / 111, lon + rng.uniform(-km, km) / 84


def pick_archetype(rng):
    r, acc = rng.random(), 0.0
    for name, w in ARCHETYPES:
        acc += w
        if r <= acc:
            return name
    return "normal"


def mother_values(rng, arche, progress, base, self_report=False):
    """progress: 0..1 through the monitored period. Returns a dict of observation values."""
    sbp = base["sbp"] + rng.gauss(0, 6 if self_report else 4)
    dbp = base["dbp"] + rng.gauss(0, 5 if self_report else 3)
    hb = base["hb"] - 6 * progress + rng.gauss(0, 3)
    glu = base["glu"] + rng.gauss(0, 0.15)
    temp = 36.6 + rng.gauss(0, 0.2)
    hr = base["hr"] + 6 * progress + rng.gauss(0, 4)
    prot, symptoms = 0, []
    if arche == "gest_hypertension":
        sbp += 26 * progress ** 1.5
        dbp += 16 * progress ** 1.5
    elif arche == "preeclampsia":
        sbp += 45 * progress ** 2.2
        dbp += 30 * progress ** 2.2
        if progress > 0.75:
            prot = rng.choice([2, 3, 3, 4])
            if rng.random() < 0.6:
                symptoms.append(rng.choice(["severe_headache", "swelling_face_hands", "blurred_vision"]))
    elif arche == "anemia":
        hb -= 32 * progress
    elif arche == "gdm":
        glu += 2.0 * min(1, progress * 1.5)
    elif arche == "infection" and progress > 0.85:
        temp = rng.uniform(38.0, 39.2)
        hr += 22
        symptoms.append(rng.choice(["fever", "painful_urination"]))
    return {"sbp": round(sbp), "dbp": round(dbp), "hemoglobin": round(hb), "glucose": round(glu, 1),
            "temperature": round(temp, 1), "heart_rate": round(hr), "proteinuria": prot, "symptoms": symptoms}


def seed(n_mothers: int, n_newborns: int, rng_seed: int = 7) -> None:
    rng = random.Random(rng_seed)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    now = utcnow()
    today = now.date()
    ml.ENABLED = False  # fast history replay; ML is applied in the final pass

    districts = []
    for name, lat, lon in DISTRICTS:
        d = models.District(name=name, region="Toshkent shahri", lat=lat, lon=lon)
        db.add(d)
        districts.append(d)
    db.flush()

    code = 100
    for d in districts:
        for role, title in (("specialist", "OvaBMU mutaxassisi"), ("head", "Bosh shifokor"), ("nurse", "Patronaj hamshirasi")):
            code += 1
            db.add(models.Staff(full_name=f"{rng.choice(FIRST)} {rng.choice(LAST)} ({title}, {d.name})",
                                role=role, district_id=d.id, phone=phone(rng), link_code=f"{d.name[:3].upper().replace(chr(39), '')}{code}"))
    db.add(models.Staff(full_name="Viloyat perinatal markazi navbatchisi", role="regional", phone=phone(rng), link_code="REG001"))
    db.flush()

    mothers = []
    for i in range(n_mothers):
        d = rng.choice(districts)
        arche = pick_archetype(rng)
        age = int(min(46, max(16, rng.gauss(28, 6))))
        ga_now = rng.randint(10, 39)
        lmp = today - timedelta(weeks=ga_now, days=rng.randint(0, 6))
        rf = []
        if rng.random() < 0.10: rf.append("prior_cesarean")
        if rng.random() < 0.04: rf.append("multiple_pregnancy")
        if rng.random() < 0.05: rf.append("anemia_history")
        if rng.random() < 0.04: rf.append("social_risk")
        if arche == "gest_hypertension" and rng.random() < 0.3: rf.append("chronic_hypertension")
        if arche == "preeclampsia" and rng.random() < 0.4: rf.append("prior_preeclampsia")
        if arche == "gdm" and rng.random() < 0.3: rf.append("diabetes")
        lat, lon = jitter(rng, d.lat, d.lon)
        is_demo = i == 0
        p = models.Patient(
            kind="mother", full_name="Malika Karimova" if is_demo else f"{rng.choice(FIRST)} {rng.choice(LAST)}",
            birth_date=date(today.year - age, rng.randint(1, 12), rng.randint(1, 28)),
            phone=DEMO_PHONE if is_demo else phone(rng), district_id=d.id,
            address=f"{d.name} t., {rng.choice(STREETS)} ko'chasi, {rng.randint(1, 120)}-uy",
            lat=lat, lon=lon, lmp_date=lmp, parity=rng.choice([0, 0, 1, 1, 2, 3, 4]),
            risk_factors=[] if is_demo else rf, created_at=datetime.combine(lmp + timedelta(weeks=8), datetime.min.time()),
        )
        if is_demo:
            arche, ga_now = "normal", 32
            p.lmp_date = today - timedelta(weeks=32)
            p.birth_date = date(today.year - 27, 4, 12)
        db.add(p)
        db.flush()
        mothers.append(p)

        base = {"sbp": rng.gauss(112, 8), "dbp": rng.gauss(72, 6), "hb": rng.gauss(124, 6),
                "glu": rng.gauss(4.4, 0.25), "hr": rng.gauss(78, 6), "w": rng.gauss(58, 7)}
        start_week = rng.randint(6, 12)
        uses_bot = is_demo or rng.random() < 0.55
        if uses_bot:
            p.telegram_chat_id = None  # becomes real when she links via the bot
        # Clinic visits: every 2-4 weeks early, weekly after 28 weeks
        week = start_week
        visit_times = []
        while week <= ga_now:
            visit_times.append(lmp + timedelta(weeks=week, days=rng.randint(0, 3)))
            week += 1 if week >= 28 else rng.choice([2, 3, 4])
        span = max(1, (ga_now - start_week))
        # Some women stop coming -> missed check-in alerts
        if not is_demo and rng.random() < 0.07 and len(visit_times) > 2:
            visit_times = visit_times[:-2]
        for vd in visit_times:
            if vd > today:
                continue
            prog = ((vd - lmp).days / 7 - start_week) / span
            vals = mother_values(rng, arche, max(0, prog), base)
            vals["weight"] = round(base["w"] + 0.4 * (vd - lmp).days / 7 + rng.gauss(0, 0.3), 1)
            if (vd - lmp).days // 7 not in range(24, 29):
                vals["glucose"] = None if rng.random() < 0.5 else vals["glucose"]
            at = datetime.combine(vd, datetime.min.time()) + timedelta(hours=rng.randint(8, 16))
            if at > now:
                at = now - timedelta(hours=2)
            add_observation(db, p, vals, source="clinic", entered_by="Patronaj hamshirasi", recorded_at=at, notify=False)
        # Self-reports in the last 3 weeks (symptoms + home BP)
        if uses_bot:
            t = now - timedelta(days=21)
            while t < now - timedelta(hours=6):
                t += timedelta(days=rng.choice([1, 2, 3]), hours=rng.randint(-3, 3))
                if t >= now:
                    break
                prog = ((t.date() - lmp).days / 7 - start_week) / span
                vals = mother_values(rng, arche, max(0, min(1, prog)), base, self_report=True)
                data = {"sbp": vals["sbp"], "dbp": vals["dbp"]} if rng.random() < 0.6 else {}
                data["symptoms"] = vals["symptoms"] if rng.random() < 0.7 else []
                if arche == "infection" and vals["temperature"] > 37.5:
                    data["temperature"] = vals["temperature"]
                add_observation(db, p, data, source="self", entered_by="telegram", recorded_at=t, notify=False)
        p.outcome = None  # still pregnant; label filled after delivery
        p._arche = arche  # type: ignore[attr-defined]

    # Newborns (some are children of registered mothers, sharing her phone)
    for _ in range(n_newborns):
        d = rng.choice(districts)
        age_days = rng.randint(0, 27)
        ga = int(min(42, max(27, rng.gauss(38.5, 2.2))))
        bw = int(max(900, rng.gauss(3300 - (40 - ga) * 230, 380)))
        apgar = rng.choice([9, 9, 8, 8, 8, 7, 7, 6, 5]) if ga < 35 else rng.choice([9, 9, 9, 8, 8, 8, 7])
        sick = rng.random() < 0.15
        mother_name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        surname = mother_name.split()[1]
        boy = rng.random() < 0.5
        name = f"{rng.choice(BOY if boy else GIRL)} {surname[:-1] if boy and surname.endswith('a') else surname}"
        lat, lon = jitter(rng, d.lat, d.lon)
        nb = models.Patient(kind="newborn", full_name=name, birth_date=today - timedelta(days=age_days),
                            phone=phone(rng), district_id=d.id, lat=lat, lon=lon,
                            address=f"{d.name} t., {rng.choice(STREETS)} ko'chasi",
                            birth_weight_g=bw, gestational_age_at_birth=ga, apgar5=apgar,
                            risk_factors=["maternal_infection"] if sick and rng.random() < 0.5 else [])
        db.add(nb)
        db.flush()
        w = bw / 1000
        for day in range(0, age_days + 1, rng.choice([2, 3])):
            at = datetime.combine(nb.birth_date + timedelta(days=day), datetime.min.time()) + timedelta(hours=rng.randint(9, 17))
            if at > now:
                at = now - timedelta(hours=1)
            w = w * (0.97 if day < 4 else 1.01) + rng.gauss(0, 0.01)
            late_sick = sick and day >= age_days - 2
            vals = {"temperature": round((38.4 if late_sick else 36.9) + rng.gauss(0, 0.2), 1),
                    "heart_rate": round((172 if late_sick else 140) + rng.gauss(0, 8)),
                    "resp_rate": round((62 if late_sick else 44) + rng.gauss(0, 4)),
                    "weight": round(w, 3),
                    "symptoms": rng.sample(["poor_feeding", "lethargy", "jaundice"], 1) if late_sick else []}
            add_observation(db, nb, vals, source="clinic" if day % 2 == 0 else "self",
                            entered_by="Patronaj hamshirasi", recorded_at=at, notify=False)

    # Final pass with ML enabled — current zones
    ml.ENABLED = True
    for p in db.query(models.Patient).all():
        reassess(db, p, now=now, notify=False)
    db.flush()

    # Historic alerts: replay created alerts with realistic response times
    for a in db.query(models.Alert).all():
        a.next_escalation_at = None
        age = now - a.created_at
        if age > timedelta(days=2) or rng.random() < 0.5:
            a.status = "resolved"
            a.acknowledged_at = a.created_at + timedelta(minutes=rng.randint(4, 240))
            a.acknowledged_by = "OvaBMU mutaxassisi"
            a.resolved_at = a.acknowledged_at + timedelta(hours=rng.randint(1, 30))
            db.add(models.AlertEvent(alert_id=a.id, type="acknowledged", actor=a.acknowledged_by, at=a.acknowledged_at))
            db.add(models.AlertEvent(alert_id=a.id, type="resolved", actor=a.acknowledged_by, at=a.resolved_at))
    db.commit()

    zones = {}
    for p in db.query(models.Patient).all():
        zones[(p.kind, p.zone)] = zones.get((p.kind, p.zone), 0) + 1
    print("Seeded:", {f"{k[0]}/{k[1]}": v for k, v in sorted(zones.items())})
    print("Alerts:", db.query(models.Alert).count(), "| open:", db.query(models.Alert).filter_by(status="open").count())
    print(f"Demo patient: Malika Karimova, phone {DEMO_PHONE}")
    print("Staff Telegram link codes:", ", ".join(s.link_code for s in db.query(models.Staff).filter(models.Staff.role != "nurse")))
    db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mothers", type=int, default=160)
    ap.add_argument("--newborns", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    seed(a.mothers, a.newborns, a.seed)
