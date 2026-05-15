"""Сценарий отправки рекламных предложений ответственному администратору."""

from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import database as db
from states.admin_states import AdRequest
from utils.users import mention_from_user


router = Router()
logger = logging.getLogger(__name__)


def _sender_card(message: Message) -> str:
    """Формирует карточку отправителя рекламного предложения."""
    user = message.from_user
    if user is None:
        return "📣 <b>Новая заявка на рекламу</b>\n\nОтправитель неизвестен."

    username = f"@{user.username}" if user.username else "нет username"
    return (
        "📣 <b>Новая заявка на рекламу</b>\n\n"
        f"👤 Отправитель: {mention_from_user(user)}\n"
        f"🔗 Username: {escape(username)}"
    )


@router.message(Command("ads"))
async def cmd_ads(message: Message, state: FSMContext) -> None:
    """Запускает отправку рекламной заявки командой."""
    await state.set_state(AdRequest.content)
    await message.answer(
        f"{db.get_setting('ads_text')}\n\n"
        "Отправь следующим сообщением рекламное предложение. Я перешлю его ответственному администратору.",
        parse_mode=None,
    )


@router.message(AdRequest.content)
async def receive_ad_request(message: Message, bot: Bot, state: FSMContext) -> None:
    """Копирует рекламное сообщение ответственному ID и завершает сценарий."""
    receiver_id = db.get_int_setting("ads_receiver_id", 8436225978)
    try:
        await bot.send_message(receiver_id, _sender_card(message))
        await bot.copy_message(
            chat_id=receiver_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        logger.exception("Не удалось отправить рекламную заявку")
        await message.answer(
            "Не получилось отправить заявку. Ответственный ID должен сначала открыть чат с ботом и нажать /start."
        )
        await state.clear()
        return

    await state.clear()
    await message.answer("✅ Заявка на рекламу отправлена. Ответственный администратор получит ее в личном чате с ботом.")
