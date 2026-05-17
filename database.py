"""Работа с SQLite для BIBISHKA Admin Bot."""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime
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
        "📣 По рекламе открой раздел «Реклама» в /start и отправь предложение. Оно уйдет ответственному администратору.",
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
    "ai_enabled": "1",
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

        # Миграция таблицы game_participants: если старой схемы без chat_id
        try:
            info = conn.execute("PRAGMA table_info(game_participants)").fetchall()
            cols = [row[1] for row in info] if info else []
            if info and "chat_id" not in cols:
                # Создаём новую таблицу с нужной схемой и переносим данные
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS game_participants_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        username TEXT,
                        chat_id INTEGER NOT NULL DEFAULT 0,
                        joined_at TEXT NOT NULL,
                        UNIQUE(user_id, chat_id)
                    );
                    """
                )
                rows = conn.execute(
                    "SELECT id, user_id, username, joined_at FROM game_participants"
                ).fetchall()
                for row in rows:
                    conn.execute(
                        "INSERT OR IGNORE INTO game_participants_new (user_id, username, chat_id, joined_at) VALUES (?, ?, ?, ?)",
                        (row[1], row[2], 0, row[3]),
                    )
                conn.execute("DROP TABLE game_participants")
                conn.execute("ALTER TABLE game_participants_new RENAME TO game_participants")
        except Exception:
            # Если чего-то не получилось — просто логируем и продолжаем
            logger.debug("Нет необходимости мигрировать game_participants или миграция не удалась", exc_info=True)


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
                created_at TEXT NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS game_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                chat_id INTEGER NOT NULL DEFAULT 0,
                joined_at TEXT NOT NULL,
                UNIQUE(user_id, chat_id)
            );
            """
        )

        # Миграция таблицы admins для добавления полей rank, title, is_hidden
        try:
            conn.execute(
                """
                ALTER TABLE admins ADD COLUMN rank TEXT DEFAULT 'Админ';
                """
            )
        except Exception:
            pass  # Колонки уже существуют

        try:
            conn.execute(
                """
                ALTER TABLE admins ADD COLUMN title TEXT DEFAULT '';
                """
            )
        except Exception:
            pass  # Колонки уже существуют

        try:
            conn.execute(
                """
                ALTER TABLE admins ADD COLUMN is_hidden INTEGER DEFAULT 0;
                """
            )
        except Exception:
            pass  # Колонки уже существуют

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

        # Создаём вспомогательные таблицы для игр и лидеров
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    finished_at TEXT
                );

                CREATE TABLE IF NOT EXISTS game_players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    role TEXT,
                    alive INTEGER NOT NULL DEFAULT 1,
                    last_word TEXT
                );

                CREATE TABLE IF NOT EXISTS wins (
                    user_id INTEGER PRIMARY KEY,
                    wins INTEGER NOT NULL DEFAULT 0
                );
                """
            )
        except Exception:
            logger.exception("Не удалось создать таблицы для игр")


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
            (admin_id, rank, title, is_hidden)
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
            (admin_id,)
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


def add_award(user_id: int, chat_id: int, title: str, issuer_id: int) -> int:
    """Выдает награду пользователю и возвращает ID награды."""
    created_at = datetime.utcnow().isoformat(timespec="seconds")
    with _db_lock, _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO awards (user_id, chat_id, title, issuer_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, chat_id, title.strip(), issuer_id, created_at),
        )
        award_id = int(cursor.lastrowid)
    return award_id


def list_awards(user_id: int, chat_id: int | None = None) -> list[dict[str, Any]]:
    """Возвращает награды пользователя, при необходимости только для одного чата."""
    query = "SELECT id, user_id, chat_id, title, issuer_id, created_at FROM awards WHERE user_id = ?"
    params: list[Any] = [user_id]
    if chat_id is not None:
        query += " AND chat_id = ?"
        params.append(chat_id)
    query += " ORDER BY id DESC"

    with _db_lock, _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def delete_award(award_id: int) -> bool:
    """Удаляет награду по ID."""
    with _db_lock, _connect() as conn:
        cursor = conn.execute("DELETE FROM awards WHERE id = ?", (award_id,))
    return cursor.rowcount > 0




def add_game_participant(user_id: int, username: str | None, chat_id: int | None) -> bool:
    """Добавляет пользователя в список участников игры для конкретного чата.
    Возвращает True, если запись была вставлена, False если уже есть.
    """
    joined_at = datetime.utcnow().isoformat(timespec="seconds")
    with _db_lock, _connect() as conn:
        try:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO game_participants (user_id, username, chat_id, joined_at) VALUES (?, ?, ?, ?)",
                (user_id, username, chat_id or 0, joined_at),
            )
            return cursor.rowcount > 0
        except Exception:
            logger.exception("Не удалось добавить участника игры в БД")
            return False




def is_game_participant(user_id: int, chat_id: int | None) -> bool:
    """Проверяет, участвует ли пользователь в игре для конкретного чата."""
    with _db_lock, _connect() as conn:
        row = conn.execute(
            "SELECT id FROM game_participants WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id or 0),
        ).fetchone()
    return row is not None


def is_game_participant_global(user_id: int) -> bool:
    """Проверяет, есть ли пользователь в любой игре."""
    with _db_lock, _connect() as conn:
        row = conn.execute(
            "SELECT id FROM game_participants WHERE user_id = ? LIMIT 1",
            (user_id,),
        ).fetchone()
    return row is not None




def list_game_participants(limit: int = 100, chat_id: int | None = None) -> list[dict[str, Any]]:
    """Возвращает список участников игры.

    Если `chat_id` указан, возвращает участников только для этого чата.
    """
    with _db_lock, _connect() as conn:
        if chat_id is None:
            rows = conn.execute(
                "SELECT id, user_id, username, chat_id, joined_at FROM game_participants ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, user_id, username, chat_id, joined_at FROM game_participants WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
                (chat_id, limit),
            ).fetchall()
    return [dict(row) for row in rows]


def create_game(chat_id: int) -> int:
    """Создаёт запись игры и возвращает её ID."""
    created_at = datetime.utcnow().isoformat(timespec="seconds")
    with _db_lock, _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO games (chat_id, status, created_at) VALUES (?, 'active', ?)",
            (chat_id, created_at),
        )
        return int(cursor.lastrowid)


def add_game_player(game_id: int, user_id: int, username: str | None, role: str) -> int:
    """Добавляет игрока в игру."""
    with _db_lock, _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO game_players (game_id, user_id, username, role, alive) VALUES (?, ?, ?, ?, 1)",
            (game_id, user_id, username, role),
        )
        return int(cursor.lastrowid)


def remove_game_player(game_id: int, user_id: int) -> None:
    """Удаляет игрока из игры (используется если не удалось отправить ЛС)."""
    with _db_lock, _connect() as conn:
        conn.execute("DELETE FROM game_players WHERE game_id = ? AND user_id = ?", (game_id, user_id))


def get_active_game(chat_id: int) -> dict[str, Any] | None:
    """Возвращает последнюю активную игру в чате, если есть."""
    with _db_lock, _connect() as conn:
        row = conn.execute(
            "SELECT id, chat_id, status, created_at FROM games WHERE chat_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (chat_id,),
        ).fetchone()
    return dict(row) if row else None


def get_game_players(game_id: int) -> list[dict[str, Any]]:
    """Возвращает всех игроков указанной игры."""
    with _db_lock, _connect() as conn:
        rows = conn.execute(
            "SELECT id, game_id, user_id, username, role, alive, last_word FROM game_players WHERE game_id = ?",
            (game_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_game_player(game_id: int, user_id: int) -> dict[str, Any] | None:
    """Возвращает одну запись игрока по game_id и user_id."""
    with _db_lock, _connect() as conn:
        row = conn.execute(
            "SELECT id, game_id, user_id, username, role, alive, last_word FROM game_players WHERE game_id = ? AND user_id = ?",
            (game_id, user_id),
        ).fetchone()
    return dict(row) if row else None


def set_player_last_word(game_id: int, user_id: int, last_word: str | None) -> None:
    """Сохраняет последнее слово игрока."""
    with _db_lock, _connect() as conn:
        conn.execute(
            "UPDATE game_players SET last_word = ? WHERE game_id = ? AND user_id = ?",
            (last_word, game_id, user_id),
        )


def set_player_alive(game_id: int, user_id: int, alive: bool) -> None:
    """Устанавливает состояние alive для игрока."""
    with _db_lock, _connect() as conn:
        conn.execute(
            "UPDATE game_players SET alive = ? WHERE game_id = ? AND user_id = ?",
            (1 if alive else 0, game_id, user_id),
        )


def finish_game(game_id: int, winnerside: str) -> None:
    """Завершает игру и добавляет победы в таблицу wins.

    winnerside: 'mafia' или 'village'
    """
    finished_at = datetime.utcnow().isoformat(timespec="seconds")
    with _db_lock, _connect() as conn:
        conn.execute("UPDATE games SET status = 'finished', finished_at = ? WHERE id = ?", (finished_at, game_id))
        if winnerside == "mafia":
            rows = conn.execute("SELECT user_id FROM game_players WHERE game_id = ? AND role = 'mafia'", (game_id,)).fetchall()
        else:
            rows = conn.execute("SELECT user_id FROM game_players WHERE game_id = ? AND role != 'mafia'", (game_id,)).fetchall()

        for r in rows:
            uid = int(r[0])
            try:
                conn.execute(
                    "INSERT INTO wins (user_id, wins) VALUES (?, 1) ON CONFLICT(user_id) DO UPDATE SET wins = wins + 1",
                    (uid,),
                )
            except Exception:
                # fallback for older SQLite versions: read/update
                cur = conn.execute("SELECT wins FROM wins WHERE user_id = ?", (uid,)).fetchone()
                if cur:
                    conn.execute("UPDATE wins SET wins = ? WHERE user_id = ?", (int(cur[0]) + 1, uid))
                else:
                    conn.execute("INSERT INTO wins (user_id, wins) VALUES (?, 1)", (uid,))


def get_top_wins(limit: int = 10) -> list[dict[str, Any]]:
    """Возвращает топ победителей по убыванию wins."""
    with _db_lock, _connect() as conn:
        rows = conn.execute("SELECT user_id, wins FROM wins ORDER BY wins DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]
