"""Проверяет права бота в указанном чате.

Запуск:
  python scripts/check_bot_rights.py CHAT_ID

Если CHAT_ID не указан, выводит права бота везде, где это возможно.
"""
from __future__ import annotations
import sys
from pathlib import Path

# Добавляем корневую папку проекта в sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import config
from aiogram import Bot
import asyncio


async def main_async():
    if not config.token:
        print("BOT_TOKEN not found in .env")
        return
    bot = Bot(token=config.token)
    chat_id = None
    if len(sys.argv) >= 2:
        try:
            chat_id = int(sys.argv[1])
        except ValueError:
            print("CHAT_ID must be integer")
            await bot.session.close()
            return

    try:
        me = await bot.get_me()
        print("Bot:", me.username, me.id)
        if chat_id is None:
            print("No chat_id provided. Provide chat id as argument to check rights in that chat.")
            await bot.session.close()
            return

        member = await bot.get_chat_member(chat_id, me.id)
        print("Chat member status:", getattr(member, "status", None))
        print("Can restrict members:", getattr(member, "can_restrict_members", False))
    except Exception as e:
        print("Failed to get chat member info:", e)
    finally:
        await bot.session.close()


if __name__ == '__main__':
    asyncio.run(main_async())
