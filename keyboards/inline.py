"""Inline-клавиатуры для меню пользователя и админ-панели."""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def _faq_label(item: dict[str, Any]) -> str:
    """Формирует красивую подпись FAQ-кнопки с большой буквы."""
    first_keyword = str(item["keywords"]).replace("\n", ",").split(",")[0].strip()
    first_keyword = first_keyword[:32].strip()
    return f"#{item['id']} {first_keyword[:1].upper()}{first_keyword[1:]}"


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Создает главное меню для /start."""
    builder = InlineKeyboardBuilder()
    # Игровой раздел отключён
    builder.button(text="❓ FAQ", callback_data="main:faq")
    builder.button(text="🌐 Соцсети", callback_data="main:socials")
    builder.button(text="🎥 Стримы", callback_data="main:streams")
    builder.button(text="📣 Реклама", callback_data="main:ads")
    builder.button(text="🏆 Награды", callback_data="main:awards")
    builder.button(text="📊 Топы", callback_data="main:top")
    builder.button(text="💍 Браки", callback_data="main:marriages")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def private_start_keyboard(bot_username: str, chat_id: int | None = None) -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопкой для открытия личных сообщений с ботом.

    Если передан `chat_id`, добавляет его в payload (`start=join_{chat_id}`),
    чтобы при открытии ЛС бот мог зарегистрировать пользователя для конкретного чата.
    """
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    if chat_id is not None:
        url = f"https://t.me/{bot_username}?start=join_{chat_id}"
    else:
        url = f"https://t.me/{bot_username}?start=join"
    # Текст кнопки изменён: избегаем формулировки 'Написать'
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть бота", url=url)]])


def faq_public_keyboard(items: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    """Создает список FAQ-вопросов для пользователей."""
    builder = InlineKeyboardBuilder()
    for item in items:
        builder.button(text=_faq_label(item), callback_data=f"faq:item:{item['id']}")
    builder.button(text="⬅️ Назад", callback_data="main:back")
    builder.adjust(1)
    return builder.as_markup()


def socials_keyboard() -> InlineKeyboardMarkup:
    """Создает меню соцсетей без YouTube и доната."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🎵 TikTok", callback_data="social:tiktok")
    builder.button(text="📸 Instagram", callback_data="social:instagram")
    builder.button(text="💬 Telegram", callback_data="social:telegram")
    builder.button(text="⬅️ Назад", callback_data="main:back")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def back_to_main_keyboard() -> InlineKeyboardMarkup:
    """Создает кнопку возврата в главное меню."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="main:back")]]
    )


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Создает главное меню админ-панели."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Список вопросов", callback_data="admin:list")
    builder.button(text="➕ Добавить вопрос", callback_data="admin:add")
    builder.button(text="✏️ Изменить ответ", callback_data="admin:edit")
    builder.button(text="🗑 Удалить вопрос", callback_data="admin:delete")
    builder.button(text="📊 Статистика", callback_data="admin:stats")
    builder.button(text="👥 Управление администраторами", callback_data="admin:admins")
    builder.button(text="⚙️ Настройки", callback_data="admin:settings")
    builder.adjust(1)
    return builder.as_markup()


def admin_back_keyboard() -> InlineKeyboardMarkup:
    """Создает кнопку возврата в админ-панель."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin:menu")]]
    )


def admin_cancel_keyboard() -> InlineKeyboardMarkup:
    """Создает кнопку отмены текущего действия."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin:cancel")]]
    )


def faq_admin_list_keyboard(items: list[dict[str, Any]], action: str) -> InlineKeyboardMarkup:
    """Создает список FAQ-записей для редактирования или удаления."""
    builder = InlineKeyboardBuilder()
    for item in items:
        builder.button(text=_faq_label(item), callback_data=f"admin:{action}:{item['id']}")
    builder.button(text="⬅️ В админ-панель", callback_data="admin:menu")
    builder.adjust(1)
    return builder.as_markup()


def delete_confirm_keyboard(faq_id: int) -> InlineKeyboardMarkup:
    """Создает подтверждение удаления FAQ."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Удалить", callback_data=f"admin:delete_confirm:{faq_id}")
    builder.button(text="❌ Отмена", callback_data="admin:delete")
    builder.adjust(2)
    return builder.as_markup()


def admins_manage_keyboard() -> InlineKeyboardMarkup:
    """Создает меню управления администраторами."""
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить администратора", callback_data="admin:add_admin")
    builder.button(text="🗑 Удалить администратора", callback_data="admin:remove_admin")
    builder.button(text="🏅 Установить ранг", callback_data="admin:set_rank")
    builder.button(text="📝 Установить должность", callback_data="admin:set_title")
    builder.button(text="👁 Скрыть/показать админа", callback_data="admin:toggle_hidden")
    builder.button(text="⬅️ В админ-панель", callback_data="admin:menu")
    builder.adjust(1)
    return builder.as_markup()


def admins_remove_keyboard(admin_ids: list[int]) -> InlineKeyboardMarkup:
    """Создает список администраторов для удаления."""
    builder = InlineKeyboardBuilder()
    for index, admin_id in enumerate(admin_ids, start=1):
        builder.button(text=f"🗑 Администратор {index}", callback_data=f"admin:remove_admin:{admin_id}")
    builder.button(text="⬅️ Назад", callback_data="admin:admins")
    builder.adjust(1)
    return builder.as_markup()


def admins_select_keyboard(admins: list[dict[str, Any]], action: str) -> InlineKeyboardMarkup:
    """Создает список администраторов для выбора действия."""
    builder = InlineKeyboardBuilder()
    for admin in admins:
        admin_id = admin["id"]
        rank = admin.get("rank", "Админ")
        title = admin.get("title", "")
        is_hidden = admin.get("is_hidden", 0)
        hidden_mark = " 🔒" if is_hidden else ""
        label = f"{rank}"
        if title:
            label += f" ({title})"
        label += hidden_mark
        builder.button(text=label, callback_data=f"admin:{action}:{admin_id}")
    builder.button(text="⬅️ Назад", callback_data="admin:admins")
    builder.adjust(1)
    return builder.as_markup()


def settings_keyboard(settings: dict[str, str]) -> InlineKeyboardMarkup:
    """Создает меню настроек фильтров, наказаний и рекламы."""
    toggles = {
        "filter_bad_words": "Мат",
        "filter_spam": "Спам",
        "filter_links": "Ссылки",
        "filter_caps": "Капс",
        "ai_enabled": "AI",
    }
    builder = InlineKeyboardBuilder()
    for key, title in toggles.items():
        is_enabled = settings.get(key, "0") == "1"
        icon = "✅" if is_enabled else "❌"
        builder.button(text=f"{icon} {title}", callback_data=f"admin:setting_toggle:{key}")

    builder.button(text="⚠️ Лимит варнов", callback_data="admin:settings_warn_limit")
    builder.button(text="🔇 Мут за варны", callback_data="admin:settings_warn_mute")
    builder.button(text="⏱ Мут по умолчанию", callback_data="admin:settings_default_mute")
    builder.button(text="⛔ Бан по умолчанию", callback_data="admin:settings_default_ban")
    builder.button(text="📣 Получатель рекламы", callback_data="admin:settings_ads_id")
    builder.button(text="📌 Правила", callback_data="admin:settings_rules")
    builder.button(text="🚫 Слова фильтра", callback_data="admin:settings_bad_words")
    builder.button(text="⬅️ В админ-панель", callback_data="admin:menu")
    builder.adjust(2, 2, 1, 2, 2, 1, 1, 1)
    return builder.as_markup()
