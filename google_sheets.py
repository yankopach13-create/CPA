"""Загрузка справочника из Google Sheets."""

from typing import Any

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, SpreadsheetNotFound

from processor import (
    SHEET_CYCLES,
    SHEET_DISPLAY,
    SHEET_RETURN,
    _pick_sheet,
    parse_display_volumes,
    parse_return_weeks,
)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _authorize_gspread(
    credentials_path: str | None = None,
    credentials_info: dict[str, Any] | None = None,
) -> gspread.Client:
    """Авторизует клиент gspread через сервисный аккаунт."""
    try:
        if credentials_info is not None:
            creds = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
        elif credentials_path is not None:
            creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
        else:
            raise ValueError(
                "Не указаны учётные данные Google. "
                "Добавьте в Secrets секцию [google.service_account]."
            )
        return gspread.authorize(creds)
    except (ValueError, OSError) as exc:
        raise ValueError(f"Ошибка учётных данных Google: {exc}") from exc


def _worksheet_to_dataframe_multilevel(worksheet: gspread.Worksheet) -> pd.DataFrame:
    """Читает лист с двухуровневым заголовком (строки 1 и 2)."""
    raw = worksheet.get_all_values()
    if len(raw) < 2:
        raise ValueError(
            f"Лист «{worksheet.title}» должен содержать минимум две строки заголовка."
        )

    header_top = [str(cell).strip() for cell in raw[0]]
    header_bottom = [str(cell).strip() for cell in raw[1]]
    data_rows = raw[2:]

    # Выравниваем длину заголовков по числу столбцов данных
    if data_rows:
        col_count = max(len(row) for row in data_rows)
    else:
        col_count = max(len(header_top), len(header_bottom))

    header_top = (header_top + [""] * col_count)[:col_count]
    header_bottom = (header_bottom + [""] * col_count)[:col_count]

    columns = pd.MultiIndex.from_arrays([header_top, header_bottom])
    normalized_rows = [row + [""] * (col_count - len(row)) for row in data_rows]
    display_df = pd.DataFrame(normalized_rows, columns=columns)
    return display_df.replace("", pd.NA)


def _worksheet_to_dataframe(worksheet: gspread.Worksheet) -> pd.DataFrame:
    """Читает простой лист с одной строкой заголовка."""
    records = worksheet.get_all_records()
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def load_spravochnik_from_sheets(
    sheets_id: str,
    credentials_path: str | None = None,
    credentials_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Загружает справочник из Google Sheets.

    Ожидаются листы: «Категории и продукты», «Недели циклов», «Возврат».
    """
    if not sheets_id or not str(sheets_id).strip():
        raise ValueError("Не указан ID таблицы Google Sheets (GOOGLE_SHEETS_ID).")

    client = _authorize_gspread(credentials_path, credentials_info)
    service_email = None
    if credentials_info:
        service_email = credentials_info.get("client_email")

    try:
        spreadsheet = client.open_by_key(sheets_id.strip())
    except SpreadsheetNotFound:
        raise ValueError(
            f"Таблица Google Sheets не найдена. Проверьте sheets_id: {sheets_id}"
        ) from None
    except APIError as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code == 403:
            email_hint = service_email or "cpa-951@b2b-rnp.iam.gserviceaccount.com"
            raise PermissionError(
                f"Нет доступа к Google таблице (403). "
                f"1) В Google Cloud включите Google Sheets API для проекта b2b-rnp. "
                f"2) В Google Sheets откройте «Поделиться» и добавьте {email_hint} "
                f"с правом «Читатель» или «Редактор»."
            ) from exc
        raise ValueError(f"Ошибка Google Sheets API ({status_code}): {exc}") from exc
    except PermissionError as exc:
        if str(exc).strip():
            raise
        email_hint = service_email or "cpa-951@b2b-rnp.iam.gserviceaccount.com"
        raise PermissionError(
            f"Нет доступа к Google таблице. "
            f"Добавьте {email_hint} в доступ к таблице и включите Google Sheets API."
        ) from exc

    sheet_names = [worksheet.title for worksheet in spreadsheet.worksheets()]

    display_sheet = _pick_sheet(sheet_names, SHEET_DISPLAY, fallback_index=0)
    cycles_sheet = _pick_sheet(sheet_names, SHEET_CYCLES, fallback_index=2)
    return_sheet = _pick_sheet(sheet_names, SHEET_RETURN, fallback_index=1)

    display_df = _worksheet_to_dataframe_multilevel(spreadsheet.worksheet(display_sheet))
    cycles_df = _worksheet_to_dataframe(spreadsheet.worksheet(cycles_sheet))
    return_df = _worksheet_to_dataframe(spreadsheet.worksheet(return_sheet))

    volumes = parse_display_volumes(display_df)
    return_weeks = parse_return_weeks(return_df)

    return {
        "path": f"google-sheets:{sheets_id}",
        "display": display_df,
        "cycles": cycles_df,
        "return": return_df,
        "return_weeks": return_weeks,
        "volumes": volumes,
    }
