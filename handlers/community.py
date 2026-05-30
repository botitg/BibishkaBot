"""Команды сообщества: состав админов и награды."""

from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from datetime import datetime
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import database as db
from utils.filters import AdminFilter
from utils.users import mention_by_id, mention_from_user


router = Router()
logger = logging.getLogger(__name__)


def _target_from_args(message: Message, args: str | None) -> tuple[int | None, str, bool]:
    """Определяет пользователя из reply или первого аргумента."""
    parts = (args or "").split()
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id, " ".join(parts).strip(), True

    if parts and parts[0].lstrip("-").isdigit():
        return int(parts.pop(0)), " ".join(parts).strip(), True

    if message.from_user:
        return message.from_user.id, " ".join(parts).strip(), False

    return None, " ".join(parts).strip(), False


def _mention(user_id: int) -> str:
    """Формирует fallback-ссылку на профиль без показа ID."""
    return f'<a href="tg://user?id={user_id}">профиль</a>'


@router.message(Command("staff"))
async def cmd_staff(message: Message, bot: Bot) -> None:
    """Показывает состав админов бота и текущего чата."""
    lines = ["👑 <b>Админский состав</b>\n"]
    # Показываем скрытых админов только если запрашивающий — админ бота
    show_hidden = False
    if message.from_user and db.is_admin(message.from_user.id):
        show_hidden = True
    bot_admins = db.list_admins(include_hidden=show_hidden)
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
                lines.append(f"• {mention} — <b>{rank}</b> ({title}){hidden_mark}")
            else:
                lines.append(f"• {mention} — <b>{rank}</b>{hidden_mark}")
    else:
        lines.append("Админы бота пока не назначены.")

    if message.chat.type != ChatType.PRIVATE:
        try:
            chat_admins = await bot.get_chat_administrators(message.chat.id)
            lines.append("\n<b>Админы чата:</b>")
            for admin in chat_admins[:30]:
                name = escape(admin.user.full_name)
                lines.append(f"• <a href=\"tg://user?id={admin.user.id}\">{name}</a>")
        except Exception:
            logger.exception("Не удалось получить админов чата")
            lines.append("\nНе удалось получить админов чата. Проверь права бота.")

    await message.answer("\n".join(lines))


@router.message(Command("award"), AdminFilter())
async def cmd_award(message: Message, command: CommandObject, bot: Bot) -> None:
    """Выдает награду пользователю ответом на сообщение или по ID."""
    if message.from_user is None:
        return

    target_id, title, explicit_target = _target_from_args(message, command.args)
    if target_id is None or not explicit_target:
        await message.answer("Использование: ответь на сообщение /award Название награды или /award USER_ID Название.")
        return

    if not title:
        title = "Заслуженная награда"
    # Поддерживаем расширенный формат: Название | emoji | Описание | rarity
    parts = [p.strip() for p in title.split("|") if p.strip()]
    title_text = parts[0] if parts else "Заслуженная награда"
    emoji = parts[1] if len(parts) >= 2 else None
    description = parts[2] if len(parts) >= 3 else None
    rarity = parts[3].lower() if len(parts) >= 4 else None

    award_id = db.add_award(target_id, message.chat.id, title_text, message.from_user.id, emoji=emoji, description=description, rarity=rarity)
    if award_id == -1:
        await message.answer("❗ Такая уникальная награда уже существует — нельзя выдать дубликат.")
        return
    target_label = (
        mention_from_user(message.reply_to_message.from_user)
        if message.reply_to_message and message.reply_to_message.from_user
        else await mention_by_id(bot, target_id)
    )
    rarity_names = {"common": "Обычная", "rare": "Редкая", "epic": "Эпическая", "mythic": "Мифическая", "ultra": "Ультра", "legendary": "Легендарная"}
    rarity_label = rarity_names.get(rarity, "Обычная") if rarity else "Обычная"
    points_map = {"common": 1, "rare": 5, "epic": 20, "mythic": 100, "ultra": 500, "legendary": 250}
    points = points_map.get(rarity, 1)
    lines = [f"🏆 Награда выдана пользователю {target_label}.", f"ID: <code>{award_id}</code>"]
    if emoji:
        lines.append(f"{emoji} <b>{escape(title_text)}</b> — <i>{rarity_label}</i> — <b>{points} очков</b>")
    else:
        lines.append(f"<b>{escape(title_text)}</b> — <i>{rarity_label}</i> — <b>{points} очков</b>")
    if description:
        lines.append(escape(description))

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("awards"))
async def cmd_awards(message: Message, command: CommandObject, bot: Bot) -> None:
    """Показывает награды пользователя."""
    target_id, _, _ = _target_from_args(message, command.args)
    if target_id is None:
        await message.answer("Не удалось определить пользователя.")
        return

    # По-умолчанию показываем все награды пользователя из всех чатов
    awards = db.list_awards(target_id, None)
    target_label = (
        mention_from_user(message.reply_to_message.from_user)
        if message.reply_to_message and message.reply_to_message.from_user
        else await mention_by_id(bot, target_id)
    )
    if not awards:
        await message.answer(f"🏆 У пользователя {target_label} пока нет наград.")
        return

    lines = [f"🏆 <b>Награды пользователя {target_label}</b>"]
    points_map = {"common": 1, "rare": 5, "epic": 20, "mythic": 100, "ultra": 500, "legendary": 250}
    for award in awards[:30]:
        issuer_label = await mention_by_id(bot, int(award["issuer_id"]))
        emoji = award.get("emoji") or ""
        desc = award.get("description") or ""
        rarity = (award.get("rarity") or "common").lower()
        rarity = rarity if rarity else "common"
        rarity_names = {"common": "Обычная", "rare": "Редкая", "epic": "Эпическая", "mythic": "Мифическая", "ultra": "Ультра", "legendary": "Легендарная"}
        rarity_label = rarity_names.get(rarity, "Обычная")
        title = escape(str(award["title"]))
        # Показываем, в каком чате была выдана награда (если доступно)
        chat_note = ""
        try:
            award_chat = int(award.get("chat_id", 0))
            if award_chat:
                chat_note = f" (чат {award_chat})"
        except Exception:
            chat_note = ""
        points = points_map.get(rarity, 1)
        lines.append(f"\n<b>#{award['id']}</b> {emoji} <b>{title}</b>{chat_note} — <i>{rarity_label}</i> — <b>{points} очков</b>")
        if desc:
            lines.append(f"{escape(desc)}")
        lines.append(f"Выдал: {issuer_label}")
    await message.answer("\n".join(lines))


def _format_duration(seconds: int) -> str:
    """Форматирует секунды в удобочитаемый вид (дни/часы/минуты)."""
    seconds = int(seconds)
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24
    if days > 0:
        return f"{days}д {hours % 24}ч {minutes % 60}м"
    if hours > 0:
        return f"{hours}ч {minutes % 60}м"
    if minutes > 0:
        return f"{minutes}м"
    return f"{seconds}с"


@router.message(Command("marry"))
async def cmd_marry(message: Message, command: CommandObject, bot: Bot) -> None:
    """Отправляет предложение брака выбранному пользователю."""
    if message.from_user is None:
        return

    target_id, _, explicit = _target_from_args(message, command.args)
    if target_id is None or not explicit:
        await message.answer("Использование: ответь на сообщение /marry или /marry USER_ID")
        return

    if int(target_id) == int(message.from_user.id):
        await message.answer("❗ Нельзя вступить в брак с самим собой.")
        return

    chat_id = None if message.chat.type == ChatType.PRIVATE else message.chat.id
    proposal_id = db.create_marriage_proposal(message.from_user.id, target_id, chat_id)
    if proposal_id == -1:
        await message.answer("❗ Эти пользователи уже состоят в браке.")
        return
    if proposal_id == -2:
        await message.answer("❗ Неверные ID пользователей.")
        return

    proposer_label = mention_from_user(message.from_user)
    target_label = (
        mention_from_user(message.reply_to_message.from_user)
        if message.reply_to_message and message.reply_to_message.from_user
        else await mention_by_id(bot, target_id)
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💍 Принять", callback_data=f"marry:accept:{proposal_id}"),
                InlineKeyboardButton(text="💔 Отказаться", callback_data=f"marry:decline:{proposal_id}"),
            ]
        ]
    )
    await message.answer(
        "💌 <b>Предложение брака</b>\n\n"
        f"{proposer_label} предлагает брак пользователю {target_label}.\n\n"
        "Ответить может только тот, кому сделали предложение.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@router.callback_query(lambda callback: callback.data and callback.data.startswith("marry:accept:"))
async def callback_marry_accept(callback: CallbackQuery, bot: Bot) -> None:
    """Принимает предложение брака только от адресата."""
    proposal_id = int(callback.data.rsplit(":", 1)[1])
    proposal = db.get_marriage_proposal(proposal_id)
    if not proposal:
        await callback.answer("Предложение уже неактуально.", show_alert=True)
        return

    if callback.from_user.id != int(proposal["proposee_id"]):
        await callback.answer("Это предложение адресовано не тебе.", show_alert=True)
        return

    chat_id = proposal["chat_id"]
    marriage_id = db.create_marriage(int(proposal["proposer_id"]), int(proposal["proposee_id"]), chat_id)
    db.delete_marriage_proposals_between(int(proposal["proposer_id"]), int(proposal["proposee_id"]))
    if marriage_id == -1:
        await callback.answer("Эта пара уже в браке.", show_alert=True)
        return

    marriage = db.get_marriage(marriage_id)
    proposer_label = await mention_by_id(bot, int(proposal["proposer_id"]))
    proposee_label = mention_from_user(callback.from_user)
    text = (
        "💍 <b>Брак заключен!</b>\n\n"
        f"{proposer_label} и {proposee_label} теперь пара.\n"
        f"Номер брака: <code>#{marriage_id}</code>\n"
        f"Дата: <code>{marriage['started_at']}</code>"
    )
    await callback.answer("Поздравляем!")
    if callback.message:
        await callback.message.edit_text(text, parse_mode="HTML")


@router.callback_query(lambda callback: callback.data and callback.data.startswith("marry:decline:"))
async def callback_marry_decline(callback: CallbackQuery, bot: Bot) -> None:
    """Отклоняет предложение брака только от адресата."""
    proposal_id = int(callback.data.rsplit(":", 1)[1])
    proposal = db.get_marriage_proposal(proposal_id)
    if not proposal:
        await callback.answer("Предложение уже неактуально.", show_alert=True)
        return

    if callback.from_user.id != int(proposal["proposee_id"]):
        await callback.answer("Это предложение адресовано не тебе.", show_alert=True)
        return

    db.delete_marriage_proposal(proposal_id)
    proposer_label = await mention_by_id(bot, int(proposal["proposer_id"]))
    proposee_label = mention_from_user(callback.from_user)
    await callback.answer("Предложение отклонено.")
    if callback.message:
        await callback.message.edit_text(
            "💔 <b>Предложение отклонено</b>\n\n"
            f"{proposee_label} отказался/отказалась от предложения {proposer_label}.",
            parse_mode="HTML",
        )


@router.message(Command("divorce"))
async def cmd_divorce(message: Message, command: CommandObject, bot: Bot) -> None:
    """Расторгает конкретный брак только участником пары."""
    if message.from_user is None:
        return

    args = (command.args or "").strip()

    # Если указан ID брака
    if args.isdigit():
        marriage_id = int(args)
        marriage = db.get_marriage(marriage_id)
        if not marriage:
            await message.answer("Брак не найден.")
            return
        caller = int(message.from_user.id)
        if marriage.get("ended_at"):
            await message.answer("Этот брак уже расторгнут.")
            return
        if caller not in (int(marriage["user1_id"]), int(marriage["user2_id"])):
            await message.answer("Расторгнуть этот брак может только один из участников пары.")
            return
        if db.end_marriage_by_id(marriage_id):
            u1_label = await mention_by_id(bot, int(marriage["user1_id"]))
            u2_label = await mention_by_id(bot, int(marriage["user2_id"]))
            await message.answer(f"✅ Брак <code>#{marriage_id}</code> расторгнут.\n{u1_label} × {u2_label}")
        else:
            await message.answer("Брак уже расторгнут или не найден.")
        return

    if message.reply_to_message and message.reply_to_message.from_user:
        spouse_id = message.reply_to_message.from_user.id
        caller_id = message.from_user.id
        marriage = db.get_active_marriage_between(caller_id, spouse_id)
        if caller_id != spouse_id and marriage and db.end_marriage_by_id(int(marriage["id"])):
            caller_label = mention_from_user(message.from_user)
            spouse_label = mention_from_user(message.reply_to_message.from_user)
            await message.answer(f"✅ Брак <code>#{marriage['id']}</code> расторгнут.\n{caller_label} × {spouse_label}")
            return

        await message.answer("Не найден активный брак между вами и этим пользователем.")
        return

    active = [
        marriage
        for marriage in db.list_marriages_for_user(message.from_user.id, None)
        if not marriage.get("ended_at")
    ]
    if len(active) == 1:
        marriage = active[0]
        other_id = int(marriage["user2_id"]) if int(marriage["user1_id"]) == message.from_user.id else int(marriage["user1_id"])
        other_label = await mention_by_id(bot, other_id)
        await message.answer(
            "У тебя один активный брак.\n"
            f"Пара: {other_label}\n\n"
            f"Чтобы расторгнуть именно его, напиши: <code>/divorce {marriage['id']}</code>"
        )
        return

    if len(active) > 1:
        lines = ["💔 <b>Твои активные браки</b>\n", "Выбери конкретный номер и напиши <code>/divorce ID</code>:"]
        for marriage in active[:10]:
            other_id = int(marriage["user2_id"]) if int(marriage["user1_id"]) == message.from_user.id else int(marriage["user1_id"])
            other_label = await mention_by_id(bot, other_id)
            lines.append(f"• <code>#{marriage['id']}</code> — {other_label}")
        await message.answer("\n".join(lines))
        return

    await message.answer("У тебя нет активных браков. Использование: reply /divorce или /divorce ID_брака")


@router.message(Command("marriages"))
async def cmd_marriages(message: Message, command: CommandObject, bot: Bot) -> None:
    """Показывает топ браков и/или список браков пользователя.

    Использование:
    - /marriages — топ браков
    - ответ: /marriages — браки для выбранного пользователя
    - /marriages USER_ID — браки пользователя
    """
    target_id, _, explicit = _target_from_args(message, command.args)
    # Если указан пользователь — показываем его браки
    if explicit and target_id is not None:
        marriages = db.list_marriages_for_user(target_id, None)
        target_label = (
            mention_from_user(message.reply_to_message.from_user)
            if message.reply_to_message and message.reply_to_message.from_user
            else await mention_by_id(bot, target_id)
        )
        if not marriages:
            await message.answer(f"У пользователя {target_label} нет записей о браках.")
            return
        lines = [f"💍 <b>Браки пользователя {target_label}</b>"]
        for m in marriages[:30]:
            partner = int(m["user2_id"]) if int(m["user1_id"]) == int(target_id) else int(m["user1_id"]) 
            partner_label = await mention_by_id(bot, partner)
            started = m.get("started_at")
            ended = m.get("ended_at")
            if ended:
                # длительность
                try:
                    dur = int((datetime.fromisoformat(ended) - datetime.fromisoformat(started)).total_seconds())
                except Exception:
                    dur = 0
                lines.append(f"\n<b>#{m['id']}</b> {partner_label} — {started} — окончено {ended} ({_format_duration(dur)})")
            else:
                try:
                    dur = int((datetime.utcnow() - datetime.fromisoformat(started)).total_seconds())
                except Exception:
                    dur = 0
                lines.append(f"\n<b>#{m['id']}</b> {partner_label} — {started} — активно ({_format_duration(dur)})")
        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    # Иначе показываем топы: по длительности браков и по числу браков у пользователей
    chat_id = None if message.chat.type == ChatType.PRIVATE else message.chat.id
    top_marriages = db.top_marriages_by_duration(chat_id=chat_id, limit=10)
    top_users = db.top_users_by_marriage_count(chat_id=chat_id, limit=10)

    lines = [
        "💍 <b>Браки и пары</b>",
        "<i>Команды: /marry ответом на сообщение, /divorce ID, /marriages ответом на пользователя</i>\n",
    ]
    if top_marriages:
        lines.append("<b>Самые долгие браки</b>")
        medals = ["🥇", "🥈", "🥉"]
        for index, m in enumerate(top_marriages, start=1):
            u1 = int(m["user1_id"])
            u2 = int(m["user2_id"])
            u1_label = await mention_by_id(bot, u1)
            u2_label = await mention_by_id(bot, u2)
            dur = int(m.get("duration", 0))
            prefix = medals[index - 1] if index <= len(medals) else f"{index}."
            lines.append(f"{prefix} {u1_label} + {u2_label}\n   <b>{_format_duration(dur)}</b> · <code>#{m['id']}</code>")
    else:
        lines.append("<b>Самые долгие браки</b>\nПока нет данных.")

    if top_users:
        lines.append("\n<b>Самые семейные участники</b>")
        for index, row in enumerate(top_users, start=1):
            uid = int(row["user_id"])
            cnt = int(row.get("cnt", 0))
            label = await mention_by_id(bot, uid)
            lines.append(f"{index}. {label} — <b>{cnt}</b> браков")

    await message.answer("\n".join(lines), parse_mode="HTML")



@router.message(~F.text.startswith("/"))
async def _record_message_for_stats(message: Message) -> None:
    """Записываем факт каждого пользовательского сообщения для статистики активности."""
    if message.from_user is None:
        return
    # Не учитываем ботов
    if getattr(message.from_user, "is_bot", False):
        return

    try:
        db.add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
        db.record_message(message.from_user.id, message.chat.id)
    except Exception:
        logger.exception("Не удалось записать сообщение для статистики")


@router.message(Command("unaward"), AdminFilter())
async def cmd_unaward(message: Message, command: CommandObject) -> None:
    """Удаляет награду по ID."""
    args = (command.args or "").strip()
    if not args.isdigit():
        await message.answer("Использование: /unaward ID_награды")
        return

    award_id = int(args)
    if db.delete_award(award_id):
        await message.answer(f"✅ Награда <code>{award_id}</code> удалена.")
    else:
        await message.answer("Награда не найдена.")


@router.message(Command("transfer_award"), AdminFilter())
async def cmd_transfer_award(message: Message, command: CommandObject, bot: Bot) -> None:
    """Переносит существующую награду другому пользователю.

    Использование:
    - Ответ на сообщение: ответь на сообщение пользователя и отправь `/transfer_award AWARD_ID`
    - Без ответа: `/transfer_award AWARD_ID TARGET_USER_ID`
    """
    args = (command.args or "").split()

    # Определяем цель (reply или явный ID; старые текстовые идентификаторы тоже поддерживаются).
    if message.reply_to_message and message.reply_to_message.from_user:
        # reply -> target is replied user, award id expected in args
        if not args or not args[0].isdigit():
            await message.answer("Использование: ответь на сообщение и отправь /transfer_award AWARD_ID")
            return
        award_id = int(args[0])
        target_id = message.reply_to_message.from_user.id
    else:
        if len(args) < 2 or not args[0].isdigit():
            await message.answer("Использование: /transfer_award AWARD_ID USER_ID")
            return
        award_id = int(args[0])
        target_token = args[1]

        target_id = None
        # Если передан текстовый идентификатор, пробуем найти профиль через Telegram.
        if target_token.startswith("@") or not target_token.lstrip("-").isdigit():
            identifier = target_token
            if not identifier.startswith("@"):
                identifier = f"@{identifier}"
            try:
                chat = await bot.get_chat(identifier)
                target_id = int(getattr(chat, "id"))
            except Exception:
                # Попробуем без @
                try:
                    chat = await bot.get_chat(target_token)
                    target_id = int(getattr(chat, "id"))
                except Exception:
                    await message.answer("Не удалось найти пользователя. Лучше используй reply на сообщение или USER_ID.")
                    return
        else:
            target_id = int(target_token)

    award = db.get_award(award_id)
    if not award:
        await message.answer("Награда не найдена.")
        return

    # Если команда выполнена в чате и награда принадлежала другому чату, обновляем chat_id автоматически
    new_chat_id = None
    if message.chat.type != ChatType.PRIVATE:
        try:
            award_chat = int(award.get("chat_id", 0))
        except Exception:
            award_chat = 0
        if award_chat != int(message.chat.id):
            new_chat_id = int(message.chat.id)

    # Выполняем перенос (включая возможное обновление chat_id)
    success = db.transfer_award(award_id, target_id, new_chat_id)
    if not success:
        await message.answer("Не удалось передать награду. Проверьте ID/имя и попробуйте снова.")
        return

    target_label = await mention_by_id(bot, target_id)
    if new_chat_id is not None:
        await message.answer(f"✅ Награда <code>{award_id}</code> передана пользователю {target_label}. (чат обновлён)")
    else:
        await message.answer(f"✅ Награда <code>{award_id}</code> передана пользователю {target_label}.")
