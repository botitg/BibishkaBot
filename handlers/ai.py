"""AI-помощник по слову «Бибишка» с использованием OpenAI API."""

from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import Message
from openai import AsyncOpenAI

import database as db
from config import config


router = Router()
logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=config.openai_api_key) if config.openai_api_key else None


def _extract_question(text: str) -> str | None:
    """Достает вопрос после обращения «Бибишка»."""
    normalized = db.normalize_text(text)
    if not re.match(r"^\s*бибишка\b", normalized):
        return None

    return re.sub(r"^\s*бибишка[\s,.:;!?-]*", "", text, flags=re.IGNORECASE).strip()


async def _answer_with_ai(question: str) -> str:
    """Генерирует ответ с помощью OpenAI API."""
    if not client:
        return "⚠️ OpenAI API ключ не настроен. Добавьте OPENAI_API_KEY в .env файл."

    facts = db.BIBISHKA_FACTS
    system_prompt = (
        f"Ты — AI-помощник Бибишки (Бибисоры). Отвечай дружелюбно и информативно на вопросы о Бибишке.\n\n"
        f"Факты о Бибишке:\n"
        f"- Настоящее имя: {facts['real_name']}\n"
        f"- Возраст: {facts['age']}\n"
        f"- Класс: {facts['class']}\n"
        f"- День рождения: {facts['birthday']}\n"
        f"- Страна: {facts['country']}\n"
        f"- Город: {facts['city']}\n"
        f"- Лучшая подруга: {facts['best_friend']}\n"
        f"- Друзья: {facts['friends']}\n\n"
        "Отвечай кратко и по делу. Если вопрос не о Бибишке, вежливо скажи, что ты отвечаешь только на вопросы о ней."
    )

    try:
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            max_tokens=500,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.exception("Ошибка при вызове OpenAI API")
        return f"⚠️ Ошибка AI: {str(e)}"


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

    await message.answer(await _answer_with_ai(question), parse_mode=None)

