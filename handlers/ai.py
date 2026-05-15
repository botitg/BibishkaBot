"""Локальный бесплатный AI-помощник по слову «Бибишка»."""

from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import Message

import database as db


router = Router()
logger = logging.getLogger(__name__)


def _extract_question(text: str) -> str | None:
    """Достает вопрос после обращения «Бибишка»."""
    normalized = db.normalize_text(text)
    if not re.match(r"^\s*бибишка\b", normalized):
        return None

    return re.sub(r"^\s*бибишка[\s,.:;!?-]*", "", text, flags=re.IGNORECASE).strip()


def _answer_from_facts(question: str) -> str:
    """Генерирует ответ на основе локальной базы фактов и FAQ."""
    normalized = db.normalize_text(question)
    facts = db.BIBISHKA_FACTS

    faq = db.find_faq_by_text(question)
    if faq:
        db.record_answer(int(faq["id"]))
        return str(faq["answer"])

    if any(word in normalized for word in ["сколько лет", "возраст", "лет"]):
        return f"🎂 Бибисоре {facts['age']}."

    if any(word in normalized for word in ["класс", "учится", "школ"]):
        return f"📚 Бибисора сейчас в {facts['class']}."

    if any(word in normalized for word in ["родилась", "день рождения", "др", "дата рождения"]):
        return f"🎉 Бибисора родилась {facts['birthday']}."

    if any(word in normalized for word in ["где жив", "город", "страна", "откуда"]):
        return f"📍 Бибисора живет в {facts['country']}, город {facts['city']}."

    if any(word in normalized for word in ["лучшая подруга", "подруга", "садокат"]):
        return f"👑 Лучшая подруга Бибисоры — {facts['best_friend']}."

    if any(word in normalized for word in ["друзья", "друг", "нурик", "абубакр", "эмиль"]):
        return f"🤝 Друзья Бибисоры: {facts['friends']}."

    if any(word in normalized for word in ["реклама", "пиар", "сотрудничество"]):
        return "📣 По рекламе открой /ads или раздел «Реклама» в меню /start и отправь предложение."

    return (
        "🤖 Я локальный AI-помощник Бибишки. Вот что я точно знаю:\n"
        f"• Бибисоре {facts['age']}\n"
        f"• Она в {facts['class']}\n"
        f"• День рождения — {facts['birthday']}\n"
        f"• Живет: {facts['country']}, {facts['city']}\n"
        f"• Лучшая подруга: {facts['best_friend']}\n"
        f"• Друзья: {facts['friends']}\n\n"
        "Спроси конкретнее, например: «Бибишка, когда день рождения?»"
    )


@router.message(F.text)
async def bibishka_ai(message: Message) -> None:
    """Отвечает, когда сообщение начинается с обращения «Бибишка»."""
    if not db.get_bool_setting("ai_enabled", True):
        raise SkipHandler()

    if message.text is None:
        raise SkipHandler()

    question = _extract_question(message.text)
    if question is None:
        raise SkipHandler()

    if message.from_user:
        db.add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)

    if not question:
        await message.answer("🤖 Зови меня так: «Бибишка, сколько лет Бибисоре?»")
        return

    await message.answer(_answer_from_facts(question), parse_mode=None)

