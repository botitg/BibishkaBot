"""Reply-клавиатуры для быстрых команд."""

from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove


def admin_reply_keyboard() -> ReplyKeyboardMarkup:
    """Создает компактную клавиатуру для администраторов."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/admin"), KeyboardButton(text="/rules")],
            [KeyboardButton(text="/help")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите команду или напишите сообщение",
    )


def remove_reply_keyboard() -> ReplyKeyboardRemove:
    """Убирает reply-клавиатуру у пользователя."""
    return ReplyKeyboardRemove()

