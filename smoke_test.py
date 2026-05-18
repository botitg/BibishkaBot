"""Локальный smoke-test для проверки конфигурации бота.

Проверяет:
- Настройку `ai_enabled` (должна быть False)
- Кнопки главного меню (нет игровой кнопки)
- Количество наград в БД
"""

from __future__ import annotations

from config import config
import database as db
import keyboards.inline as kb


def run():
    db.init_db([])
    print("db_path:", config.database_path)
    print("ai_enabled:", db.get_bool_setting("ai_enabled", True))

    markup = kb.main_menu_keyboard()
    buttons = [button.text for row in markup.inline_keyboard for button in row]
    print("menu_buttons:", buttons)
    has_game = any(("игра" in (t.lower()) or "🎮" in t) for t in buttons)
    print("game_button_present:", has_game)

    stats = db.get_statistics()
    print("awards_count:", stats.get("awards_count"))


if __name__ == '__main__':
    run()
