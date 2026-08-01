"""Конфигурация источника справочника (Google Sheets / локальный Excel)."""

import os
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_CREDENTIALS_PATH = PROJECT_DIR / "google_credentials.json"
DEFAULT_SHEETS_ID = "1B5PMa5qlzhf6ssLJ7iansVFPfLjdRlFLdsdyj2aXako"

SERVICE_ACCOUNT_FIELDS = (
    "type",
    "project_id",
    "private_key_id",
    "private_key",
    "client_email",
    "client_id",
    "auth_uri",
    "token_uri",
    "auth_provider_x509_cert_url",
    "client_x509_cert_url",
    "universe_domain",
)


def build_google_sheets_url(sheets_id: str) -> str:
    """Формирует ссылку на Google таблицу справочника."""
    return f"https://docs.google.com/spreadsheets/d/{sheets_id.strip()}/edit"


def _to_plain_dict(section: Any) -> dict[str, Any]:
    """Преобразует dict или Streamlit Secrets в обычный словарь."""
    if section is None:
        return {}
    if isinstance(section, dict):
        return {str(key): value for key, value in section.items()}
    if hasattr(section, "keys"):
        return {str(key): section[key] for key in section.keys()}
    return {}


def _normalize_service_account_info(service_account: Any) -> dict[str, str]:
    """Преобразует service_account из secrets в обычный dict со строковыми полями."""
    raw = _to_plain_dict(service_account)
    if not raw:
        raise ValueError("Секция [google.service_account] в Secrets пуста.")

    normalized: dict[str, str] = {}
    for field in SERVICE_ACCOUNT_FIELDS:
        value = raw.get(field)
        if value is not None and str(value).strip():
            normalized[field] = str(value)

    required = ("type", "project_id", "private_key", "client_email", "token_uri")
    missing = [field for field in required if field not in normalized]
    if missing:
        raise ValueError(
            "В [google.service_account] не хватает полей: "
            + ", ".join(missing)
        )

    normalized["private_key"] = normalized["private_key"].replace("\\n", "\n")
    return normalized


def _read_google_section(streamlit_secrets: Any) -> dict[str, Any]:
    """Читает секцию [google] из st.secrets."""
    if streamlit_secrets is None:
        return {}

    if hasattr(streamlit_secrets, "get"):
        google_section = streamlit_secrets.get("google")
        if google_section is not None:
            return _to_plain_dict(google_section)

    try:
        return _to_plain_dict(streamlit_secrets["google"])
    except (KeyError, TypeError, AttributeError):
        return {}


def get_sheets_id_from_env_or_secrets(streamlit_secrets: Any | None = None) -> str | None:
    """Возвращает ID Google таблицы из secrets или переменных окружения."""
    sheets_id = os.environ.get("GOOGLE_SHEETS_ID")
    if streamlit_secrets is not None:
        google_cfg = _read_google_section(streamlit_secrets)
        if google_cfg.get("sheets_id"):
            sheets_id = str(google_cfg.get("sheets_id")).strip()
    return sheets_id


def get_google_credentials_from_secrets(
    streamlit_secrets: Any,
) -> tuple[str | None, dict[str, str] | None]:
    """Извлекает sheets_id и service_account из st.secrets."""
    google_cfg = _read_google_section(streamlit_secrets)
    if not google_cfg:
        return None, None

    sheets_id = google_cfg.get("sheets_id")
    sheets_id = str(sheets_id).strip() if sheets_id else None

    credentials_info = None
    if "service_account" in google_cfg:
        credentials_info = _normalize_service_account_info(google_cfg["service_account"])

    return sheets_id, credentials_info


def has_google_secrets_config(streamlit_secrets: Any) -> bool:
    """Проверяет, задан ли справочник через Google Secrets."""
    google_cfg = _read_google_section(streamlit_secrets)
    return bool(google_cfg.get("sheets_id") or google_cfg.get("service_account"))


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
            resolved_credentials_info = _normalize_service_account_info(
                google_cfg["service_account"]
            )

    if resolved_credentials_info:
        resolved_credentials_info = dict(resolved_credentials_info)

    if not resolved_credentials_path and resolved_credentials_info is None:
        if DEFAULT_CREDENTIALS_PATH.exists():
            resolved_credentials_path = str(DEFAULT_CREDENTIALS_PATH)

    if resolved_sheets_id is not None:
        resolved_sheets_id = str(resolved_sheets_id).strip()

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
