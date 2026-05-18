"""Автоматические ответы на частые вопросы."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message

import database as db
from keyboards.inline import back_to_main_keyboard, main_menu_keyboard


router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("faq:item:"))
async def callback_faq_item(callback: CallbackQuery) -> None:
    """Отправляет выбранный FAQ-ответ."""
    await callback.answer()
    if callback.data is None or callback.message is None:
        return

    try:
        faq_id = int(callback.data.rsplit(":", 1)[1])
    except ValueError:
        await callback.message.answer("Не удалось открыть этот вопрос.")
        return

    faq = db.get_faq(faq_id)
    if faq is None:
        await callback.message.answer("Этот вопрос уже удален.", reply_markup=back_to_main_keyboard())
        return

    db.record_answer(faq_id)
    await callback.message.answer(str(faq["answer"]), reply_markup=back_to_main_keyboard(), parse_mode=None)


@router.message(F.text)
async def auto_answer_faq(message: Message) -> None:
    """Ищет ключевые слова и отвечает подходящим FAQ-текстом."""
    if message.text is None or message.text.startswith("/"):
        raise SkipHandler()

    # В группах не отвечаем на сообщения, содержащие обращение к Бибишке
    try:
        normalized = db.normalize_text(message.text)
        if message.chat.type != ChatType.PRIVATE and "бибишка" in normalized:
            raise SkipHandler()
    except Exception:
        # В редком случае, если нормализация упала, просто продолжаем
        pass

    if message.from_user:
        db.add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)

    faq = db.find_faq_by_text(message.text)
    if faq is None:
        if message.chat.type == ChatType.PRIVATE:
            await message.answer(
                "Пока не нашла точный ответ. Открой FAQ или спроси так: «Бибишка, сколько лет Бибисоре?»",
                reply_markup=main_menu_keyboard(),
            )
        return

    db.record_answer(int(faq["id"]))
    await message.answer(str(faq["answer"]), parse_mode=None)

