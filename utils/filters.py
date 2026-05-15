"""Фильтры доступа и проверки автомодерации."""

from __future__ import annotations

import re
from typing import Any

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

import database as db


LINK_RE = re.compile(
    r"(https?://|www\.|t\.me/|telegram\.me/|discord\.gg/|vk\.com/|instagram\.com/|tiktok\.com/|youtu\.be/|youtube\.com/)",
    re.IGNORECASE,
)


class AdminFilter(BaseFilter):
    """Пропускает только пользователей из таблицы admins."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        """Проверяет Telegram ID автора события."""
        user = getattr(event, "from_user", None)
        return db.is_admin(user.id if user else None)


def normalize_text(text: str) -> str:
    """Нормализует текст для фильтров."""
    return db.normalize_text(text)


def contains_link(text: str) -> bool:
    """Проверяет наличие ссылок в сообщении."""
    return bool(LINK_RE.search(text))


def contains_bad_words(text: str, raw_bad_words: str) -> bool:
    """Проверяет сообщение по списку запрещенных слов и корней."""
    normalized = normalize_text(text)
    compact = re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)
    bad_words = db.split_keywords(raw_bad_words)
    for word in bad_words:
        prepared = re.sub(r"[\W_]+", "", word, flags=re.UNICODE)
        if prepared and (prepared in compact or word in normalized):
            return True
    return False


def is_caps(text: str, min_letters: int = 12, max_ratio: float = 0.7) -> bool:
    """Определяет чрезмерный капс."""
    letters = [char for char in text if char.isalpha()]
    if len(letters) < min_letters:
        return False

    uppercase_count = sum(1 for char in letters if char.isupper())
    return uppercase_count / len(letters) >= max_ratio


def is_private_event(event: Any) -> bool:
    """Проверяет, относится ли событие к личному чату."""
    chat = getattr(event, "chat", None)
    if chat is None and hasattr(event, "message"):
        chat = getattr(event.message, "chat", None)
    return bool(chat and chat.type == "private")

