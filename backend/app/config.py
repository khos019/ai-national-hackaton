"""Application settings (read from environment / .env file)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    env = ROOT_DIR / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _ints(value: str) -> list[int]:
    return [int(v) for v in value.split(",") if v.strip()]


class Settings:
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{(ROOT_DIR / 'data' / 'perizone.db').as_posix()}")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    # Seconds to wait for acknowledgement before escalating to level 1, then level 2.
    # Production would be e.g. "1800,3600"; demo default is short so judges can see it.
    escalation_seconds: list[int] = _ints(os.getenv("ESCALATION_SECONDS", "90,180"))
    scheduler_interval_seconds: int = int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "10"))
    model_path: Path = ROOT_DIR / "ml" / "models" / "maternal_risk.joblib"
    rules_dir: Path = Path(__file__).resolve().parent / "rules"
    frontend_dir: Path = ROOT_DIR / "frontend"
    # ML probability of "high" above which a green patient is raised to yellow.
    ml_high_threshold: float = float(os.getenv("ML_HIGH_THRESHOLD", "0.6"))
    emergency_phone: str = "103"


settings = Settings()
