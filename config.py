"""Конфигурация BIBISHKA Admin Bot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _parse_admin_ids(raw_value: str | None) -> list[int]:
    """Преобразует ADMIN_IDS из .env в список Telegram ID."""
    if not raw_value:
        return []

    admin_ids: list[int] = []
    for item in raw_value.split(","):
        item = item.strip()
        if item.isdigit():
            admin_ids.append(int(item))
    return admin_ids


@dataclass(frozen=True)
class BotConfig:
    """Хранит основные настройки приложения."""

    token: str
    database_path: Path
    admin_ids: list[int]


config = BotConfig(
    token=os.getenv("BOT_TOKEN", "").strip(),
    database_path=Path(os.getenv("DATABASE_PATH", BASE_DIR / "data" / "bot.db")),
    admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS")),
)

