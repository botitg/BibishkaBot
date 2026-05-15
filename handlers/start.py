"""Стартовые команды и пользовательские inline-меню."""

from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from keyboards.inline import (
    back_to_main_keyboard,
    faq_public_keyboard,
    main_menu_keyboard,
    private_start_keyboard,
    socials_keyboard,
)
from keyboards.reply import user_reply_keyboard
from states.admin_states import AdRequest
from utils.users import mention_by_id


router = Router()
logger = logging.getLogger(__name__)


async def _safe_edit(callback: CallbackQuery, text: str, reply_markup=None, parse_mode: str | None = "HTML") -> None:
    """Редактирует сообщение, а если нельзя — отправляет новое."""
    if callback.message is None:
        await callback.answer()
        return

    try:
        await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)


def _user_name(message: Message) -> str:
    """Возвращает безопасное имя пользователя для приветствия."""
    if message.from_user is None:
        return "друг"
    return escape(message.from_user.first_name or message.from_user.username or "друг")


def _faq_or_setting(query: str, setting_key: str, fallback: str) -> str:
    """Берет текст из FAQ по ключу или из настроек."""
    faq = db.find_faq_by_text(query)
    if faq:
        db.record_answer(int(faq["id"]))
        return str(faq["answer"])
    return db.get_setting(setting_key, fallback)


async def _format_staff(bot: Bot, chat_id: int | None = None) -> str:
    """Формирует текст состава админов бота и, если можно, чата."""
    bot_admins = db.list_admins()
    lines = ["👑 <b>Админский состав</b>\n"]
    if bot_admins:
        lines.append("<b>Админы бота:</b>")
        for admin_id in bot_admins:
            lines.append(f"• {await mention_by_id(bot, admin_id)}")
    else:
        lines.append("Админы бота пока не назначены.")

    if chat_id is not None:
        try:
            chat_admins = await bot.get_chat_administrators(chat_id)
            lines.append("\n<b>Админы чата:</b>")
            for admin in chat_admins[:20]:
                user = admin.user
                name = escape(user.full_name)
                lines.append(f"• <a href=\"tg://user?id={user.id}\">{name}</a>")
        except Exception:
            logger.exception("Не удалось получить админов чата")

    return "\n".join(lines)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Показывает приветствие и главное меню."""
    if message.from_user:
        db.add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)

    text = (
        f"✨ Привет, <b>{_user_name(message)}</b>!\n\n"
        "Я <b>BIBISHKA Admin Bot</b> — официальный помощник чата Бибишки.\n"
        "Помогаю с FAQ, составом, наградами, рекламой, модерацией и быстрыми ответами.\n\n"
        "Напиши <b>Бибишка, твой вопрос</b>, и я отвечу как локальный бесплатный AI-помощник."
    )
    await message.answer(text, reply_markup=main_menu_keyboard())
    # В личных сообщениях показываем компактную reply-клавиатуру с быстрыми командами
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("Быстрые команды:", reply_markup=user_reply_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Показывает список команд."""
    text = (
        "🧭 <b>Команды BIBISHKA Admin Bot</b>\n\n"
        "/start — главное меню\n"
        "/help — помощь\n"
        "/rules — правила чата\n"
        "/staff — состав админов\n"
        "/awards — награды пользователя\n"
        "/ads — отправить рекламное предложение\n\n"
        "🏆 <b>Активность</b>\n"
        "/award — выдать награду ответом на сообщение\n"
        "/unaward ID — удалить награду\n\n"
        "🛡 <b>Модерация</b>\n"
        "/warn причина — предупреждение\n"
        "/unwarn — снять предупреждение\n"
        "/mute 1m/1h/1d причина — мут\n"
        "/unmute — снять мут\n"
        "/ban 1m/1h/1d причина — бан на время или навсегда без времени\n"
        "/unban USER_ID — разбан\n"
        "/kick причина — кик\n\n"
        "⚙️ /admin — админ-панель"
    )
    await message.answer(text)


@router.callback_query(F.data == "main:back")
async def callback_main_back(callback: CallbackQuery, state: FSMContext) -> None:
    """Возвращает в главное меню."""
    await callback.answer()
    await state.clear()
    await _safe_edit(
        callback,
        "✨ <b>BIBISHKA Admin Bot</b>\n\nВыбирай нужный раздел:",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(F.data == "main:faq")
async def callback_main_faq(callback: CallbackQuery) -> None:
    """Показывает список FAQ."""
    await callback.answer()
    items = db.list_faq()
    if not items:
        await _safe_edit(
            callback,
            "FAQ пока пуст. Админы могут добавить вопросы через /admin.",
            reply_markup=back_to_main_keyboard(),
        )
        return

    text = "❓ <b>FAQ</b>\n\nВыбери раздел или просто напиши вопрос в чат."
    await _safe_edit(callback, text, reply_markup=faq_public_keyboard(items))


@router.callback_query(F.data == "main:socials")
async def callback_main_socials(callback: CallbackQuery) -> None:
    """Показывает соцсети."""
    await callback.answer()
    text = _faq_or_setting("Соцсети", "socials_text", "🌐 Соцсети Бибишки скоро появятся.")
    await _safe_edit(callback, text, reply_markup=socials_keyboard(), parse_mode=None)


@router.callback_query(F.data == "main:streams")
async def callback_main_streams(callback: CallbackQuery) -> None:
    """Показывает расписание стримов."""
    await callback.answer()
    text = _faq_or_setting("Стрим", "streams_text", "🎥 Расписание стримов скоро появится.")
    await _safe_edit(callback, text, reply_markup=back_to_main_keyboard(), parse_mode=None)


@router.callback_query(F.data == "main:ads")
async def callback_main_ads(callback: CallbackQuery, state: FSMContext) -> None:
    """Запускает отправку рекламного предложения ответственному ID."""
    await callback.answer()
    await state.set_state(AdRequest.content)
    text = (
        f"{db.get_setting('ads_text')}\n\n"
        "Отправь следующим сообщением текст, фото, видео или файл с предложением. "
        "Я перешлю его ответственному за рекламу."
    )
    await _safe_edit(callback, text, reply_markup=back_to_main_keyboard(), parse_mode=None)


@router.callback_query(F.data == "main:staff")
async def callback_main_staff(callback: CallbackQuery, bot: Bot) -> None:
    """Показывает состав администраторов."""
    await callback.answer()
    chat_id = (
        callback.message.chat.id
        if callback.message and callback.message.chat.type != ChatType.PRIVATE
        else None
    )
    text = await _format_staff(bot, chat_id)
    await _safe_edit(callback, text, reply_markup=back_to_main_keyboard())


@router.callback_query(F.data == "game:join")
async def callback_game_join(callback: CallbackQuery, bot: Bot) -> None:
    """При нажатии на кнопку игры в группе — предлагаем написать боту в ЛС."""
    await callback.answer()
    me = await bot.get_me()
    username = getattr(me, "username", None)
    if username:
        await callback.message.answer(
            "Чтобы присоединиться к игре, напишите боту в личные сообщения:",
            reply_markup=private_start_keyboard(username),
        )
    else:
        await callback.message.answer("Чтобы присоединиться к игре, напишите боту в личку.")


@router.message(Command("join"))
async def cmd_join(message: Message, bot: Bot) -> None:
    """Команда /join — если в группе, просим открыть ЛС, если в личке — регистрируем участника."""
    if message.chat.type != ChatType.PRIVATE:
        me = await bot.get_me()
        username = getattr(me, "username", None)
        if username:
            await message.answer(
                "Для участия нажмите кнопку и напишите боту в личку:",
                reply_markup=private_start_keyboard(username),
            )
        else:
            await message.answer("Для участия напишите боту в личные сообщения.")
        return

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    added = db.add_game_participant(message.from_user.id, message.from_user.username)
    if added:
        await message.answer("✅ Вы успешно присоединились к игре! Удачи!", reply_markup=back_to_main_keyboard())
    else:
        await message.answer("ℹ️ Вы уже участвуете в игре.", reply_markup=back_to_main_keyboard())


@router.callback_query(F.data == "main:awards")
async def callback_main_awards(callback: CallbackQuery) -> None:
    """Показывает подсказку по наградам."""
    await callback.answer()
    text = (
        "🏆 <b>Награды</b>\n\n"
        "Награды выдают администраторы командой <code>/award</code> ответом на сообщение.\n"
        "Посмотреть свои награды можно командой <code>/awards</code>."
    )
    await _safe_edit(callback, text, reply_markup=back_to_main_keyboard())


@router.callback_query(F.data.startswith("social:"))
async def callback_social_item(callback: CallbackQuery) -> None:
    """Отвечает на кнопки соцсетей через FAQ-поиск."""
    await callback.answer()
    query = callback.data.split(":", 1)[1] if callback.data else ""
    labels = {
        "tiktok": "TikTok",
        "instagram": "Instagram",
        "telegram": "Telegram",
    }
    faq = db.find_faq_by_text(labels.get(query, query))
    if faq:
        db.record_answer(int(faq["id"]))
        await _safe_edit(callback, str(faq["answer"]), reply_markup=back_to_main_keyboard(), parse_mode=None)
        return

    await _safe_edit(
        callback,
        "🌐 Ссылка пока не добавлена. Админы могут обновить FAQ через /admin.",
        reply_markup=back_to_main_keyboard(),
        parse_mode=None,
    )
