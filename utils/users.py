"""Помощники для красивого отображения пользователей Telegram."""

from __future__ import annotations

import logging
from html import escape
from typing import Any

from aiogram import Bot
from aiogram.types import User


logger = logging.getLogger(__name__)


def mention_from_user(user: User | None, fallback_id: int | None = None) -> str:
    """Возвращает имя пользователя как кликабельную ссылку на профиль."""
    if user is not None:
        name = escape(user.full_name or user.first_name or "профиль")
        return f'<a href="tg://user?id={user.id}">{name}</a>'

    if fallback_id is not None:
        return f'<a href="tg://user?id={fallback_id}">профиль</a>'

    return "пользователь"


async def mention_by_id(bot: Bot, user_id: int, fallback: str = "профиль") -> str:
    """Пытается получить имя по ID, иначе возвращает ссылку на профиль."""
    try:
        chat: Any = await bot.get_chat(user_id)
    except Exception:
        logger.debug("Не удалось получить профиль пользователя %s", user_id, exc_info=True)
        return f'<a href="tg://user?id={user_id}">{escape(fallback)}</a>'

    full_name = getattr(chat, "full_name", None)
    first_name = getattr(chat, "first_name", None)
    title = getattr(chat, "title", None)
    name = escape(str(full_name or first_name or title or fallback))
    return f'<a href="tg://user?id={user_id}">{name}</a>'
