"""Live pitch demo: Malika Karimova (32 weeks) deteriorates step by step.

Start the server first (uvicorn backend.app.main:app), open the dashboard, then:
  python scripts/demo_scenario.py            # press Enter between steps
  python scripts/demo_scenario.py --auto 8   # auto-advance every 8 seconds
"""
from __future__ import annotations

import argparse
import time

import httpx

BASE = "http://127.0.0.1:8000"
PHONE = "+998901234567"

STEPS = [
    ("1/4  Malika Telegram orqali uyda o'lchagan bosimini yuboradi (hali me'yorda)",
     "self", {"sbp": 128, "dbp": 82, "symptoms": []}),
    ("2/4  Ertasi kuni: bosim ko'tarildi + kuchli bosh og'rig'i (o'zi kiritgan) -> QIZIL, tasdiqlash kerak",
     "self", {"sbp": 148, "dbp": 94, "symptoms": ["severe_headache"]}),
    ("3/4  Patronaj hamshirasi uyga keldi: klinik o'lchov 166/112, proteinuriya 2+ -> tasdiqlangan preeklampsiya",
     "clinic", {"sbp": 166, "dbp": 112, "proteinuria": 3, "heart_rate": 96, "entered_by": "Patronaj hamshirasi"}),
    ("4/4  Hech kim javob bermasa — eskalatsiya avtomatik: bosh shifokor, keyin viloyat. Panelni kuzating.",
     None, None),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto", type=float, default=0)
    args = ap.parse_args()
    c = httpx.Client(base_url=BASE, timeout=10)
    patient = c.get("/api/self-report/lookup", params={"phone": PHONE}).json()
    print(f"Demo bemor: {patient['full_name']} (ID {patient['id']}) -> {BASE}/patient.html?id={patient['id']}\n")
    for title, source, body in STEPS:
        if args.auto:
            time.sleep(args.auto)
        else:
            input(f"[Enter] {title}")
        print("     " + title if args.auto else "", end="")
        if source == "self":
            r = c.post("/api/self-report", json={"patient_id": patient["id"], **body}).json()
            print(f"\n     -> zona: {r['zone']}; onaga javob: {r['advice']['title']}")
        elif source == "clinic":
            r = c.post(f"/api/patients/{patient['id']}/observations", json={"source": "clinic", **body}).json()
            print(f"\n     -> zona: {r['zone']}; sabablar: " + "; ".join(x["label"] for x in r["reasons"][:3]))
        else:
            meta = c.get("/api/meta").json()
            print(f"\n     -> eskalatsiya oralig'i: {meta['escalation_seconds']} soniya")
    print("\nTayyor.")


if __name__ == "__main__":
    main()
