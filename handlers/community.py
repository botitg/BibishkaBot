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
        lines.append(f"\n<b>#{award['id']}</b> {emoji} <b>{title}</b>{chat_note} — <i>{rarity_label}</i> — <b>{points} очков</b")
        if desc:
            lines.append(f"{escape(desc)}")
        lines.append(f"Выдал: {issuer_label}")
    await message.answer("\n".join(lines))



@router.message()
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

    # Определяем цель (reply или явный ID/@username)
    if message.reply_to_message and message.reply_to_message.from_user:
        # reply -> target is replied user, award id expected in args
        if not args or not args[0].isdigit():
            await message.answer("Использование: ответь на сообщение и отправь /transfer_award AWARD_ID или /transfer_award AWARD_ID @username")
            return
        award_id = int(args[0])
        target_id = message.reply_to_message.from_user.id
    else:
        if len(args) < 2 or not args[0].isdigit():
            await message.answer("Использование: /transfer_award AWARD_ID TARGET (@username или USER_ID)")
            return
        award_id = int(args[0])
        target_token = args[1]

        target_id = None
        # Если передано имя пользователя (@username или username)
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
                    await message.answer("Не удалось найти пользователя по имени. Используйте @username или ID.")
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
