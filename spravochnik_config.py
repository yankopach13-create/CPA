"""Конфигурация источника справочника (Google Sheets / локальный Excel)."""

import os
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_CREDENTIALS_PATH = PROJECT_DIR / "google_credentials.json"


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

    if streamlit_secrets is not None:
        google_cfg = streamlit_secrets.get("google", {})
        if not resolved_sheets_id:
            resolved_sheets_id = google_cfg.get("sheets_id")
        if not resolved_credentials_path:
            resolved_credentials_path = google_cfg.get("credentials_path")
        if resolved_credentials_info is None and "service_account" in google_cfg:
            resolved_credentials_info = dict(google_cfg["service_account"])

    if not resolved_credentials_path and resolved_credentials_info is None:
        if DEFAULT_CREDENTIALS_PATH.exists():
            resolved_credentials_path = str(DEFAULT_CREDENTIALS_PATH)

    return {
        "sheets_id": resolved_sheets_id,
        "credentials_path": resolved_credentials_path,
        "credentials_info": resolved_credentials_info,
    }
