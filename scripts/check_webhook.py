"""Проверяет getWebhookInfo для бота, не выводя BOT_TOKEN в явном виде."""

from __future__ import annotations

import json
import urllib.request
import sys
from pathlib import Path

# Добавляем корневую папку проекта в sys.path, чтобы импортировать локальные модули
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import config

if not config.token:
    print("BOT_TOKEN не найден в .env")
    raise SystemExit(1)

url = f"https://api.telegram.org/bot{config.token}/getWebhookInfo"
try:
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.load(resp)
    print(json.dumps(data, ensure_ascii=False, indent=2))
except Exception as e:
    print("Ошибка при обращении к Telegram API:", e)
