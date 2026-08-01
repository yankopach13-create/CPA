"""Конфигурация источника справочника (Google Sheets / локальный Excel)."""

import os
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_CREDENTIALS_PATH = PROJECT_DIR / "google_credentials.json"


def _to_plain_dict(section: Any) -> dict[str, Any]:
    """Преобразует dict или Streamlit Secrets в обычный словарь."""
    if section is None:
        return {}
    if isinstance(section, dict):
        return dict(section)
    if hasattr(section, "keys"):
        return {key: section[key] for key in section.keys()}
    return {}


def _read_google_section(streamlit_secrets: Any) -> dict[str, Any]:
    """Читает секцию [google] из st.secrets."""
    if streamlit_secrets is None:
        return {}

    try:
        return _to_plain_dict(streamlit_secrets["google"])
    except (KeyError, TypeError, AttributeError):
        if hasattr(streamlit_secrets, "get"):
            return _to_plain_dict(streamlit_secrets.get("google"))
        return {}


def resolve_spravochnik_settings(
    sheets_id: str | None = None,
    credentials_path: str | None = None,
    credentials_info: dict[str, Any] | None = None,
    streamlit_secrets: Any | None = None,
) -> dict[str, Any]:
    """
    Собирает настройки справочника из аргументов, переменных окружения и secrets.

    Приоритет: явные аргументы → Streamlit secrets → переменные окружения.
    """
    resolved_sheets_id = sheets_id or os.environ.get("GOOGLE_SHEETS_ID")
    resolved_credentials_path = credentials_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    resolved_credentials_info = credentials_info

    google_cfg = _read_google_section(streamlit_secrets)
    if google_cfg:
        if not resolved_sheets_id:
            resolved_sheets_id = google_cfg.get("sheets_id")
        if not resolved_credentials_path:
            resolved_credentials_path = google_cfg.get("credentials_path")
        if resolved_credentials_info is None and "service_account" in google_cfg:
            resolved_credentials_info = _to_plain_dict(google_cfg["service_account"])

    if resolved_credentials_info:
        resolved_credentials_info = dict(resolved_credentials_info)
        private_key = resolved_credentials_info.get("private_key")
        if private_key is not None:
            resolved_credentials_info["private_key"] = str(private_key)

    if not resolved_credentials_path and resolved_credentials_info is None:
        if DEFAULT_CREDENTIALS_PATH.exists():
            resolved_credentials_path = str(DEFAULT_CREDENTIALS_PATH)

    return {
        "sheets_id": resolved_sheets_id,
        "credentials_path": resolved_credentials_path,
        "credentials_info": resolved_credentials_info,
    }


def validate_spravochnik_settings(settings: dict[str, Any]) -> None:
    """Проверяет, что для Google Sheets заданы ID таблицы и учётные данные."""
    if not settings.get("sheets_id"):
        raise ValueError(
            "Не указан sheets_id. Добавьте в Secrets: [google] sheets_id = \"...\""
        )

    has_file = bool(settings.get("credentials_path"))
    has_info = bool(settings.get("credentials_info"))
    if not has_file and not has_info:
        raise ValueError(
            "Не найдены учётные данные Google. "
            "Добавьте в Secrets секцию [google.service_account] с полями из JSON-ключа."
        )
