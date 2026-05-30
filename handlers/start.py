"""Стартовые команды и пользовательские inline-меню (игра удалена)."""

from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, CommandObject
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
from utils.filters import AdminFilter


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
    return escape(message.from_user.full_name or message.from_user.first_name or "друг")


def _faq_or_setting(query: str, setting_key: str, fallback: str) -> str:
    """Берет текст из FAQ по ключу или из настроек."""
    faq = db.find_faq_by_text(query)
    if faq:
        db.record_answer(int(faq["id"]))
        return str(faq["answer"])
    return db.get_setting(setting_key, fallback)


def _place(index: int) -> str:
    """Возвращает красивый маркер места в топе."""
    medals = ["🥇", "🥈", "🥉"]
    return medals[index - 1] if index <= len(medals) else f"{index}."


def _format_duration(seconds: int) -> str:
    """Форматирует длительность для топа браков."""
    minutes = max(0, int(seconds)) // 60
    hours = minutes // 60
    days = hours // 24
    if days:
        return f"{days}д {hours % 24}ч"
    if hours:
        return f"{hours}ч {minutes % 60}м"
    if minutes:
        return f"{minutes}м"
    return f"{seconds}с"


async def _build_top_text(bot: Bot, chat_id: int | None) -> str:
    """Собирает понятное меню топов."""
    lines = [
        "📊 <b>Топы чата</b>",
        "<i>/top — это меню, /marriages — топы браков, /awards — твои награды</i>\n",
    ]

    top_all = db.top_senders(chat_id=chat_id, limit=5)
    lines.append("<b>💬 Сообщения за всё время</b>")
    if top_all:
        for index, row in enumerate(top_all, start=1):
            label = await mention_by_id(bot, int(row["user_id"]))
            lines.append(f"{_place(index)} {label} — <b>{int(row.get('cnt', 0))}</b>")
    else:
        lines.append("Пока нет статистики сообщений.")

    top_week = db.top_senders_in_period(days=7, chat_id=chat_id, limit=5)
    lines.append("\n<b>🔥 Активность за 7 дней</b>")
    if top_week:
        for index, row in enumerate(top_week, start=1):
            label = await mention_by_id(bot, int(row["user_id"]))
            lines.append(f"{_place(index)} {label} — <b>{int(row.get('cnt', 0))}</b>")
    else:
        lines.append("За неделю пока пусто.")

    top_points = db.top_award_points(chat_id=chat_id, limit=5)
    lines.append("\n<b>🏆 Очки наград</b>")
    if top_points:
        for index, row in enumerate(top_points, start=1):
            label = await mention_by_id(bot, int(row["user_id"]))
            points = int(row.get("points", 0))
            count = int(row.get("cnt", 0))
            lines.append(f"{_place(index)} {label} — <b>{points}</b> очков · {count} наград")
    else:
        lines.append("Наград пока нет.")

    return "\n".join(lines)


async def _build_marriages_text(bot: Bot, chat_id: int | None) -> str:
    """Собирает понятное меню браков."""
    lines = [
        "💍 <b>Браки</b>",
        "<i>/marry ответом — сделать предложение, /divorce ID — расторгнуть конкретный брак</i>\n",
    ]

    top_marriages = db.top_marriages_by_duration(chat_id=chat_id, limit=5)
    lines.append("<b>Самые долгие пары</b>")
    if top_marriages:
        for index, marriage in enumerate(top_marriages, start=1):
            u1_label = await mention_by_id(bot, int(marriage["user1_id"]))
            u2_label = await mention_by_id(bot, int(marriage["user2_id"]))
            duration = _format_duration(int(marriage.get("duration", 0)))
            lines.append(f"{_place(index)} {u1_label} + {u2_label}\n   <b>{duration}</b> · <code>#{marriage['id']}</code>")
    else:
        lines.append("Пока нет браков.")

    top_users = db.top_users_by_marriage_count(chat_id=chat_id, limit=5)
    lines.append("\n<b>Самые семейные участники</b>")
    if top_users:
        for index, row in enumerate(top_users, start=1):
            label = await mention_by_id(bot, int(row["user_id"]))
            lines.append(f"{index}. {label} — <b>{int(row.get('cnt', 0))}</b> браков")
    else:
        lines.append("Пока нет данных.")

    return "\n".join(lines)


async def _format_staff(bot: Bot, chat_id: int | None = None, viewer_id: int | None = None) -> str:
    """Формирует текст состава админов бота и, если можно, чата.

    Скрытые админы не показываются в публичном меню — только в админ-панели.
    """
    # Показываем скрытых админов только если вызывающий пользователь — админ бота
    show_hidden = False
    if viewer_id is not None and db.is_admin(viewer_id):
        show_hidden = True

    bot_admins = db.list_admins(include_hidden=show_hidden)
    lines = ["👑 <b>Админский состав</b>\n"]
    if bot_admins:
        lines.append("<b>Админы бота:</b>")
        for admin in bot_admins:
            admin_id = admin.get("id")
            rank = admin.get("rank", "Админ")
            title = admin.get("title", "")
            is_hidden = admin.get("is_hidden", 0)
            mention = await mention_by_id(bot, admin_id)
            hidden_mark = " 🔒" if is_hidden else ""
            if title:
                lines.append(f"• {mention} — <b>{rank}</b> ({escape(title)}){hidden_mark}")
            else:
                lines.append(f"• {mention} — <b>{rank}</b>{hidden_mark}")
    else:
        lines.append("Админы бота пока не назначены.")

    if chat_id is not None:
        try:
            chat_admins = await bot.get_chat_administrators(chat_id)
            # Получаем список скрытых админов из БД, чтобы при необходимости скрыть их в списке чата
            hidden_db_admins = {a["id"] for a in db.list_admins(include_hidden=True) if a.get("is_hidden")}
            lines.append("\n<b>Админы чата:</b>")
            count = 0
            for admin in chat_admins:
                if count >= 20:
                    break
                user = admin.user
                # Если админ скрыт в БД и вызывающий не админ — пропускаем
                if user and user.id in hidden_db_admins and not show_hidden:
                    continue
                name = escape(user.full_name)
                # Пометка для скрытых админов, если вызывающий — админ
                hidden_mark = " 🔒" if user and user.id in hidden_db_admins else ""
                lines.append(f"• <a href=\"tg://user?id={user.id}\">{name}</a>{hidden_mark}")
                count += 1
        except Exception:
            logger.exception("Не удалось получить админов чата")

    return "\n".join(lines)


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, command: CommandObject | None = None) -> None:
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
    viewer_id = callback.from_user.id if callback.from_user else None
    text = await _format_staff(bot, chat_id, viewer_id)
    await _safe_edit(callback, text, reply_markup=back_to_main_keyboard())


@router.callback_query(F.data == "game:join")
async def callback_game_join(callback: CallbackQuery, bot: Bot) -> None:
    """Кнопка игры — теперь информирует, что игра удалена."""
    await callback.answer()
    await callback.answer("⚠️ Игра удалена из бота.", show_alert=True)


@router.message(Command("join"))
async def cmd_join(message: Message, bot: Bot, command: CommandObject | None = None) -> None:
    await message.answer("⚠️ Эта команда устарела — игра удалена.")


@router.message(Command("startgame"))
async def cmd_startgame(message: Message, bot: Bot) -> None:
    await message.answer("⚠️ Игровой функционал удалён из бота.")


@router.callback_query(F.data.startswith("game:participants:"))
async def callback_game_participants(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    await callback.answer("⚠️ Игровой раздел удалён.", show_alert=True)


@router.message(Command("lynch"), AdminFilter())
async def cmd_lynch(message: Message, bot: Bot, command: CommandObject | None = None) -> None:
    await message.answer("⚠️ Команда удалена вместе с игрой.")


@router.message(Command("endgame"), AdminFilter())
async def cmd_endgame(message: Message, bot: Bot, command: CommandObject | None = None) -> None:
    await message.answer("⚠️ Команда удалена вместе с игрой.")


@router.message(Command("top"))
async def cmd_top(message: Message, bot: Bot) -> None:
    """Показывает красивое меню топов."""
    chat_id = None if message.chat.type == ChatType.PRIVATE else message.chat.id
    await message.answer(await _build_top_text(bot, chat_id))


@router.callback_query(F.data == "main:top")
async def callback_main_top(callback: CallbackQuery, bot: Bot) -> None:
    """Показывает топы из главного меню."""
    await callback.answer()
    chat_id = callback.message.chat.id if callback.message and callback.message.chat.type != ChatType.PRIVATE else None
    await _safe_edit(callback, await _build_top_text(bot, chat_id), reply_markup=back_to_main_keyboard())


@router.callback_query(F.data == "main:marriages")
async def callback_main_marriages(callback: CallbackQuery, bot: Bot) -> None:
    """Показывает браки из главного меню."""
    await callback.answer()
    chat_id = callback.message.chat.id if callback.message and callback.message.chat.type != ChatType.PRIVATE else None
    await _safe_edit(callback, await _build_marriages_text(bot, chat_id), reply_markup=back_to_main_keyboard())


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


@router.message(F.chat.type == ChatType.PRIVATE)
async def private_lastword_capture(message: Message, bot: Bot) -> None:
    """Фиксируем, что пользователь писал боту в ЛС."""
    if message.from_user is None:
        return
    db.add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    return


@router.message(F.chat.type == ChatType.PRIVATE)
async def private_message_prompt(message: Message) -> None:
    """Подсказка для пользователей, которые пишут боту в ЛС без нажатия Start/кнопки."""
    # Игнорируем команды — они обрабатываются отдельно
    if message.text and message.text.startswith("/"):
        return

    # Сохраняем факт, что пользователь писал боту в ЛС
    if message.from_user:
        db.add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    # Общая подсказка
    await message.answer(
        "Привет! Вы можете использовать главное меню или ввести команду /help для списка доступных действий.",
        reply_markup=back_to_main_keyboard(),
    )
