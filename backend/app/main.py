"""PeriZone — Perinatal high-risk registry with colour-zone monitoring.

Run:  uvicorn backend.app.main:app --reload
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .config import settings
from .db import SessionLocal, init_db
from .services import alerts as alert_svc
from .services import notify

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("perizone")
# httpx logs full request URLs at INFO — for Telegram that URL contains the bot token. Keep it out of logs.
logging.getLogger("httpx").setLevel(logging.WARNING)


def _scheduler_tick() -> None:
    db = SessionLocal()
    try:
        n_esc = alert_svc.run_escalations(db)
        n_miss = alert_svc.run_missed_checkins(db)
        db.commit()
        if n_esc or n_miss:
            log.info("scheduler: %s escalated, %s missed check-ins", n_esc, n_miss)
    except Exception:
        log.exception("scheduler tick failed")
        db.rollback()
    finally:
        db.close()


async def _scheduler(stop: asyncio.Event) -> None:
    while not stop.is_set():
        await asyncio.to_thread(_scheduler_tick)
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.scheduler_interval_seconds)
        except TimeoutError:
            pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    stop = asyncio.Event()
    tasks = [asyncio.create_task(_scheduler(stop))]
    if notify.telegram_enabled():
        from .services.telegram_bot import run_polling

        tasks.append(asyncio.create_task(run_polling(stop)))
    else:
        log.info("TELEGRAM_BOT_TOKEN not set — alerts are shown in the dashboard only")
    yield
    stop.set()
    for t in tasks:
        t.cancel()


app = FastAPI(title="PeriZone API", version="0.1.0", lifespan=lifespan)
app.include_router(router)
app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
