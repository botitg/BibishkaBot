"""Админ-панель для FAQ, админов, статистики и настроек."""

from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from keyboards.inline import (
    admin_back_keyboard,
    admin_cancel_keyboard,
    admin_menu_keyboard,
    admins_manage_keyboard,
    admins_remove_keyboard,
    delete_confirm_keyboard,
    faq_admin_list_keyboard,
    settings_keyboard,
)
from states.admin_states import AdminManage, FAQAdd, FAQEdit, SettingsManage
from utils.filters import AdminFilter
from utils.users import mention_by_id


router = Router()
logger = logging.getLogger(__name__)


async def _safe_edit(callback: CallbackQuery, text: str, reply_markup=None, parse_mode: str | None = "HTML") -> None:
    """Редактирует сообщение или отправляет новое, если редактирование невозможно."""
    if callback.message is None:
        await callback.answer()
        return

    try:
        await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)


def _cut(text: str, limit: int = 120) -> str:
    """Обрезает длинный текст для компактного списка."""
    text = text.strip()
    return text if len(text) <= limit else f"{text[:limit - 3]}..."


def _minutes_from_setting(key: str, default_seconds: int) -> int:
    """Возвращает настройку в минутах."""
    return max(0, db.get_int_setting(key, default_seconds) // 60)


def _format_faq_list(items: list[dict]) -> str:
    """Форматирует FAQ для просмотра в админке."""
    if not items:
        return "FAQ пока пуст."

    lines = ["📋 <b>Список вопросов</b>"]
    for item in items:
        lines.append(
            f"\n<b>#{item['id']}</b> {escape(_cut(str(item['keywords']), 80))}\n"
            f"Ответ: {escape(_cut(str(item['answer']), 140))}"
        )
    return "\n".join(lines)


async def _show_admin_menu(target: Message | CallbackQuery) -> None:
    """Показывает главное меню админ-панели."""
    text = "🛡 <b>Админ-панель BIBISHKA Admin Bot</b>\n\nВыберите действие:"
    if isinstance(target, CallbackQuery):
        await target.answer()
        await _safe_edit(target, text, reply_markup=admin_menu_keyboard())
    else:
        await target.answer(text, reply_markup=admin_menu_keyboard())


async def _show_settings(callback: CallbackQuery, bot: Bot) -> None:
    """Показывает текущие настройки бота."""
    settings = db.list_settings()
    warn_mute = _minutes_from_setting("warn_mute_seconds", 600)
    default_mute = _minutes_from_setting("default_mute_seconds", 600)
    default_ban = _minutes_from_setting("default_ban_seconds", 0)
    default_ban_text = "навсегда" if default_ban == 0 else f"{default_ban} мин."
    ads_receiver_id = db.get_int_setting("ads_receiver_id", 8436225978)
    ads_receiver = await mention_by_id(bot, ads_receiver_id, "получатель рекламы")

    text = (
        "⚙️ <b>Настройки</b>\n\n"
        f"🚫 Мат: {'вкл' if settings.get('filter_bad_words') == '1' else 'выкл'}\n"
        f"🔁 Спам: {'вкл' if settings.get('filter_spam') == '1' else 'выкл'}\n"
        f"🔗 Ссылки: {'вкл' if settings.get('filter_links') == '1' else 'выкл'}\n"
        f"🔠 Капс: {'вкл' if settings.get('filter_caps') == '1' else 'выкл'}\n"
        f"🤖 AI: {'вкл' if settings.get('ai_enabled') == '1' else 'выкл'}\n\n"
        f"⚠️ Варны: <b>{escape(settings.get('max_warnings', '3'))}/"
        f"{escape(settings.get('max_warnings', '3'))}</b>\n"
        f"🔇 Мут за лимит варнов: <b>{warn_mute} мин.</b>\n"
        f"⏱ Мут по умолчанию: <b>{default_mute} мин.</b>\n"
        f"⛔ Бан по умолчанию: <b>{default_ban_text}</b>\n"
        f"📣 Получатель рекламы: {ads_receiver}"
    )
    await _safe_edit(callback, text, reply_markup=settings_keyboard(settings))


@router.message(Command("admin"), AdminFilter())
async def cmd_admin(message: Message) -> None:
    """Открывает админ-панель."""
    await _show_admin_menu(message)


@router.message(Command("admin"))
async def cmd_admin_denied(message: Message) -> None:
    """Сообщает об отсутствии доступа."""
    await message.answer("⛔ У тебя нет доступа к админ-панели.")


@router.message(Command("cancel"), AdminFilter())
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Отменяет текущий FSM-сценарий."""
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=admin_menu_keyboard())


@router.callback_query(AdminFilter(), F.data == "admin:cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """Отменяет текущий сценарий по кнопке."""
    await state.clear()
    await _show_admin_menu(callback)


@router.callback_query(AdminFilter(), F.data == "admin:menu")
async def callback_admin_menu(callback: CallbackQuery, state: FSMContext) -> None:
    """Возвращает в главное меню админки."""
    await state.clear()
    await _show_admin_menu(callback)


@router.callback_query(AdminFilter(), F.data == "admin:list")
async def callback_admin_list(callback: CallbackQuery) -> None:
    """Показывает список FAQ."""
    await callback.answer()
    await _safe_edit(callback, _format_faq_list(db.list_faq()), reply_markup=admin_back_keyboard())


@router.callback_query(AdminFilter(), F.data == "admin:add")
async def callback_admin_add(callback: CallbackQuery, state: FSMContext) -> None:
    """Запускает добавление FAQ."""
    await callback.answer()
    await state.set_state(FAQAdd.keywords)
    await _safe_edit(
        callback,
        "➕ <b>Добавление FAQ</b>\n\nОтправьте ключевые слова через запятую.\nПример: <code>Возраст, сколько лет, лет</code>",
        reply_markup=admin_cancel_keyboard(),
    )


@router.message(FAQAdd.keywords, AdminFilter())
async def state_add_keywords(message: Message, state: FSMContext) -> None:
    """Сохраняет ключи новой FAQ-записи."""
    if not message.text or not message.text.strip():
        await message.answer("Ключевые слова не должны быть пустыми.", reply_markup=admin_cancel_keyboard())
        return

    await state.update_data(keywords=message.text.strip())
    await state.set_state(FAQAdd.answer)
    await message.answer("Теперь отправьте ответ для пользователей.", reply_markup=admin_cancel_keyboard())


@router.message(FAQAdd.answer, AdminFilter())
async def state_add_answer(message: Message, state: FSMContext) -> None:
    """Создает новую FAQ-запись."""
    if not message.text or not message.text.strip():
        await message.answer("Ответ не должен быть пустым.", reply_markup=admin_cancel_keyboard())
        return

    data = await state.get_data()
    faq_id = db.add_faq(str(data["keywords"]), message.text.strip())
    await state.clear()
    await message.answer(f"✅ FAQ добавлен. ID: <b>#{faq_id}</b>", reply_markup=admin_menu_keyboard())


@router.callback_query(AdminFilter(), F.data == "admin:edit")
async def callback_admin_edit(callback: CallbackQuery) -> None:
    """Показывает FAQ для редактирования."""
    await callback.answer()
    items = db.list_faq()
    if not items:
        await _safe_edit(callback, "FAQ пока пуст.", reply_markup=admin_back_keyboard())
        return

    await _safe_edit(
        callback,
        "✏️ <b>Изменение ответа</b>\n\nВыберите вопрос:",
        reply_markup=faq_admin_list_keyboard(items, "edit"),
    )


@router.callback_query(AdminFilter(), F.data.startswith("admin:edit:"))
async def callback_admin_edit_pick(callback: CallbackQuery, state: FSMContext) -> None:
    """Запоминает выбранный FAQ и просит новый ответ."""
    await callback.answer()
    try:
        faq_id = int(callback.data.rsplit(":", 1)[1]) if callback.data else 0
    except ValueError:
        await _safe_edit(callback, "Некорректный ID.", reply_markup=admin_back_keyboard())
        return

    faq = db.get_faq(faq_id)
    if faq is None:
        await _safe_edit(callback, "FAQ не найден.", reply_markup=admin_back_keyboard())
        return

    await state.update_data(faq_id=faq_id)
    await state.set_state(FAQEdit.answer)
    text = (
        f"✏️ <b>Новый ответ для #{faq_id}</b>\n\n"
        f"<b>Ключи:</b> {escape(str(faq['keywords']))}\n\n"
        f"<b>Текущий ответ:</b>\n{escape(str(faq['answer']))}\n\n"
        "Отправьте новый текст."
    )
    await _safe_edit(callback, text, reply_markup=admin_cancel_keyboard())


@router.message(FAQEdit.answer, AdminFilter())
async def state_edit_answer(message: Message, state: FSMContext) -> None:
    """Обновляет ответ FAQ."""
    if not message.text or not message.text.strip():
        await message.answer("Ответ не должен быть пустым.", reply_markup=admin_cancel_keyboard())
        return

    data = await state.get_data()
    faq_id = int(data["faq_id"])
    updated = db.update_faq_answer(faq_id, message.text.strip())
    await state.clear()
    await message.answer(
        f"✅ Ответ для <b>#{faq_id}</b> обновлен." if updated else "FAQ не найден.",
        reply_markup=admin_menu_keyboard(),
    )


@router.callback_query(AdminFilter(), F.data == "admin:delete")
async def callback_admin_delete(callback: CallbackQuery) -> None:
    """Показывает FAQ для удаления."""
    await callback.answer()
    items = db.list_faq()
    if not items:
        await _safe_edit(callback, "FAQ пока пуст.", reply_markup=admin_back_keyboard())
        return

    await _safe_edit(
        callback,
        "🗑 <b>Удаление FAQ</b>\n\nВыберите запись:",
        reply_markup=faq_admin_list_keyboard(items, "delete"),
    )


@router.callback_query(AdminFilter(), F.data.startswith("admin:delete:"))
async def callback_admin_delete_pick(callback: CallbackQuery) -> None:
    """Просит подтверждение удаления FAQ."""
    await callback.answer()
    try:
        faq_id = int(callback.data.rsplit(":", 1)[1]) if callback.data else 0
    except ValueError:
        await _safe_edit(callback, "Некорректный ID.", reply_markup=admin_back_keyboard())
        return

    faq = db.get_faq(faq_id)
    if faq is None:
        await _safe_edit(callback, "FAQ не найден.", reply_markup=admin_back_keyboard())
        return

    text = (
        f"🗑 Удалить <b>#{faq_id}</b>?\n\n"
        f"<b>Ключи:</b> {escape(str(faq['keywords']))}\n"
        f"<b>Ответ:</b> {escape(_cut(str(faq['answer']), 300))}"
    )
    await _safe_edit(callback, text, reply_markup=delete_confirm_keyboard(faq_id))


@router.callback_query(AdminFilter(), F.data.startswith("admin:delete_confirm:"))
async def callback_admin_delete_confirm(callback: CallbackQuery) -> None:
    """Удаляет FAQ после подтверждения."""
    await callback.answer()
    try:
        faq_id = int(callback.data.rsplit(":", 1)[1]) if callback.data else 0
    except ValueError:
        await _safe_edit(callback, "Некорректный ID.", reply_markup=admin_back_keyboard())
        return

    if db.delete_faq(faq_id):
        await _safe_edit(callback, f"✅ FAQ <b>#{faq_id}</b> удален.", reply_markup=admin_back_keyboard())
    else:
        await _safe_edit(callback, "FAQ уже удален.", reply_markup=admin_back_keyboard())


@router.callback_query(AdminFilter(), F.data == "admin:stats")
async def callback_admin_stats(callback: CallbackQuery) -> None:
    """Показывает статистику."""
    await callback.answer()
    stats = db.get_statistics()
    popular = []
    for item in stats["popular"]:
        first_key = str(item["keywords"]).split(",")[0]
        popular.append(f"• #{item['id']} {escape(_cut(first_key, 40))}: {item['hits']}")

    text = (
        "📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{stats['users_count']}</b>\n"
        f"❓ FAQ-записей: <b>{stats['faq_count']}</b>\n"
        f"🏆 Наград: <b>{stats['awards_count']}</b>\n"
        f"💬 Ответов за день: <b>{stats['today_answers']}</b>\n\n"
        "<b>Популярные вопросы:</b>\n"
        f"{chr(10).join(popular) if popular else 'Пока нет данных.'}"
    )
    await _safe_edit(callback, text, reply_markup=admin_back_keyboard())


@router.callback_query(AdminFilter(), F.data == "admin:admins")
async def callback_admins(callback: CallbackQuery, bot: Bot) -> None:
    """Показывает управление администраторами."""
    await callback.answer()
    admin_ids = db.list_admins()
    admin_lines = [f"• {await mention_by_id(bot, admin_id)}" for admin_id in admin_ids]
    ids_text = "\n".join(admin_lines) or "Пока нет администраторов."
    await _safe_edit(callback, f"👥 <b>Администраторы</b>\n\n{ids_text}", reply_markup=admins_manage_keyboard())


@router.callback_query(AdminFilter(), F.data == "admin:add_admin")
async def callback_add_admin(callback: CallbackQuery, state: FSMContext) -> None:
    """Запускает добавление администратора."""
    await callback.answer()
    await state.set_state(AdminManage.add_admin_id)
    await _safe_edit(callback, "Отправьте Telegram ID нового администратора.", reply_markup=admin_cancel_keyboard())


@router.message(AdminManage.add_admin_id, AdminFilter())
async def state_add_admin(message: Message, state: FSMContext, bot: Bot) -> None:
    """Добавляет администратора по ID."""
    if not message.text or not message.text.strip().isdigit():
        await message.answer("ID должен быть числом.", reply_markup=admin_cancel_keyboard())
        return

    admin_id = int(message.text.strip())
    db.add_admin(admin_id)
    await state.clear()
    admin_label = await mention_by_id(bot, admin_id, "администратор")
    await message.answer(f"✅ Администратор {admin_label} добавлен.", reply_markup=admin_menu_keyboard())


@router.callback_query(AdminFilter(), F.data == "admin:remove_admin")
async def callback_remove_admin(callback: CallbackQuery) -> None:
    """Показывает админов для удаления."""
    await callback.answer()
    admin_ids = db.list_admins()
    if not admin_ids:
        await _safe_edit(callback, "Список администраторов пуст.", reply_markup=admin_back_keyboard())
        return

    await _safe_edit(callback, "Выберите администратора для удаления:", reply_markup=admins_remove_keyboard(admin_ids))


@router.callback_query(AdminFilter(), F.data.startswith("admin:remove_admin:"))
async def callback_remove_admin_pick(callback: CallbackQuery, bot: Bot) -> None:
    """Удаляет выбранного администратора."""
    await callback.answer()
    try:
        admin_id = int(callback.data.rsplit(":", 1)[1]) if callback.data else 0
    except ValueError:
        await _safe_edit(callback, "Некорректный ID.", reply_markup=admin_back_keyboard())
        return

    admin_label = await mention_by_id(bot, admin_id, "администратор")
    if db.remove_admin(admin_id):
        await _safe_edit(callback, f"✅ Администратор {admin_label} удален.", reply_markup=admin_back_keyboard())
    else:
        await _safe_edit(callback, "Администратор не найден.", reply_markup=admin_back_keyboard())


@router.callback_query(AdminFilter(), F.data == "admin:settings")
async def callback_settings(callback: CallbackQuery, bot: Bot) -> None:
    """Показывает настройки."""
    await callback.answer()
    await _show_settings(callback, bot)


@router.callback_query(AdminFilter(), F.data.startswith("admin:setting_toggle:"))
async def callback_toggle_setting(callback: CallbackQuery, bot: Bot) -> None:
    """Переключает булевую настройку."""
    await callback.answer()
    key = callback.data.rsplit(":", 1)[1] if callback.data else ""
    allowed = {"filter_bad_words", "filter_spam", "filter_links", "filter_caps", "ai_enabled"}
    if key not in allowed:
        await _safe_edit(callback, "Неизвестная настройка.", reply_markup=admin_back_keyboard())
        return

    db.set_setting(key, "0" if db.get_bool_setting(key) else "1")
    await _show_settings(callback, bot)


@router.callback_query(AdminFilter(), F.data == "admin:settings_rules")
async def callback_settings_rules(callback: CallbackQuery, state: FSMContext) -> None:
    """Запускает изменение правил."""
    await callback.answer()
    await state.set_state(SettingsManage.rules_text)
    current = db.get_setting("rules_text")
    await _safe_edit(callback, f"📌 <b>Текущие правила:</b>\n{escape(current)}\n\nОтправьте новый текст.", reply_markup=admin_cancel_keyboard())


@router.message(SettingsManage.rules_text, AdminFilter())
async def state_rules_text(message: Message, state: FSMContext) -> None:
    """Сохраняет правила."""
    if not message.text or not message.text.strip():
        await message.answer("Текст правил не должен быть пустым.", reply_markup=admin_cancel_keyboard())
        return

    db.set_setting("rules_text", message.text.strip())
    await state.clear()
    await message.answer("✅ Правила обновлены.", reply_markup=admin_menu_keyboard())


@router.callback_query(AdminFilter(), F.data == "admin:settings_bad_words")
async def callback_settings_bad_words(callback: CallbackQuery, state: FSMContext) -> None:
    """Запускает изменение списка мата."""
    await callback.answer()
    await state.set_state(SettingsManage.bad_words)
    current = db.get_setting("bad_words")
    await _safe_edit(callback, f"🚫 <b>Слова фильтра:</b>\n{escape(current)}\n\nОтправьте слова через запятую.", reply_markup=admin_cancel_keyboard())


@router.message(SettingsManage.bad_words, AdminFilter())
async def state_bad_words(message: Message, state: FSMContext) -> None:
    """Сохраняет список мата."""
    if not message.text:
        await message.answer("Отправьте список слов текстом.", reply_markup=admin_cancel_keyboard())
        return

    db.set_setting("bad_words", message.text.strip())
    await state.clear()
    await message.answer("✅ Фильтр мата обновлен.", reply_markup=admin_menu_keyboard())


@router.callback_query(AdminFilter(), F.data == "admin:settings_warn_limit")
async def callback_warn_limit(callback: CallbackQuery, state: FSMContext) -> None:
    """Запускает изменение лимита варнов."""
    await callback.answer()
    await state.set_state(SettingsManage.warn_limit)
    await _safe_edit(callback, "⚠️ Отправьте новый лимит варнов числом. Например: <code>3</code>", reply_markup=admin_cancel_keyboard())


@router.message(SettingsManage.warn_limit, AdminFilter())
async def state_warn_limit(message: Message, state: FSMContext) -> None:
    """Сохраняет лимит варнов."""
    if not message.text or not message.text.strip().isdigit() or int(message.text.strip()) <= 0:
        await message.answer("Введите положительное число.", reply_markup=admin_cancel_keyboard())
        return

    db.set_setting("max_warnings", message.text.strip())
    await state.clear()
    await message.answer("✅ Лимит варнов обновлен.", reply_markup=admin_menu_keyboard())


@router.callback_query(AdminFilter(), F.data == "admin:settings_warn_mute")
async def callback_warn_mute(callback: CallbackQuery, state: FSMContext) -> None:
    """Запускает изменение мута за лимит варнов."""
    await callback.answer()
    await state.set_state(SettingsManage.warn_mute_minutes)
    await _safe_edit(callback, "🔇 На сколько минут мутить за лимит варнов? Например: <code>10</code>", reply_markup=admin_cancel_keyboard())


@router.message(SettingsManage.warn_mute_minutes, AdminFilter())
async def state_warn_mute(message: Message, state: FSMContext) -> None:
    """Сохраняет мут за лимит варнов."""
    if not message.text or not message.text.strip().isdigit() or int(message.text.strip()) <= 0:
        await message.answer("Введите положительное число минут.", reply_markup=admin_cancel_keyboard())
        return

    db.set_setting("warn_mute_seconds", str(int(message.text.strip()) * 60))
    await state.clear()
    await message.answer("✅ Мут за варны обновлен.", reply_markup=admin_menu_keyboard())


@router.callback_query(AdminFilter(), F.data == "admin:settings_default_mute")
async def callback_default_mute(callback: CallbackQuery, state: FSMContext) -> None:
    """Запускает изменение мута по умолчанию."""
    await callback.answer()
    await state.set_state(SettingsManage.default_mute_minutes)
    await _safe_edit(callback, "⏱ Мут по умолчанию в минутах. Например: <code>10</code>", reply_markup=admin_cancel_keyboard())


@router.message(SettingsManage.default_mute_minutes, AdminFilter())
async def state_default_mute(message: Message, state: FSMContext) -> None:
    """Сохраняет мут по умолчанию."""
    if not message.text or not message.text.strip().isdigit() or int(message.text.strip()) <= 0:
        await message.answer("Введите положительное число минут.", reply_markup=admin_cancel_keyboard())
        return

    db.set_setting("default_mute_seconds", str(int(message.text.strip()) * 60))
    await state.clear()
    await message.answer("✅ Мут по умолчанию обновлен.", reply_markup=admin_menu_keyboard())


@router.callback_query(AdminFilter(), F.data == "admin:settings_default_ban")
async def callback_default_ban(callback: CallbackQuery, state: FSMContext) -> None:
    """Запускает изменение бана по умолчанию."""
    await callback.answer()
    await state.set_state(SettingsManage.default_ban_minutes)
    await _safe_edit(callback, "⛔ Бан по умолчанию в минутах. <code>0</code> — навсегда.", reply_markup=admin_cancel_keyboard())


@router.message(SettingsManage.default_ban_minutes, AdminFilter())
async def state_default_ban(message: Message, state: FSMContext) -> None:
    """Сохраняет бан по умолчанию."""
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите число минут. 0 означает навсегда.", reply_markup=admin_cancel_keyboard())
        return

    db.set_setting("default_ban_seconds", str(int(message.text.strip()) * 60))
    await state.clear()
    await message.answer("✅ Бан по умолчанию обновлен.", reply_markup=admin_menu_keyboard())


@router.callback_query(AdminFilter(), F.data == "admin:settings_ads_id")
async def callback_ads_id(callback: CallbackQuery, state: FSMContext) -> None:
    """Запускает изменение ID получателя рекламы."""
    await callback.answer()
    await state.set_state(SettingsManage.ads_receiver_id)
    await _safe_edit(callback, "📣 Отправьте Telegram ID, куда будут приходить заявки рекламы.", reply_markup=admin_cancel_keyboard())


@router.message(SettingsManage.ads_receiver_id, AdminFilter())
async def state_ads_id(message: Message, state: FSMContext) -> None:
    """Сохраняет ID получателя рекламы."""
    if not message.text or not message.text.strip().isdigit():
        await message.answer("ID должен быть числом.", reply_markup=admin_cancel_keyboard())
        return

    db.set_setting("ads_receiver_id", message.text.strip())
    await state.clear()
    await message.answer("✅ Получатель рекламы обновлен.", reply_markup=admin_menu_keyboard())


@router.callback_query(F.data.startswith("admin:"))
async def callback_admin_denied(callback: CallbackQuery) -> None:
    """Блокирует нажатия админ-кнопок без доступа."""
    await callback.answer("⛔ Нет доступа.", show_alert=True)
