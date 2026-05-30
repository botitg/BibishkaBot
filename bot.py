"""Точка входа BIBISHKA Admin Bot."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import ExceptionTypeFilter
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent

import database as db
from config import config
from handlers import ads, admin, ai, community, faq, moderation, start


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def setup_commands(bot: Bot) -> None:
    """Регистрирует команды в меню Telegram."""
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="rules", description="Правила чата"),
        BotCommand(command="staff", description="Админский состав"),
        BotCommand(command="awards", description="Награды"),
        # Игровые команды (мафия) временно отключены
        BotCommand(command="ads", description="Реклама"),
        BotCommand(command="marry", description="Заключить брак (ответ)"),
        BotCommand(command="divorce", description="Расторгнуть брак"),
        BotCommand(command="marriages", description="Список/топ браков"),
        BotCommand(command="admin", description="Админ-панель"),
        BotCommand(command="warn", description="Выдать варн"),
        BotCommand(command="unwarn", description="Снять варн"),
        BotCommand(command="mute", description="Мут 1m/1h/1d"),
        BotCommand(command="unmute", description="Снять мут"),
        BotCommand(command="ban", description="Бан 1m/1h/1d"),
        BotCommand(command="unban", description="Разбан"),
        BotCommand(command="kick", description="Кик пользователя"),
        BotCommand(command="award", description="Выдать награду"),
        BotCommand(command="unaward", description="Удалить награду"),
    ]
    await bot.set_my_commands(commands)


async def on_error(event: ErrorEvent) -> bool:
    """Логирует ошибки обработчиков, не останавливая бота."""
    logger.exception("Ошибка при обработке апдейта", exc_info=event.exception)
    return True


async def main() -> None:
    """Инициализирует базу, подключает роутеры и запускает polling."""
    if not config.token:
        logger.critical("BOT_TOKEN не найден. Создайте .env и добавьте BOT_TOKEN=...")
        return

    db.init_db(config.admin_ids)

    bot = Bot(
        token=config.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(ads.router)
    dp.include_router(moderation.router)
    dp.include_router(community.router)
    dp.include_router(ai.router)
    dp.include_router(faq.router)
    dp.errors.register(on_error, ExceptionTypeFilter(Exception))

    await setup_commands(bot)
    logger.info("BIBISHKA Admin Bot запущен")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

