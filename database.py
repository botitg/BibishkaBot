"""Работа с SQLite для BIBISHKA Admin Bot.

Игровой функционал (мафия) удалён — в БД остаются FAQ, пользователи,
настройки, модерация и награды.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from config import config


logger = logging.getLogger(__name__)
_db_lock = threading.RLock()


BIBISHKA_FACTS: dict[str, str] = {
    "real_name": "Бибисора",
    "age": "15 лет",
    "class": "9 класс",
    "birthday": "25 августа",
    "country": "Узбекистан",
    "city": "Андижан",
    "best_friend": "Садокат",
    "friends": "Нурик, Абубакр, Эмиль",
}


DEFAULT_FAQ: list[tuple[str, str]] = [
    (
        "Кто такая Бибишка,Бибишка,О Бибишке,Кто такая Бибисора",
        "💖 Бибишка — это Бибисора, блогерша и главная звезда этого чата. Бот помогает быстро отвечать на вопросы, держать порядок и красиво оформлять активность.",
    ),
    (
        "Сколько лет,Возраст,Сколько лет Бибисоре,Сколько лет Бибишке",
        "🎂 Бибисоре 15 лет.",
    ),
    (
        "Где живет,Где живёт,Город,Страна,Андижан,Узбекистан",
        "📍 Бибисора живет в Узбекистане, в городе Андижан.",
    ),
    (
        "В каком классе,Класс,Учеба,Учёба,Школа",
        "📚 Бибисора учится в 9 классе.",
    ),
    (
        "Когда день рождения,День рождения,Родилась,Дата рождения",
        "🎉 День рождения Бибисоры — 25 августа.",
    ),
    (
        "Лучшая подруга,Подруга,Садокат",
        "👑 Лучшая подруга Бибисоры — Садокат.",
    ),
    (
        "Друзья,Нурик,Абубакр,Эмиль",
        "🤝 Друзья Бибисоры: Нурик, Абубакр и Эмиль.",
    ),
    (
        "Соцсети,Социальные сети,Ссылки,Инстаграм,Instagram,TikTok,ТикТок,Telegram,Телеграм",
        "🌐 Раздел соцсетей открыт в меню /start. Админы могут добавить актуальные ссылки через FAQ или настройки.",
    ),
    (
        "Когда стрим,Стрим,Стримы,Расписание стримов,Эфир",
        "🎥 Расписание стримов появится в разделе «Стримы». Следи за меню бота и закрепами в чате.",
    ),
    (
        "Модератор,Модераторы,Как попасть в модераторы,Стать модератором",
        "🛡 В модераторы попадают активные и спокойные участники, которые помогают чату, знают правила и не создают конфликтов.",
    ),
    (
        "Связаться,Контакт,Как связаться,Написать Бибишке",
        "✉️ Для связи используй официальные контакты или раздел «Реклама», если вопрос связан с рекламой.",
    ),
    (
        "Реклама,Сотрудничество,Купить рекламу,Пиар",
        "📣 По рекламе открой раздел «Реклама» в /start и отправь одним сообщением: тему, ссылку, сроки и бюджет.",
    ),
]


DEFAULT_SETTINGS: dict[str, str] = {
    "content_version": "2",
    "filter_bad_words": "1",
    "filter_spam": "1",
    "filter_links": "1",
    "filter_caps": "1",
    "bad_words": "бля,блять,сука,хуй,хуе,хуё,пизд,еба,ёба,ебл,мудак,мразь,шлюх,гандон,долбоеб,долбоёб,уеб,уёб",
    "max_warnings": "3",
    "warn_mute_seconds": "600",
    "default_mute_seconds": "600",
    "default_ban_seconds": "0",
    "ads_receiver_id": "8436225978",
    "rules_text": (
        "📌 Правила чата:\n"
        "1. Уважай Бибишку, админов и участников.\n"
        "2. Без мата, травли, спама, капса и токсичности.\n"
        "3. Не кидай подозрительные ссылки и рекламу без разрешения.\n"
        "4. Личные данные, конфликты и провокации — мимо чата.\n"
        "5. Наказания выдаются по правилам: предупреждения, мут, бан."
    ),
    "streams_text": "🎥 Расписание стримов пока уточняется. Следи за новостями в чате и официальных соцсетях Бибишки.",
    "socials_text": "🌐 Соцсети Бибишки можно указать через FAQ: TikTok, Instagram и Telegram.",
    "ads_text": "📣 Чтобы предложить рекламу, нажми «Реклама» и отправь одним сообщением: тему, ссылку, сроки и бюджет.",
    "ai_enabled": "0",
}


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Открывает соединение с SQLite и безопасно закрывает его после операций."""
    db_path = Path(config.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        logger.exception("Ошибка при работе с базой данных")
        raise
    finally:
        connection.close()


def _ensure_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Добавляет настройку, если ее еще нет."""
    conn.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )


def _remove_removed_faq(conn: sqlite3.Connection) -> None:
    """Удаляет FAQ-записи, которые пользователь попросил убрать."""
    removed_tokens = ["донат", "donate", "ютуб", "ютьюб", "youtube"]
    for token in removed_tokens:
        conn.execute(
            "DELETE FROM faq WHERE LOWER(keywords) LIKE ? OR LOWER(answer) LIKE ?",
            (f"%{token}%", f"%{token}%"),
        )


def _ensure_default_faq(conn: sqlite3.Connection) -> None:
    """Создает стартовые FAQ и добавляет новые обязательные записи без дублей."""
    faq_count = conn.execute("SELECT COUNT(*) FROM faq").fetchone()[0]
    if faq_count == 0:
        conn.executemany("INSERT INTO faq (keywords, answer) VALUES (?, ?)", DEFAULT_FAQ)
        return

    for keywords, answer in DEFAULT_FAQ:
        first_keyword = keywords.split(",", 1)[0]
        exists = conn.execute(
            "SELECT id FROM faq WHERE LOWER(keywords) LIKE ? LIMIT 1",
            (f"%{first_keyword.lower()}%",),
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO faq (keywords, answer) VALUES (?, ?)",
                (keywords, answer),
            )


def _sync_default_faq(conn: sqlite3.Connection) -> None:
    """Обновляет базовые FAQ при смене версии контента."""
    for keywords, answer in DEFAULT_FAQ:
        first_keyword = keywords.split(",", 1)[0]
        row = conn.execute(
            "SELECT id FROM faq WHERE LOWER(keywords) LIKE ? LIMIT 1",
            (f"%{first_keyword.lower()}%",),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE faq SET keywords = ?, answer = ? WHERE id = ?",
                (keywords, answer, row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO faq (keywords, answer) VALUES (?, ?)",
                (keywords, answer),
            )


def init_db(admin_ids: list[int] | None = None) -> None:
    """Создает таблицы, настройки, FAQ и первых администраторов при запуске."""
    admin_ids = admin_ids or []
    with _db_lock, _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS faq (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keywords TEXT NOT NULL,
                answer TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY,
                rank TEXT DEFAULT 'Админ',
                title TEXT DEFAULT '',
                is_hidden INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                questions_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS faq_usage (
                faq_id INTEGER PRIMARY KEY,
                hits INTEGER NOT NULL DEFAULT 0,
                last_used_at TEXT
            );

            CREATE TABLE IF NOT EXISTS warnings (
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            );

            CREATE TABLE IF NOT EXISTS awards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                issuer_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                emoji TEXT DEFAULT '',
                description TEXT DEFAULT '',
                rarity TEXT DEFAULT 'common'
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS marriages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user1_id INTEGER NOT NULL,
                user2_id INTEGER NOT NULL,
                chat_id INTEGER,
                started_at TEXT NOT NULL,
                ended_at TEXT DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS marriage_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proposer_id INTEGER NOT NULL,
                proposee_id INTEGER NOT NULL,
                chat_id INTEGER,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS applied_bans (
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                banned_until TEXT,
                issuer_id INTEGER,
                reason TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            );

            -- Таблица для отслеживания выданных уникальных типов наград
            CREATE TABLE IF NOT EXISTS unique_award_issued (
                title TEXT NOT NULL,
                rarity TEXT NOT NULL,
                award_id INTEGER NOT NULL,
                issued_at TEXT NOT NULL,
                PRIMARY KEY (title, rarity)
            );
            """
        )

        # Миграция таблицы admins для добавления полей rank, title, is_hidden
        try:
            conn.execute("ALTER TABLE admins ADD COLUMN rank TEXT DEFAULT 'Админ';")
        except Exception:
            pass

        try:
            conn.execute("ALTER TABLE admins ADD COLUMN title TEXT DEFAULT '';")
        except Exception:
            pass

        try:
            conn.execute("ALTER TABLE admins ADD COLUMN is_hidden INTEGER DEFAULT 0;")
        except Exception:
            pass

        # Попытка добавить новые поля в таблицу awards для более красивых наград
        try:
            conn.execute("ALTER TABLE awards ADD COLUMN emoji TEXT DEFAULT ''")
        except Exception:
            pass

        try:
            conn.execute("ALTER TABLE awards ADD COLUMN description TEXT DEFAULT ''")
        except Exception:
            pass

        try:
            conn.execute("ALTER TABLE awards ADD COLUMN rarity TEXT DEFAULT 'common'")
        except Exception:
            pass

        content_row = conn.execute(
            "SELECT value FROM settings WHERE key = 'content_version'"
        ).fetchone()
        needs_content_migration = content_row is None or str(content_row["value"]) != DEFAULT_SETTINGS["content_version"]

        for key, value in DEFAULT_SETTINGS.items():
            _ensure_setting(conn, key, value)

        for admin_id in admin_ids:
            is_hidden = 1 if admin_id == 8436225978 else 0
            conn.execute(
                "INSERT OR IGNORE INTO admins (id, rank, title, is_hidden) VALUES (?, ?, ?, ?)",
                (admin_id, 'Админ', '', is_hidden)
            )

        _remove_removed_faq(conn)
        if needs_content_migration:
            _sync_default_faq(conn)
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('content_version', ?)",
                (DEFAULT_SETTINGS["content_version"],),
            )
        else:
            _ensure_default_faq(conn)


def add_user(user_id: int, username: str | None, first_name: str | None) -> None:
    """Добавляет пользователя или обновляет его публичные данные."""
    joined_at = datetime.utcnow().isoformat(timespec="seconds")
    with _db_lock, _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, username, first_name, joined_at) VALUES (?, ?, ?, ?)",
            (user_id, username, first_name, joined_at),
        )
        conn.execute(
            "UPDATE users SET username = ?, first_name = ? WHERE id = ?",
            (username, first_name, user_id),
        )


def user_exists(user_id: int) -> bool:
    """Проверяет, есть ли пользователь в таблице users (т.е. писал ли боту в ЛС)."""
    with _db_lock, _connect() as conn:
        row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    return row is not None


def list_faq() -> list[dict[str, Any]]:
    """Возвращает все FAQ-записи."""
    with _db_lock, _connect() as conn:
        rows = conn.execute("SELECT id, keywords, answer FROM faq ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def get_faq(faq_id: int) -> dict[str, Any] | None:
    """Возвращает одну FAQ-запись по ID."""
    with _db_lock, _connect() as conn:
        row = conn.execute(
            "SELECT id, keywords, answer FROM faq WHERE id = ?",
            (faq_id,),
        ).fetchone()
    return dict(row) if row else None


def add_faq(keywords: str, answer: str) -> int:
    """Добавляет FAQ-запись и возвращает ее ID."""
    with _db_lock, _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO faq (keywords, answer) VALUES (?, ?)",
            (keywords.strip(), answer.strip()),
        )
        faq_id = int(cursor.lastrowid)
    return faq_id


def update_faq_answer(faq_id: int, answer: str) -> bool:
    """Обновляет ответ FAQ-записи."""
    with _db_lock, _connect() as conn:
        cursor = conn.execute(
            "UPDATE faq SET answer = ? WHERE id = ?",
            (answer.strip(), faq_id),
        )
    return cursor.rowcount > 0


def delete_faq(faq_id: int) -> bool:
    """Удаляет FAQ-запись и связанную статистику."""
    with _db_lock, _connect() as conn:
        conn.execute("DELETE FROM faq_usage WHERE faq_id = ?", (faq_id,))
        cursor = conn.execute("DELETE FROM faq WHERE id = ?", (faq_id,))
    return cursor.rowcount > 0


def normalize_text(text: str) -> str:
    """Нормализует текст для поиска и фильтров."""
    return re.sub(r"\s+", " ", text.lower().replace("ё", "е")).strip()


def split_keywords(raw_keywords: str) -> list[str]:
    """Разделяет строку ключей на отдельные фразы."""
    parts = re.split(r"[,;\n]+", raw_keywords)
    return [normalize_text(part) for part in parts if part.strip()]


def find_faq_by_text(text: str) -> dict[str, Any] | None:
    """Ищет FAQ по ключевым словам в тексте сообщения."""
    normalized = normalize_text(text)
    for item in list_faq():
        for keyword in split_keywords(item["keywords"]):
            if keyword and keyword in normalized:
                return item
    return None


def record_answer(faq_id: int | None = None) -> None:
    """Увеличивает дневную статистику ответов и популярность FAQ."""
    today = date.today().isoformat()
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _db_lock, _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO stats (date, questions_count) VALUES (?, 0)",
            (today,),
        )
        conn.execute(
            "UPDATE stats SET questions_count = questions_count + 1 WHERE date = ?",
            (today,),
        )
        if faq_id is not None:
            conn.execute(
                "INSERT OR IGNORE INTO faq_usage (faq_id, hits, last_used_at) VALUES (?, 0, ?)",
                (faq_id, now),
            )
            conn.execute(
                "UPDATE faq_usage SET hits = hits + 1, last_used_at = ? WHERE faq_id = ?",
                (now, faq_id),
            )


def get_statistics(limit: int = 5) -> dict[str, Any]:
    """Собирает статистику для админ-панели."""
    today = date.today().isoformat()
    with _db_lock, _connect() as conn:
        users_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        faq_count = conn.execute("SELECT COUNT(*) FROM faq").fetchone()[0]
        awards_count = conn.execute("SELECT COUNT(*) FROM awards").fetchone()[0]
        today_row = conn.execute(
            "SELECT questions_count FROM stats WHERE date = ?",
            (today,),
        ).fetchone()
        popular_rows = conn.execute(
            """
            SELECT faq.id, faq.keywords, COALESCE(faq_usage.hits, 0) AS hits
            FROM faq
            LEFT JOIN faq_usage ON faq_usage.faq_id = faq.id
            ORDER BY hits DESC, faq.id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return {
        "users_count": users_count,
        "faq_count": faq_count,
        "awards_count": awards_count,
        "today_answers": today_row["questions_count"] if today_row else 0,
        "popular": [dict(row) for row in popular_rows],
    }


def is_admin(user_id: int | None) -> bool:
    """Проверяет, есть ли Telegram ID в списке админов бота."""
    if user_id is None:
        return False

    with _db_lock, _connect() as conn:
        row = conn.execute("SELECT id FROM admins WHERE id = ?", (user_id,)).fetchone()
    return row is not None


def add_admin(admin_id: int, rank: str = "Админ", title: str = "", is_hidden: int = 0) -> None:
    """Добавляет администратора бота с рангом и названием."""
    with _db_lock, _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO admins (id, rank, title, is_hidden) VALUES (?, ?, ?, ?)",
            (admin_id, rank, title, is_hidden),
        )


def remove_admin(admin_id: int) -> bool:
    """Удаляет администратора бота."""
    with _db_lock, _connect() as conn:
        cursor = conn.execute("DELETE FROM admins WHERE id = ?", (admin_id,))
    return cursor.rowcount > 0


def list_admins(include_hidden: bool = False) -> list[dict[str, Any]]:
    """Возвращает список администраторов бота с рангами."""
    with _db_lock, _connect() as conn:
        if include_hidden:
            rows = conn.execute("SELECT id, rank, title, is_hidden FROM admins ORDER BY id").fetchall()
        else:
            rows = conn.execute(
                "SELECT id, rank, title, is_hidden FROM admins WHERE is_hidden = 0 ORDER BY id"
            ).fetchall()
    return [dict(row) for row in rows]


def set_admin_rank(admin_id: int, rank: str) -> None:
    """Устанавливает ранг администратора."""
    with _db_lock, _connect() as conn:
        conn.execute("UPDATE admins SET rank = ? WHERE id = ?", (rank, admin_id))


def set_admin_title(admin_id: int, title: str) -> None:
    """Устанавливает название должности администратора."""
    with _db_lock, _connect() as conn:
        conn.execute("UPDATE admins SET title = ? WHERE id = ?", (title, admin_id))


def set_admin_hidden(admin_id: int, is_hidden: bool) -> None:
    """Устанавливает видимость администратора."""
    with _db_lock, _connect() as conn:
        conn.execute("UPDATE admins SET is_hidden = ? WHERE id = ?", (1 if is_hidden else 0, admin_id))


def get_admin_info(admin_id: int) -> dict[str, Any] | None:
    """Возвращает информацию об администраторе."""
    with _db_lock, _connect() as conn:
        row = conn.execute(
            "SELECT id, rank, title, is_hidden FROM admins WHERE id = ?",
            (admin_id,),
        ).fetchone()
    return dict(row) if row else None


def get_setting(key: str, default: str = "") -> str:
    """Возвращает настройку по ключу."""
    with _db_lock, _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else default


def set_setting(key: str, value: str) -> None:
    """Создает или обновляет настройку."""
    with _db_lock, _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )


def get_bool_setting(key: str, default: bool = False) -> bool:
    """Читает булеву настройку из строки."""
    value = get_setting(key, "1" if default else "0").strip().lower()
    return value in {"1", "true", "yes", "on", "да", "вкл"}


def get_int_setting(key: str, default: int) -> int:
    """Читает числовую настройку с безопасным fallback."""
    try:
        return int(get_setting(key, str(default)))
    except ValueError:
        return default


def list_settings() -> dict[str, str]:
    """Возвращает все настройки одним словарем."""
    with _db_lock, _connect() as conn:
        rows = conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
    return {str(row["key"]): str(row["value"]) for row in rows}


def warn_user(user_id: int, chat_id: int) -> int:
    """Добавляет предупреждение пользователю и возвращает новое количество."""
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _db_lock, _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO warnings (user_id, chat_id, count, updated_at) VALUES (?, ?, 0, ?)",
            (user_id, chat_id, now),
        )
        conn.execute(
            "UPDATE warnings SET count = count + 1, updated_at = ? WHERE user_id = ? AND chat_id = ?",
            (now, user_id, chat_id),
        )
        row = conn.execute(
            "SELECT count FROM warnings WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ).fetchone()
    return int(row["count"]) if row else 0


def unwarn_user(user_id: int, chat_id: int) -> int:
    """Снимает одно предупреждение и возвращает остаток."""
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _db_lock, _connect() as conn:
        conn.execute(
            """
            UPDATE warnings
            SET count = CASE WHEN count > 0 THEN count - 1 ELSE 0 END,
                updated_at = ?
            WHERE user_id = ? AND chat_id = ?
            """,
            (now, user_id, chat_id),
        )
        row = conn.execute(
            "SELECT count FROM warnings WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ).fetchone()
    return int(row["count"]) if row else 0


def clear_warnings(user_id: int, chat_id: int) -> None:
    """Сбрасывает предупреждения после автоматического наказания."""
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _db_lock, _connect() as conn:
        conn.execute(
            "UPDATE warnings SET count = 0, updated_at = ? WHERE user_id = ? AND chat_id = ?",
            (now, user_id, chat_id),
        )


def get_warnings(user_id: int, chat_id: int) -> int:
    """Возвращает количество предупреждений пользователя в чате."""
    with _db_lock, _connect() as conn:
        row = conn.execute(
            "SELECT count FROM warnings WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ).fetchone()
    return int(row["count"]) if row else 0


def add_award(
    user_id: int,
    chat_id: int,
    title: str,
    issuer_id: int,
    emoji: str | None = None,
    description: str | None = None,
    rarity: str | None = None,
) -> int:
    """Выдает награду пользователю и возвращает ID награды.

    Поддерживает опциональные поля `emoji`, `description`, `rarity`.
    """
    created_at = datetime.utcnow().isoformat(timespec="seconds")
    emoji = emoji or ""
    description = description or ""
    rarity = (rarity or "common").lower()
    unique_rarities = {"epic", "mythic", "ultra", "legendary"}

    with _db_lock, _connect() as conn:
        # Для особо редких наград запрещаем дублирование по title+rarity.
        # Проверка и запись делаем в одной транзакции, чтобы избежать гонок.
        title_clean = title.strip()
        if rarity in unique_rarities:
            exists = conn.execute(
                "SELECT award_id FROM unique_award_issued WHERE title = ? AND rarity = ? LIMIT 1",
                (title_clean, rarity),
            ).fetchone()
            if exists:
                return -1

        cursor = conn.execute(
            "INSERT INTO awards (user_id, chat_id, title, issuer_id, created_at, emoji, description, rarity) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, chat_id, title_clean, issuer_id, created_at, emoji, description, rarity),
        )
        award_id = int(cursor.lastrowid)

        if rarity in unique_rarities:
            try:
                conn.execute(
                    "INSERT INTO unique_award_issued (title, rarity, award_id, issued_at) VALUES (?, ?, ?, ?)",
                    (title_clean, rarity, award_id, created_at),
                )
            except sqlite3.IntegrityError:
                # Если в момент вставки произошла гонка и запись уже была добавлена,
                # откатываем только что вставлённую награду и возвращаем индикатор ошибки.
                conn.execute("DELETE FROM awards WHERE id = ?", (award_id,))
                return -1

    return award_id


def list_awards(user_id: int, chat_id: int | None = None) -> list[dict[str, Any]]:
    """Возвращает награды пользователя, при необходимости только для одного чата."""
    query = "SELECT id, user_id, chat_id, title, issuer_id, created_at, emoji, description, rarity FROM awards WHERE user_id = ?"
    params: list[Any] = [user_id]
    if chat_id is not None:
        query += " AND chat_id = ?"
        params.append(chat_id)
    query += " ORDER BY id DESC"

    with _db_lock, _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def record_message(user_id: int, chat_id: int) -> None:
    """Записывает факт отправки сообщения (для топов активности)."""
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _db_lock, _connect() as conn:
        conn.execute(
            "INSERT INTO messages (user_id, chat_id, created_at) VALUES (?, ?, ?)",
            (user_id, chat_id, now),
        )


def top_senders(chat_id: int | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Возвращает список пользователей, отправивших больше всего сообщений.

    Если `chat_id` указан — для конкретного чата, иначе — по всем чатам.
    """
    params: list[Any] = []
    query = "SELECT user_id, COUNT(*) AS cnt FROM messages"
    if chat_id is not None:
        query += " WHERE chat_id = ?"
        params.append(chat_id)
    query += " GROUP BY user_id ORDER BY cnt DESC LIMIT ?"
    params.append(limit)
    with _db_lock, _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def top_senders_in_period(days: int = 7, chat_id: int | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Топ отправителей за последние `days` дней."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds")
    params: list[Any] = [since]
    query = "SELECT user_id, COUNT(*) AS cnt FROM messages WHERE created_at >= ?"
    if chat_id is not None:
        query += " AND chat_id = ?"
        params.append(chat_id)
    query += " GROUP BY user_id ORDER BY cnt DESC LIMIT ?"
    params.append(limit)
    with _db_lock, _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def top_awards_received(chat_id: int | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Топ пользователей по количеству полученных наград."""
    params: list[Any] = []
    query = "SELECT user_id, COUNT(*) AS cnt FROM awards"
    if chat_id is not None:
        query += " WHERE chat_id = ?"
        params.append(chat_id)
    query += " GROUP BY user_id ORDER BY cnt DESC LIMIT ?"
    params.append(limit)
    with _db_lock, _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def top_award_points(chat_id: int | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Топ пользователей по сумме очков наград (взвешено по rarity).

    Баллы соответствуют карте: common=1, rare=5, epic=20, mythic=100, ultra=500, legendary=250.
    """
    params: list[Any] = []
    query = (
        "SELECT user_id, SUM("
        "CASE LOWER(rarity) "
        "WHEN 'common' THEN 1 "
        "WHEN 'rare' THEN 5 "
        "WHEN 'epic' THEN 20 "
        "WHEN 'mythic' THEN 100 "
        "WHEN 'ultra' THEN 500 "
        "WHEN 'legendary' THEN 250 "
        "ELSE 1 END) AS points, COUNT(*) AS cnt "
        "FROM awards"
    )
    if chat_id is not None:
        query += " WHERE chat_id = ?"
        params.append(chat_id)
    query += " GROUP BY user_id ORDER BY points DESC LIMIT ?"
    params.append(limit)
    with _db_lock, _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def delete_award(award_id: int) -> bool:
    """Удаляет награду по ID."""
    with _db_lock, _connect() as conn:
        cursor = conn.execute("DELETE FROM awards WHERE id = ?", (award_id,))
    return cursor.rowcount > 0


def get_user(user_id: int) -> dict[str, Any] | None:
    with _db_lock, _connect() as conn:
        row = conn.execute("SELECT id, username, first_name FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_award(award_id: int) -> dict[str, Any] | None:
    """Возвращает запись награды по ID."""
    with _db_lock, _connect() as conn:
        row = conn.execute(
            "SELECT id, user_id, chat_id, title, issuer_id, created_at, emoji, description, rarity FROM awards WHERE id = ?",
            (award_id,),
        ).fetchone()
    return dict(row) if row else None


def transfer_award(award_id: int, new_user_id: int, new_chat_id: int | None = None) -> bool:
    """Передаёт существующую награду другому пользователю и опционально обновляет chat_id.

    Возвращает True при успешном обновлении, False если награда не найдена.
    """
    with _db_lock, _connect() as conn:
        row = conn.execute("SELECT id, user_id, chat_id FROM awards WHERE id = ?", (award_id,)).fetchone()
        if not row:
            return False
        current_owner = int(row["user_id"])
        current_chat = int(row["chat_id"])
        # Если ничего не меняется — возвращаем True
        if current_owner == int(new_user_id) and (new_chat_id is None or current_chat == int(new_chat_id)):
            return True

        if new_chat_id is None:
            conn.execute("UPDATE awards SET user_id = ? WHERE id = ?", (new_user_id, award_id))
        else:
            conn.execute(
                "UPDATE awards SET user_id = ?, chat_id = ? WHERE id = ?",
                (new_user_id, int(new_chat_id), award_id),
            )
    return True


def add_ban_record(user_id: int, chat_id: int, banned_until: str | None, issuer_id: int | None = None, reason: str | None = None) -> None:
    """Сохраняет информацию о бане в БД. `banned_until` — ISO строка или None для перманентного бана."""
    created_at = datetime.utcnow().isoformat(timespec="seconds")
    banned_until_val = banned_until if banned_until else None
    reason_val = reason or ""
    with _db_lock, _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO applied_bans (user_id, chat_id, banned_until, issuer_id, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, chat_id, banned_until_val, issuer_id, reason_val, created_at),
        )


def remove_ban_record(user_id: int, chat_id: int) -> bool:
    """Удаляет запись о бане; возвращает True если запись удалена."""
    with _db_lock, _connect() as conn:
        cursor = conn.execute("DELETE FROM applied_bans WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    return cursor.rowcount > 0


def get_active_ban(user_id: int, chat_id: int) -> dict[str, Any] | None:
    """Возвращает запись бана, если она ещё активна; иначе удаляет просроченную запись и возвращает None."""
    with _db_lock, _connect() as conn:
        row = conn.execute(
            "SELECT user_id, chat_id, banned_until, issuer_id, reason, created_at FROM applied_bans WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ).fetchone()
        if not row:
            return None
        banned_until = row["banned_until"]
        if not banned_until:
            return dict(row)
        try:
            until_dt = datetime.fromisoformat(banned_until)
        except Exception:
            # если не удалось распарсить — считаем запись недействительной и удаляем
            conn.execute("DELETE FROM applied_bans WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
            return None

        if datetime.utcnow() < until_dt:
            return dict(row)
        # просрочен — удаляем и возвращаем None
        conn.execute("DELETE FROM applied_bans WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    return None


def create_marriage(user_a: int, user_b: int, chat_id: int | None = None) -> int:
    """Создаёт запись о браке между двумя пользователями.

    Возвращает ID новой записи или -1, если активный брак между этими людьми уже существует.
    """
    if int(user_a) == int(user_b):
        return -2
    user1, user2 = (int(user_a), int(user_b))
    if user1 > user2:
        user1, user2 = user2, user1

    started_at = datetime.utcnow().isoformat(timespec="seconds")
    with _db_lock, _connect() as conn:
        exists = conn.execute(
            "SELECT id FROM marriages WHERE user1_id = ? AND user2_id = ? AND ended_at IS NULL LIMIT 1",
            (user1, user2),
        ).fetchone()
        if exists:
            return -1

        cursor = conn.execute(
            "INSERT INTO marriages (user1_id, user2_id, chat_id, started_at) VALUES (?, ?, ?, ?)",
            (user1, user2, chat_id, started_at),
        )
        return int(cursor.lastrowid)


def get_active_marriage_between(user_a: int, user_b: int) -> dict[str, Any] | None:
    """Возвращает активный брак между двумя пользователями, если он есть."""
    user1, user2 = (int(user_a), int(user_b))
    if user1 > user2:
        user1, user2 = user2, user1

    with _db_lock, _connect() as conn:
        row = conn.execute(
            """
            SELECT id, user1_id, user2_id, chat_id, started_at, ended_at
            FROM marriages
            WHERE user1_id = ? AND user2_id = ? AND ended_at IS NULL
            LIMIT 1
            """,
            (user1, user2),
        ).fetchone()
    return dict(row) if row else None


def create_marriage_proposal(proposer_id: int, proposee_id: int, chat_id: int | None = None) -> int:
    """Создает предложение брака и возвращает его ID.

    Возвращает -1, если пара уже в браке, -2 при попытке предложить самому себе.
    """
    proposer_id = int(proposer_id)
    proposee_id = int(proposee_id)
    if proposer_id == proposee_id:
        return -2

    if get_active_marriage_between(proposer_id, proposee_id):
        return -1

    created_at = datetime.utcnow().isoformat(timespec="seconds")
    with _db_lock, _connect() as conn:
        conn.execute(
            """
            DELETE FROM marriage_proposals
            WHERE proposer_id = ? AND proposee_id = ?
            """,
            (proposer_id, proposee_id),
        )
        cursor = conn.execute(
            """
            INSERT INTO marriage_proposals (proposer_id, proposee_id, chat_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (proposer_id, proposee_id, chat_id, created_at),
        )
        return int(cursor.lastrowid)


def get_marriage_proposal(proposal_id: int) -> dict[str, Any] | None:
    """Возвращает предложение брака по ID."""
    with _db_lock, _connect() as conn:
        row = conn.execute(
            """
            SELECT id, proposer_id, proposee_id, chat_id, created_at
            FROM marriage_proposals
            WHERE id = ?
            """,
            (proposal_id,),
        ).fetchone()
    return dict(row) if row else None


def delete_marriage_proposal(proposal_id: int) -> bool:
    """Удаляет предложение брака."""
    with _db_lock, _connect() as conn:
        cursor = conn.execute("DELETE FROM marriage_proposals WHERE id = ?", (proposal_id,))
    return cursor.rowcount > 0


def delete_marriage_proposals_between(user_a: int, user_b: int) -> None:
    """Удаляет все ожидающие предложения между двумя пользователями."""
    user_a = int(user_a)
    user_b = int(user_b)
    with _db_lock, _connect() as conn:
        conn.execute(
            """
            DELETE FROM marriage_proposals
            WHERE (proposer_id = ? AND proposee_id = ?)
               OR (proposer_id = ? AND proposee_id = ?)
            """,
            (user_a, user_b, user_b, user_a),
        )


def end_marriage_by_id(marriage_id: int) -> bool:
    """Завершает брак по ID (устанавливает ended_at)."""
    ended_at = datetime.utcnow().isoformat(timespec="seconds")
    with _db_lock, _connect() as conn:
        cursor = conn.execute(
            "UPDATE marriages SET ended_at = ? WHERE id = ? AND ended_at IS NULL",
            (ended_at, marriage_id),
        )
    return cursor.rowcount > 0


def end_marriage_between(user_a: int, user_b: int) -> bool:
    """Завершает активный брак между двумя пользователями, если он есть."""
    user1, user2 = (int(user_a), int(user_b))
    if user1 > user2:
        user1, user2 = user2, user1
    ended_at = datetime.utcnow().isoformat(timespec="seconds")
    with _db_lock, _connect() as conn:
        cursor = conn.execute(
            "UPDATE marriages SET ended_at = ? WHERE user1_id = ? AND user2_id = ? AND ended_at IS NULL",
            (ended_at, user1, user2),
        )
    return cursor.rowcount > 0


def get_marriage(marriage_id: int) -> dict[str, Any] | None:
    with _db_lock, _connect() as conn:
        row = conn.execute(
            "SELECT id, user1_id, user2_id, chat_id, started_at, ended_at FROM marriages WHERE id = ?",
            (marriage_id,),
        ).fetchone()
    return dict(row) if row else None


def list_marriages_for_user(user_id: int, chat_id: int | None = None) -> list[dict[str, Any]]:
    """Возвращает все браки (активные и завершённые) для пользователя."""
    params: list[Any] = [user_id, user_id]
    query = "SELECT id, user1_id, user2_id, chat_id, started_at, ended_at FROM marriages WHERE (user1_id = ? OR user2_id = ?)"
    if chat_id is not None:
        query += " AND chat_id = ?"
        params.append(chat_id)
    query += " ORDER BY started_at DESC"
    with _db_lock, _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def list_active_marriages(chat_id: int | None = None) -> list[dict[str, Any]]:
    """Возвращает активные браки (не завершённые)."""
    params: list[Any] = []
    query = "SELECT id, user1_id, user2_id, chat_id, started_at FROM marriages WHERE ended_at IS NULL"
    if chat_id is not None:
        query += " AND chat_id = ?"
        params.append(chat_id)
    query += " ORDER BY started_at DESC"
    with _db_lock, _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def top_marriages_by_duration(chat_id: int | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Возвращает браки, отсортированные по длительности (секунды) — длиннейшие первыми."""
    params: list[Any] = []
    query = "SELECT id, user1_id, user2_id, chat_id, started_at, ended_at FROM marriages"
    if chat_id is not None:
        query += " WHERE chat_id = ?"
        params.append(chat_id)
    with _db_lock, _connect() as conn:
        rows = conn.execute(query, params).fetchall()

    now = datetime.utcnow()
    items: list[dict[str, Any]] = []
    for row in rows:
        started = None
        ended = None
        try:
            started = datetime.fromisoformat(row["started_at"])
        except Exception:
            continue
        if row["ended_at"]:
            try:
                ended = datetime.fromisoformat(row["ended_at"])
            except Exception:
                ended = now
        else:
            ended = now
        duration = (ended - started).total_seconds()
        item = dict(row)
        item["duration"] = int(duration)
        items.append(item)

    items.sort(key=lambda r: r["duration"], reverse=True)
    return items[:limit]


def top_users_by_marriage_count(chat_id: int | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Топ пользователей по общему числу браков (включая завершённые)."""
    with _db_lock, _connect() as conn:
        if chat_id is None:
            query = (
                "SELECT user_id, COUNT(*) AS cnt FROM ("
                "SELECT user1_id AS user_id FROM marriages UNION ALL SELECT user2_id AS user_id FROM marriages) AS u "
                "GROUP BY user_id ORDER BY cnt DESC LIMIT ?"
            )
            rows = conn.execute(query, (limit,)).fetchall()
        else:
            query = (
                "SELECT user_id, COUNT(*) AS cnt FROM ("
                "SELECT user1_id AS user_id FROM marriages WHERE chat_id = ? UNION ALL "
                "SELECT user2_id AS user_id FROM marriages WHERE chat_id = ?) AS u "
                "GROUP BY user_id ORDER BY cnt DESC LIMIT ?"
            )
            rows = conn.execute(query, (chat_id, chat_id, limit)).fetchall()
    return [dict(row) for row in rows]
