"""Команды модерации и автоматические фильтры сообщений."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.enums import ChatType, ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandObject
from aiogram.types import ChatPermissions, Message

import database as db
from utils.filters import AdminFilter, contains_bad_words, contains_link, is_caps, normalize_text
from utils.users import mention_by_id


router = Router()
logger = logging.getLogger(__name__)
_spam_cache: dict[tuple[int, int], dict[str, object]] = {}


def _parse_duration(value: str | None) -> int | None:
    """Преобразует 1m, 1h, 1d или 30s в секунды."""
    if not value:
        return None

    match = re.fullmatch(r"(\d+)([smhd])", value.strip().lower())
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return amount * multipliers[unit]


def _format_duration(seconds: int) -> str:
    """Форматирует секунды в короткую понятную длительность."""
    if seconds <= 0:
        return "навсегда"
    if seconds % 86400 == 0:
        return f"{seconds // 86400}д"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}ч"
    if seconds % 60 == 0:
        return f"{seconds // 60}м"
    return f"{seconds}с"


def _target_from_message(message: Message, args: str | None) -> tuple[int | None, int | None, str]:
    """Определяет цель, длительность и причину из reply или аргументов."""
    parts = (args or "").split()
    target_id = message.reply_to_message.from_user.id if message.reply_to_message and message.reply_to_message.from_user else None

    if target_id is None:
        if not parts or not parts[0].lstrip("-").isdigit():
            return None, None, " ".join(parts)
        target_id = int(parts.pop(0))

    duration = _parse_duration(parts[0]) if parts else None
    if duration is not None:
        parts.pop(0)

    return target_id, duration, " ".join(parts).strip()


def _mention(user_id: int) -> str:
    """Формирует HTML-ссылку на пользователя."""
    return f'<a href="tg://user?id={user_id}">профиль</a>'


def _full_permissions() -> ChatPermissions:
    """Возвращает набор прав для снятия мута."""
    return ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_invite_users=True,
    )


async def _ensure_group(message: Message) -> bool:
    """Проверяет, что команда вызвана в группе."""
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("Эта команда работает только в группе или супергруппе.")
        return False
    return True


async def _safe_delete(message: Message) -> None:
    """Пытается удалить сообщение без падения бота."""
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        logger.exception("Не удалось удалить сообщение")


async def _mute_user(bot: Bot, chat_id: int, user_id: int, seconds: int) -> None:
    """Ограничивает пользователю отправку сообщений."""
    until_date = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    await bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=until_date,
    )


async def _unmute_user(bot: Bot, chat_id: int, user_id: int) -> None:
    """Снимает ограничения на отправку сообщений."""
    await bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=_full_permissions(),
    )


async def _ban_user(bot: Bot, chat_id: int, user_id: int, seconds: int) -> None:
    """Банит пользователя навсегда или на заданное время."""
    if seconds > 0:
        until_date = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        await bot.ban_chat_member(chat_id=chat_id, user_id=user_id, until_date=until_date)
    else:
        await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)


def _is_spam(message: Message) -> bool:
    """Определяет повторяющийся спам одного пользователя."""
    if message.from_user is None or message.text is None:
        return False

    key = (message.chat.id, message.from_user.id)
    now = time.monotonic()
    text = normalize_text(message.text)
    cached = _spam_cache.get(key)

    if cached and cached.get("text") == text and now - float(cached.get("time", 0)) <= 12:
        cached["count"] = int(cached.get("count", 1)) + 1
        cached["time"] = now
    else:
        cached = {"text": text, "time": now, "count": 1}
        _spam_cache[key] = cached

    return int(cached["count"]) >= 3


def _detect_violation(message: Message) -> str | None:
    """Возвращает причину нарушения для автофильтра."""
    text = message.text or ""
    if db.get_bool_setting("filter_bad_words") and contains_bad_words(text, db.get_setting("bad_words")):
        return "мат"
    if db.get_bool_setting("filter_links") and contains_link(text):
        return "ссылки"
    if db.get_bool_setting("filter_caps") and is_caps(text):
        return "капс"
    if db.get_bool_setting("filter_spam") and _is_spam(message):
        return "спам"
    return None


async def _apply_warn_limit(bot: Bot, message: Message, target_id: int, count: int) -> None:
    """Применяет мут, если варны дошли до лимита."""
    max_warnings = db.get_int_setting("max_warnings", 3)
    if count < max_warnings:
        return

    seconds = db.get_int_setting("warn_mute_seconds", 600)
    try:
        await _mute_user(bot, message.chat.id, target_id, seconds)
        db.clear_warnings(target_id, message.chat.id)
        await message.answer(
            f"🔇 Лимит варнов достигнут: {count}/{max_warnings}. "
            f"Мут на {_format_duration(seconds)}. Варны сброшены."
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        logger.exception("Не удалось выдать автоматический мут")
        await message.answer("Лимит варнов достигнут, но мут не применен. Проверьте права бота.")


@router.message(Command("rules"))
async def cmd_rules(message: Message) -> None:
    """Показывает правила чата."""
    await message.answer(db.get_setting("rules_text"), parse_mode=None)


@router.message(Command("mute"), AdminFilter())
async def cmd_mute(message: Message, command: CommandObject, bot: Bot) -> None:
    """Мьютит пользователя: /mute 1m причина или /mute USER_ID 1h причина."""
    if not await _ensure_group(message):
        return

    target_id, duration, reason = _target_from_message(message, command.args)
    if target_id is None:
        await message.answer("Использование: reply /mute 1m причина или /mute USER_ID 1h причина.")
        return
    if db.is_admin(target_id):
        await message.answer("Администратора бота нельзя замьютить через эту команду.")
        return

    seconds = duration if duration is not None else db.get_int_setting("default_mute_seconds", 600)
    target_label = await mention_by_id(bot, target_id)
    try:
        await _mute_user(bot, message.chat.id, target_id, seconds)
        await message.answer(
            f"🔇 Пользователь {target_label} получил мут на {_format_duration(seconds)}.\n"
            f"Причина: {reason or 'не указана'}"
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        logger.exception("Не удалось замьютить пользователя")
        await message.answer("Не удалось выдать мут. Проверьте права бота.")


@router.message(Command("unmute"), AdminFilter())
async def cmd_unmute(message: Message, command: CommandObject, bot: Bot) -> None:
    """Снимает мут с пользователя."""
    if not await _ensure_group(message):
        return

    target_id, _, _ = _target_from_message(message, command.args)
    if target_id is None:
        await message.answer("Использование: reply /unmute или /unmute USER_ID.")
        return

    target_label = await mention_by_id(bot, target_id)
    try:
        await _unmute_user(bot, message.chat.id, target_id)
        await message.answer(f"✅ Мут снят с пользователя {target_label}.")
    except (TelegramBadRequest, TelegramForbiddenError):
        logger.exception("Не удалось снять мут")
        await message.answer("Не удалось снять мут. Проверьте права бота.")


@router.message(Command("ban"), AdminFilter())
async def cmd_ban(message: Message, command: CommandObject, bot: Bot) -> None:
    """Банит пользователя: /ban 1d причина или /ban USER_ID 1h причина."""
    if not await _ensure_group(message):
        return

    target_id, duration, reason = _target_from_message(message, command.args)
    if target_id is None:
        await message.answer("Использование: reply /ban 1d причина или /ban USER_ID 1h причина.")
        return
    if db.is_admin(target_id):
        await message.answer("Администратора бота нельзя забанить через эту команду.")
        return

    # Проверяем, не является ли цель админом чата
    try:
        target_member = await bot.get_chat_member(message.chat.id, target_id)
        if getattr(target_member, "status", "") in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER, ChatMemberStatus.CREATOR):
            await message.answer("Нельзя забанить администратора чата через эту команду.")
            return
    except Exception:
        # если не удалось получить инфо о пользователе — продолжаем и полагаемся на исключения от Telegram
        logger.exception("Не удалось получить статус пользователя в чате при попытке бана")

    # Проверяем, что бот имеет право банить участников
    try:
        me = await bot.get_me()
        bot_member = await bot.get_chat_member(message.chat.id, me.id)
        can_restrict = bool(getattr(bot_member, "can_restrict_members", False)) or getattr(bot_member, "status", "") in (ChatMemberStatus.OWNER, ChatMemberStatus.CREATOR)
        if not can_restrict:
            await message.answer("У меня нет прав для бана участников. Дайте боту право «Ban users" и повторите.")
            return
    except Exception:
        logger.exception("Не удалось проверить права бота в чате")

    seconds = duration if duration is not None else db.get_int_setting("default_ban_seconds", 0)
    target_label = await mention_by_id(bot, target_id)
    try:
        await _ban_user(bot, message.chat.id, target_id, seconds)
        await message.answer(
            f"⛔ Пользователь {target_label} забанен на {_format_duration(seconds)}.\n"
            f"Причина: {reason or 'не указана'}"
        )
        # Сохраняем запись о бане для возможного авто-ре-бана при повторном заходе
        try:
            banned_until_iso = None
            if seconds > 0:
                banned_until_iso = (datetime.utcnow() + timedelta(seconds=seconds)).isoformat(timespec="seconds")
            db.add_ban_record(target_id, message.chat.id, banned_until_iso, message.from_user.id if message.from_user else None, reason)
        except Exception:
            logger.exception("Не удалось сохранить запись о бане в БД")
        # Проверяем, что бан действительно применился
        try:
            member_after = await bot.get_chat_member(message.chat.id, target_id)
            status_after = getattr(member_after, "status", "")
            if status_after in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER, ChatMemberStatus.CREATOR):
                await message.answer(
                    "⚠️ Похоже, бан не применился — пользователь всё ещё в чате. "
                    "Проверьте права бота и права пользователя (админ/создатель)."
                )
        except Exception:
            logger.exception("Не удалось проверить статус пользователя после бана")
    except (TelegramBadRequest, TelegramForbiddenError):
        logger.exception("Не удалось забанить пользователя")
        await message.answer("Не удалось выдать бан. Проверьте права бота.")


@router.message(Command("kick"), AdminFilter())
async def cmd_kick(message: Message, command: CommandObject, bot: Bot) -> None:
    """Кикает пользователя через бан и мгновенный разбан."""
    if not await _ensure_group(message):
        return

    target_id, _, reason = _target_from_message(message, command.args)
    if target_id is None:
        await message.answer("Использование: reply /kick причина или /kick USER_ID причина.")
        return
    if db.is_admin(target_id):
        await message.answer("Администратора бота нельзя кикнуть через эту команду.")
        return

    target_label = await mention_by_id(bot, target_id)
    try:
        await bot.ban_chat_member(message.chat.id, target_id)
        await bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
        await message.answer(f"🚪 Пользователь {target_label} кикнут.\nПричина: {reason or 'не указана'}")
    except (TelegramBadRequest, TelegramForbiddenError):
        logger.exception("Не удалось кикнуть пользователя")
        await message.answer("Не удалось выполнить кик. Проверьте права бота.")


@router.message(Command("unban"), AdminFilter())
async def cmd_unban(message: Message, command: CommandObject, bot: Bot) -> None:
    """Разбанивает пользователя по ID."""
    if not await _ensure_group(message):
        return

    target_id, _, _ = _target_from_message(message, command.args)
    if target_id is None:
        await message.answer("Использование: /unban USER_ID")
        return

    target_label = await mention_by_id(bot, target_id)
    try:
        await bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
        await message.answer(f"✅ Пользователь {target_label} разбанен.")
        try:
            db.remove_ban_record(target_id, message.chat.id)
        except Exception:
            logger.exception("Не удалось удалить запись о бане из БД после разбанa")
    except (TelegramBadRequest, TelegramForbiddenError):
        logger.exception("Не удалось разбанить пользователя")
        await message.answer("Не удалось снять бан. Проверьте права бота.")


@router.message(Command("warn"), AdminFilter())
async def cmd_warn(message: Message, command: CommandObject, bot: Bot) -> None:
    """Выдает предупреждение и мутит при достижении лимита."""
    if not await _ensure_group(message):
        return

    target_id, _, reason = _target_from_message(message, command.args)
    if target_id is None:
        await message.answer("Использование: reply /warn причина или /warn USER_ID причина.")
        return
    if db.is_admin(target_id):
        await message.answer("Администратору бота нельзя выдать варн через эту команду.")
        return

    count = db.warn_user(target_id, message.chat.id)
    max_warnings = db.get_int_setting("max_warnings", 3)
    target_label = await mention_by_id(bot, target_id)
    await message.answer(
        f"⚠️ Пользователь {target_label} получил варн {count}/{max_warnings}.\n"
        f"Причина: {reason or 'не указана'}"
    )
    await _apply_warn_limit(bot, message, target_id, count)


@router.message(Command("unwarn"), AdminFilter())
async def cmd_unwarn(message: Message, command: CommandObject, bot: Bot) -> None:
    """Снимает одно предупреждение."""
    if not await _ensure_group(message):
        return

    target_id, _, _ = _target_from_message(message, command.args)
    if target_id is None:
        await message.answer("Использование: reply /unwarn или /unwarn USER_ID.")
        return

    count = db.unwarn_user(target_id, message.chat.id)
    max_warnings = db.get_int_setting("max_warnings", 3)
    target_label = await mention_by_id(bot, target_id)
    await message.answer(f"✅ У пользователя {target_label} теперь варнов: {count}/{max_warnings}.")


@router.message(F.text)
async def auto_moderation(message: Message, bot: Bot) -> None:
    """Проверяет сообщения фильтрами мата, спама, ссылок и капса."""
    if (
        message.text is None
        or message.from_user is None
        or message.from_user.is_bot
        or message.chat.type == ChatType.PRIVATE
        or db.is_admin(message.from_user.id)
    ):
        raise SkipHandler()

    reason = _detect_violation(message)
    if reason is None:
        raise SkipHandler()

    await _safe_delete(message)
    count = db.warn_user(message.from_user.id, message.chat.id)
    max_warnings = db.get_int_setting("max_warnings", 3)
    await message.answer(
        f"⚠️ {message.from_user.mention_html()}, сообщение удалено: {reason}. "
        f"Варны: {count}/{max_warnings}."
    )
    await _apply_warn_limit(bot, message, message.from_user.id, count)


@router.message(F.new_chat_members)
async def auto_reban_new_members(message: Message, bot: Bot) -> None:
    """При входе новых участников проверяет, есть ли для них активный бан в БД, и повторно банит при необходимости."""
    if message.new_chat_members is None:
        return

    for member in message.new_chat_members:
        # Пропускаем ботов
        if member.is_bot:
            continue

        try:
            active = db.get_active_ban(member.id, message.chat.id)
        except Exception:
            logger.exception("Ошибка при проверке записи бана в БД")
            active = None

        if not active:
            continue

        banned_until = active.get("banned_until")
        seconds = 0
        if banned_until:
            try:
                until_dt = datetime.fromisoformat(banned_until)
                seconds = int((until_dt - datetime.utcnow()).total_seconds())
            except Exception:
                seconds = 0

        try:
            await _ban_user(bot, message.chat.id, member.id, seconds)
            label = await mention_by_id(bot, member.id)
            await message.reply(f"⛔ Пользователь {label} автоматически забанен (ранее был забанен).")
        except Exception:
            logger.exception("Не удалось автоматически забанить пользователя при входе")
