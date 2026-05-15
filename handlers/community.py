"""Команды сообщества: состав админов и награды."""

from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

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

    bot_admins = db.list_admins()
    if bot_admins:
        lines.append("<b>Админы бота:</b>")
        for admin_id in bot_admins:
            lines.append(f"• {await mention_by_id(bot, admin_id)}")
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

    award_id = db.add_award(target_id, message.chat.id, title, message.from_user.id)
    target_label = (
        mention_from_user(message.reply_to_message.from_user)
        if message.reply_to_message and message.reply_to_message.from_user
        else await mention_by_id(bot, target_id)
    )
    await message.answer(
        f"🏆 Награда выдана пользователю {target_label}.\n"
        f"ID награды: <code>{award_id}</code>\n"
        f"Название: <b>{escape(title)}</b>"
    )


@router.message(Command("awards"))
async def cmd_awards(message: Message, command: CommandObject, bot: Bot) -> None:
    """Показывает награды пользователя."""
    target_id, _, _ = _target_from_args(message, command.args)
    if target_id is None:
        await message.answer("Не удалось определить пользователя.")
        return

    chat_id = None if message.chat.type == ChatType.PRIVATE else message.chat.id
    awards = db.list_awards(target_id, chat_id)
    target_label = (
        mention_from_user(message.reply_to_message.from_user)
        if message.reply_to_message and message.reply_to_message.from_user
        else await mention_by_id(bot, target_id)
    )
    if not awards:
        await message.answer(f"🏆 У пользователя {target_label} пока нет наград.")
        return

    lines = [f"🏆 <b>Награды пользователя {target_label}</b>"]
    for award in awards[:30]:
        issuer_label = await mention_by_id(bot, int(award["issuer_id"]))
        lines.append(
            f"\n<b>#{award['id']}</b> {escape(str(award['title']))}\n"
            f"Выдал: {issuer_label}"
        )
    await message.answer("\n".join(lines))


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
