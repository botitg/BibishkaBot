"""Стартовые команды и пользовательские inline-меню."""

from __future__ import annotations

import logging
from html import escape
import random
import asyncio

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
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
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


router = Router()
logger = logging.getLogger(__name__)

# Ожидания последних слов: user_id -> {chat_id, game_id}
pending_last_word: dict[int, dict] = {}
# Задачи-таймауты для ожидания последнего слова
pending_last_word_tasks: dict[int, asyncio.Task] = {}


async def _finalize_death(bot: Bot, chat_id: int, game_id: int, user_id: int, last_word: str | None) -> None:
    """Финализирует смерть игрока: записывает последнее слово и отмечает мёртвым, публикует в чате."""
    try:
        db.set_player_last_word(game_id, user_id, last_word)
        db.set_player_alive(game_id, user_id, False)
    except Exception:
        logger.exception("Ошибка при обновлении статуса игрока в БД")

    try:
        mention = await mention_by_id(bot, user_id)
        text = f"⚰️ {mention} выбывает."
        if last_word:
            text += f"\nПоследнее слово:\n{escape(last_word)}"
        await bot.send_message(chat_id, text, parse_mode="HTML")
    except Exception:
        logger.exception("Не удалось отправить сообщение о выбытии игрока в чат")


def _schedule_last_word_timeout(user_id: int, delay: int, bot: Bot, chat_id: int, game_id: int) -> None:
    async def _timeout():
        await asyncio.sleep(delay)
        info = pending_last_word_tasks.pop(user_id, None)
        # если за это время пользователь не оставил последнее слово, финализируем смерть без текста
        if pending_last_word.pop(user_id, None) is not None:
            await _finalize_death(bot, chat_id, game_id, user_id, None)

    task = asyncio.create_task(_timeout())
    pending_last_word_tasks[user_id] = task


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
async def cmd_start(message: Message, bot: Bot, command: CommandObject | None = None) -> None:
    """Показывает приветствие и главное меню.

    Если запуск с payload типа `join_<chat_id>`, регистрирует пользователя в игре
    и уведомляет чат о присоединении.
    """
    if message.from_user:
        db.add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)

    # Обработка deep-link /start join_{chat_id}
    payload = None
    if command and getattr(command, "args", None):
        payload = command.args
    else:
        if message.text:
            parts = message.text.split(maxsplit=1)
            if len(parts) == 2:
                payload = parts[1].strip()

    if payload and payload.startswith("join_") and message.chat.type == ChatType.PRIVATE:
        try:
            chat_id = int(payload.split("_", 1)[1])
        except Exception:
            chat_id = None

        if chat_id is not None and message.from_user:
            added = db.add_game_participant(message.from_user.id, message.from_user.username, chat_id)
            if added:
                await message.answer("✅ Вы успешно присоединились к игре! Удачи!", reply_markup=back_to_main_keyboard())
                # Уведомим чат о новом участнике
                try:
                    mention = await mention_by_id(bot, message.from_user.id)
                    await bot.send_message(chat_id, f"✅ {mention} присоединился к игре.")
                except Exception:
                    logger.exception("Не удалось уведомить чат о присоединении участника")
            else:
                await message.answer("ℹ️ Вы уже участвуете в игре.", reply_markup=back_to_main_keyboard())

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
        chat_id = callback.message.chat.id if callback.message and callback.message.chat else None
        await callback.message.answer(
            "Чтобы присоединиться к игре, напишите боту в личные сообщения:",
            reply_markup=private_start_keyboard(username, chat_id),
        )
    else:
        await callback.message.answer("Чтобы присоединиться к игре, напишите боту в личку.")


@router.message(Command("join"))
async def cmd_join(message: Message, bot: Bot, command: CommandObject | None = None) -> None:
    """Команда /join — если в группе, просим открыть ЛС, если в личке — регистрируем участника."""
    if message.chat.type != ChatType.PRIVATE:
        me = await bot.get_me()
        username = getattr(me, "username", None)
        if username:
            await message.answer(
                "Для участия нажмите кнопку и напишите боту в личку:",
                reply_markup=private_start_keyboard(username, message.chat.id),
            )
        else:
            await message.answer("Для участия напишите боту в личные сообщения.")
        return

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    # Если команда /join пришла с аргументом (ID чата), используем его, иначе просим воспользоваться ссылкой
    chat_id_arg = None
    if command and getattr(command, "args", None):
        arg = command.args.strip()
        if arg.isdigit():
            chat_id_arg = int(arg)

    if chat_id_arg is None:
        await message.answer(
            "Чтобы присоединиться к конкретной игре, откройте сообщение об игре в чате и нажмите кнопку 'Присоединиться' или используйте ссылку оттуда.",
            reply_markup=back_to_main_keyboard(),
        )
        return

    added = db.add_game_participant(message.from_user.id, message.from_user.username, chat_id_arg)
    if added:
        await message.answer("✅ Вы успешно присоединились к игре! Удачи!", reply_markup=back_to_main_keyboard())
    else:
        await message.answer("ℹ️ Вы уже участвуете в игре.", reply_markup=back_to_main_keyboard())


@router.message(Command("startgame"))
async def cmd_startgame(message: Message, bot: Bot) -> None:
    """Запускает объявление об игре в чате с кнопкой присоединиться."""
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("Эту команду нужно использовать в групповом чате.")
        return
    chat_id = message.chat.id
    participants = db.list_game_participants(500, chat_id)

    # Если достаточно участников, начинаем игру: распределяем роли и отправляем ЛС
    if len(participants) >= 4:
        player_count = len(participants)
        mafia_count = max(1, player_count // 4)

        # Формируем список ролей
        roles: list[str] = ["mafia"] * mafia_count
        remaining = player_count - mafia_count
        if remaining >= 2:
            roles += ["detective", "doctor"]
            remaining -= 2
        elif remaining == 1:
            roles += ["detective"]
            remaining -= 1
        roles += ["civilian"] * remaining

        # Перемешиваем и создаём игру
        random.shuffle(roles)
        game_id = db.create_game(chat_id)

        # Добавляем игроков в игру
        for i, p in enumerate(participants):
            uid = int(p["user_id"])
            username = p.get("username")
            role = roles[i]
            db.add_game_player(game_id, uid, username, role)

        # Сообщаем роли в ЛС (и удаляем из игры тех, кому не удалось отправить ЛС)
        mafia_ids = [int(p["user_id"]) for i, p in enumerate(participants) if roles[i] == "mafia"]
        removed = []
        for i, p in enumerate(participants):
            uid = int(p["user_id"])
            role = roles[i]
            try:
                if role == "mafia":
                    others = [m for m in mafia_ids if m != uid]
                    mentions = [await mention_by_id(bot, m) for m in others]
                    text = (
                        f"🎭 Ваша роль: <b>Мафия</b>.\n"
                        f"Ваша команда: {', '.join(mentions) if mentions else 'вы один(а)'}\n"
                        "Действуйте ночью и координируйтесь через этот бот в личке."
                    )
                elif role == "detective":
                    text = (
                        "🔎 Ваша роль: <b>Детектив</b>.\n"
                        "Каждую ночь вы можете проверить одного игрока. Ведите записи в ЛС."
                    )
                elif role == "doctor":
                    text = (
                        "💊 Ваша роль: <b>Доктор</b>.\n"
                        "Каждую ночь вы можете спасти одного игрока. Действуйте в ЛС."
                    )
                else:
                    text = (
                        "🙂 Ваша роль: <b>Мирный</b>.\n"
                        "Цель — вычислить мафию и сохранить жизнь городу. Удачи!"
                    )

                await bot.send_message(uid, text, parse_mode="HTML")
            except Exception:
                # не удалось отправить ЛС — удаляем игрока из игры
                logger.exception("Не удалось отправить роль в ЛС игроку %s", uid)
                db.remove_game_player(game_id, uid)
                removed.append(uid)

        if removed:
            await message.answer(
                "⚠️ Некоторым игрокам не удалось отправить роль в ЛС — они удалены из игры. Убедитесь, что все участники нажали 'Присоединиться' и открыли бота.",
            )

        await message.answer(f"🎮 Игра началась в чате — roles отправлены в ЛС. Участников: {player_count - len(removed)}")
        return

    # Иначе — просто показываем приглашение присоединиться
    me = await bot.get_me()
    username = getattr(me, "username", None)
    url = f"https://t.me/{username}?start=join_{message.chat.id}" if username else None

    builder = InlineKeyboardBuilder()
    if url:
        builder.button(text="🔗 Присоединиться", url=url)
    else:
        # fallback: show instruction to write in PM
        builder.button(text="🔗 Присоединиться (написать в ЛС)", callback_data="game:join")
    builder.button(text="👥 Участники", callback_data=f"game:participants:{message.chat.id}")
    builder.adjust(2)

    await message.answer("🎮 Игра началась! Нажмите кнопку ниже, чтобы присоединиться.", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("game:participants:"))
async def callback_game_participants(callback: CallbackQuery, bot: Bot) -> None:
    """Показывает список участников (глобально)."""
    await callback.answer()
    data = callback.data or ""
    try:
        chat_id = int(data.rsplit(":", 1)[1])
    except Exception:
        chat_id = None

    participants = db.list_game_participants(200, chat_id)
    if not participants:
        text = "👥 Участников пока нет."
    else:
        count = len(participants)
        lines = [f"👥 <b>Участники игры</b> — <b>{count}</b>\n"]
        for p in participants:
            mention = await mention_by_id(bot, int(p["user_id"]))
            lines.append(f"• {mention}")
        text = "\n".join(lines)

    if callback.message is not None:
        try:
            await callback.message.answer(text, parse_mode="HTML")
        except Exception:
            await bot.send_message(chat_id or callback.message.chat.id, text, parse_mode="HTML")
    elif chat_id is not None:
        await bot.send_message(chat_id, text, parse_mode="HTML")


@router.message(Command("lynch"), AdminFilter())
async def cmd_lynch(message: Message, bot: Bot, command: CommandObject | None = None) -> None:
    """Команда для казни игрока — просит последнее слово и выбывает игрока."""
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("Используйте эту команду в групповом чате.")
        return

    game = db.get_active_game(message.chat.id)
    if not game:
        await message.answer("Нет активной игры в этом чате.")
        return

    target_id = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    elif command and getattr(command, "args", None):
        arg = command.args.strip()
        if arg.isdigit():
            target_id = int(arg)

    if target_id is None:
        await message.answer("Использование: ответьте на сообщение игрока или /lynch USER_ID")
        return

    player = db.get_game_player(game["id"], target_id)
    if not player:
        await message.answer("Этот пользователь не участвует в текущей игре.")
        return
    if int(player.get("alive", 1)) == 0:
        await message.answer("Этот игрок уже мёртв.")
        return

    # Отправляем ЛС с просьбой оставить последнее слово
    pending_last_word[target_id] = {"game_id": game["id"], "chat_id": message.chat.id}
    try:
        await bot.send_message(target_id, "⚠️ Вас выбрали для выбытия. У вас есть последнее слово — ответьте этим сообщением в ЛС. У вас 30 секунд.")
    except Exception:
        pending_last_word.pop(target_id, None)
        await message.answer("Не удалось отправить ЛС игроку — убедитесь, что он открыл бота.")
        return

    _schedule_last_word_timeout(target_id, 30, bot, message.chat.id, game["id"])
    await message.answer("Игроку отправлен запрос на последнее слово.")


@router.message(Command("endgame"), AdminFilter())
async def cmd_endgame(message: Message, bot: Bot, command: CommandObject | None = None) -> None:
    """Завершает текущую игру и начисляет победы сторонам."""
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("Эту команду нужно использовать в групповом чате.")
        return

    game = db.get_active_game(message.chat.id)
    if not game:
        await message.answer("Нет активной игры в этом чате.")
        return

    winnerside = "village"
    if command and getattr(command, "args", None):
        arg = command.args.strip().lower()
        if arg in {"mafia", "мафия", "maf"}:
            winnerside = "mafia"

    db.finish_game(game["id"], winnerside)
    await message.answer(f"🏁 Игра завершена. Победила: {'мафия' if winnerside == 'mafia' else 'мирные'}")

    # Показать топ побед
    top = db.get_top_wins(10)
    if not top:
        await message.answer("Пока нет статистики побед.")
        return

    lines = ["🏆 <b>Топ побед</b>\n"]
    for index, row in enumerate(top, start=1):
        uid = int(row["user_id"])
        wins = int(row["wins"])
        mention = await mention_by_id(bot, uid)
        lines.append(f"{index}. {mention} — {wins} побед")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("top"))
async def cmd_top(message: Message, bot: Bot) -> None:
    """Показывает таблицу лидеров по победам."""
    top = db.get_top_wins(10)
    if not top:
        await message.answer("Пока нет лидеров.")
        return

    lines = ["🏆 <b>Топ побед</b>\n"]
    for index, row in enumerate(top, start=1):
        uid = int(row["user_id"])
        wins = int(row["wins"])
        mention = await mention_by_id(bot, uid)
        lines.append(f"{index}. {mention} — {wins} побед")

    await message.answer("\n".join(lines), parse_mode="HTML")


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
    """Перехватывает личные сообщения для записи 'последнего слова', если оно ожидается."""
    if message.from_user is None:
        return

    user_id = message.from_user.id
    # Игнорируем команды — они обрабатываются отдельно
    if message.text and message.text.startswith("/"):
        return

    if user_id in pending_last_word:
        info = pending_last_word.pop(user_id)
        # отменяем таймер, если он есть
        task = pending_last_word_tasks.pop(user_id, None)
        if task and not task.done():
            task.cancel()

        game_id = info.get("game_id")
        chat_id = info.get("chat_id")
        last_word_text = message.text or (message.caption or "")
        await _finalize_death(bot, chat_id, game_id, user_id, last_word_text)
        return


@router.message(F.chat.type == ChatType.PRIVATE)
async def private_message_prompt(message: Message) -> None:
    """Подсказка для пользователей, которые пишут боту в ЛС без нажатия Start/кнопки."""
    # Игнорируем команды — они обрабатываются отдельно
    if message.text and message.text.startswith("/"):
        return

    if message.from_user and not db.is_game_participant_global(message.from_user.id):
        await message.answer(
            "Чтобы присоединиться к игре: откройте сообщение 'Игра' в чате и нажмите кнопку 'Присоединиться', затем нажмите /start у бота; либо отправьте `/join CHAT_ID` в эту ЛС.",
            reply_markup=back_to_main_keyboard(),
        )
