"""FSM-состояния админ-панели и пользовательских сценариев."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class FAQAdd(StatesGroup):
    """Состояния добавления FAQ-записи."""

    keywords = State()
    answer = State()


class FAQEdit(StatesGroup):
    """Состояние редактирования ответа FAQ."""

    answer = State()


class AdminManage(StatesGroup):
    """Состояние добавления администратора."""

    add_admin_id = State()


class SettingsManage(StatesGroup):
    """Состояния редактирования настроек."""

    rules_text = State()
    bad_words = State()
    warn_limit = State()
    warn_mute_minutes = State()
    default_mute_minutes = State()
    default_ban_minutes = State()
    ads_receiver_id = State()


class AdRequest(StatesGroup):
    """Состояние отправки рекламного предложения."""

    content = State()

