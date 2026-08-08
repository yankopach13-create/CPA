"""Загрузка и обновление справочника в Google Sheets."""

from datetime import date
from typing import Any

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound

from processor import (
    LIST_CATEGORY,
    LIST_DETAIL,
    SHEET_CYCLES,
    SHEET_DISPLAY,
    SHEET_EXCLUDED,
    SHEET_RETURN,
    _pick_sheet,
    normalize_cycles_df,
    parse_display_volumes,
    parse_excluded_products,
    parse_return_weeks,
)

# Полный доступ к таблицам нужен для добавления продуктов и категорий.
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


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


def _service_email_hint(credentials_info: dict[str, Any] | None) -> str:
    if credentials_info and credentials_info.get("client_email"):
        return str(credentials_info["client_email"])
    return "cpa-951@b2b-rnp.iam.gserviceaccount.com"


def _open_spreadsheet(
    sheets_id: str,
    credentials_path: str | None = None,
    credentials_info: dict[str, Any] | None = None,
) -> gspread.Spreadsheet:
    """Открывает Google-таблицу справочника с понятными ошибками доступа."""
    if not sheets_id or not str(sheets_id).strip():
        raise ValueError("Не указан ID таблицы Google Sheets (GOOGLE_SHEETS_ID).")

    client = _authorize_gspread(credentials_path, credentials_info)
    email_hint = _service_email_hint(credentials_info)

    try:
        return client.open_by_key(sheets_id.strip())
    except SpreadsheetNotFound:
        raise ValueError(
            f"Таблица Google Sheets не найдена. Проверьте sheets_id: {sheets_id}"
        ) from None
    except APIError as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code == 403:
            raise PermissionError(
                f"Нет доступа к Google таблице (403). "
                f"1) В Google Cloud включите Google Sheets API и Google Drive API. "
                f"2) В Google Sheets добавьте {email_hint} с правом «Редактор» "
                f"(нужно для добавления продуктов)."
            ) from exc
        raise ValueError(f"Ошибка Google Sheets API ({status_code}): {exc}") from exc
    except PermissionError as exc:
        if str(exc).strip():
            raise
        raise PermissionError(
            f"Нет доступа к Google таблице. "
            f"Добавьте {email_hint} как «Редактор», "
            f"включите Google Sheets API и Google Drive API."
        ) from exc


def _col_index_to_a1(index_0based: int) -> str:
    """Преобразует 0-based индекс столбца в букву A1 (A, B, …, AA)."""
    if index_0based < 0:
        raise ValueError("Индекс столбца не может быть отрицательным.")
    result = ""
    n = index_0based
    while True:
        result = chr(n % 26 + ord("A")) + result
        n = n // 26 - 1
        if n < 0:
            break
    return result


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


def _find_category_columns(
    header_top: list[str],
    header_bottom: list[str],
    category_name: str,
) -> tuple[int, int | None]:
    """
    Находит индексы столбцов «Категория» и «Детализация» для объёма.

    Возвращает (index_category, index_detail_or_None).
    """
    target = category_name.strip()
    category_idx: int | None = None
    detail_idx: int | None = None

    for index, (top, bottom) in enumerate(zip(header_top, header_bottom, strict=False)):
        if str(top).strip() != target:
            continue
        bottom_name = str(bottom).strip()
        if bottom_name == LIST_CATEGORY:
            category_idx = index
        elif bottom_name == LIST_DETAIL:
            detail_idx = index

    if category_idx is None:
        raise ValueError(f"Категория «{category_name}» не найдена на листе «{SHEET_DISPLAY}».")
    return category_idx, detail_idx


def _first_empty_row(column_values: list[str], start_row_1based: int = 3) -> int:
    """Возвращает 1-based номер первой пустой строки в столбце данных."""
    data_start = start_row_1based - 1  # 0-based в массиве raw
    for offset, value in enumerate(column_values[data_start:]):
        if str(value).strip() == "":
            return start_row_1based + offset
    return max(start_row_1based, len(column_values) + 1)


def _append_value_to_column(
    worksheet: gspread.Worksheet,
    raw: list[list[str]],
    col_index: int,
    value: str,
) -> list[dict[str, Any]] | None:
    """
    Готовит batch-update для записи value в первую пустую ячейку столбца.

    Возвращает список запросов для batch_update или None, если значение уже есть.
    """
    col_letter = _col_index_to_a1(col_index)
    column_values = [row[col_index] if col_index < len(row) else "" for row in raw]
    existing = {str(cell).strip() for cell in column_values[2:] if str(cell).strip()}
    if value in existing:
        return None
    row_number = _first_empty_row(column_values, start_row_1based=3)
    # Помечаем ячейку в raw, чтобы следующий вызов видел занятость.
    while len(raw) < row_number:
        raw.append([])
    row = raw[row_number - 1]
    while len(row) <= col_index:
        row.append("")
    row[col_index] = value
    return [{"range": f"{col_letter}{row_number}", "values": [[value]]}]


def _batch_update_cells(
    worksheet: gspread.Worksheet,
    updates: list[dict[str, Any]],
) -> None:
    """Отправляет несколько обновлений ячеек одним запросом."""
    if not updates:
        return
    worksheet.batch_update(updates, value_input_option="USER_ENTERED")


def _get_or_create_excluded_worksheet(spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
    """Возвращает лист «Исключённые», при отсутствии создаёт с заголовком."""
    try:
        return spreadsheet.worksheet(SHEET_EXCLUDED)
    except WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=SHEET_EXCLUDED, rows=1000, cols=3)
        worksheet.update([["Группа3", "Дата", "Комментарий"]], "A1:C1")
        return worksheet


def _find_return_columns(return_ws: gspread.Worksheet) -> tuple[str, str, int]:
    """
    Находит буквы столбцов категории и недель возврата.

    Возвращает (letter_category, letter_weeks, next_empty_row_1based).
    """
    raw = return_ws.get_all_values()
    if not raw:
        raise ValueError(
            f"Лист «{SHEET_RETURN}» пуст. Нужны заголовки «Категория» и «Возврат (недель)»."
        )

    header = [str(cell).strip().lower() for cell in raw[0]]
    category_idx = None
    weeks_idx = None
    for index, name in enumerate(header):
        if "категор" in name:
            category_idx = index
        if "возврат" in name and "недел" in name:
            weeks_idx = index

    if category_idx is None or weeks_idx is None:
        raise ValueError(
            f"Лист «{SHEET_RETURN}» должен содержать столбцы «Категория» и «Возврат (недель)»."
        )

    next_row = len(raw) + 1
    for row_index, row in enumerate(raw[1:], start=2):
        cell = row[category_idx] if category_idx < len(row) else ""
        if str(cell).strip() == "":
            next_row = row_index
            break

    return (
        _col_index_to_a1(category_idx),
        _col_index_to_a1(weeks_idx),
        next_row,
    )


def add_product_to_category(
    sheets_id: str,
    category_name: str,
    product_model: str,
    add_to_detail: bool = False,
    credentials_path: str | None = None,
    credentials_info: dict[str, Any] | None = None,
) -> None:
    """Добавляет Группа3 в существующую категорию (и опционально в детализацию)."""
    model = product_model.strip()
    if not model:
        raise ValueError("Пустое имя продукта.")

    spreadsheet = _open_spreadsheet(sheets_id, credentials_path, credentials_info)
    worksheet = spreadsheet.worksheet(SHEET_DISPLAY)
    raw = worksheet.get_all_values()
    if len(raw) < 2:
        raise ValueError(f"Лист «{SHEET_DISPLAY}» должен иметь двухуровневый заголовок.")

    header_top = [str(cell).strip() for cell in raw[0]]
    header_bottom = [str(cell).strip() for cell in raw[1]]
    category_idx, detail_idx = _find_category_columns(
        header_top, header_bottom, category_name
    )

    updates: list[dict[str, Any]] = []
    category_update = _append_value_to_column(worksheet, raw, category_idx, model)
    if category_update:
        updates.extend(category_update)
    if add_to_detail:
        if detail_idx is None:
            raise ValueError(
                f"У категории «{category_name}» нет столбца «Детализация»."
            )
        detail_update = _append_value_to_column(worksheet, raw, detail_idx, model)
        if detail_update:
            updates.extend(detail_update)
    _batch_update_cells(worksheet, updates)


def create_category_with_product(
    sheets_id: str,
    category_name: str,
    product_model: str,
    return_weeks: int,
    add_to_detail: bool = False,
    credentials_path: str | None = None,
    credentials_info: dict[str, Any] | None = None,
) -> None:
    """
    Создаёт новую категорию: два столбца на листе продуктов + строка на «Возврат».
    """
    name = category_name.strip()
    model = product_model.strip()
    if not name:
        raise ValueError("Пустое название категории.")
    if not model:
        raise ValueError("Пустое имя продукта.")
    if return_weeks < 1:
        raise ValueError("Возврат (недель) должен быть ≥ 1.")

    spreadsheet = _open_spreadsheet(sheets_id, credentials_path, credentials_info)
    display_ws = spreadsheet.worksheet(SHEET_DISPLAY)
    raw = display_ws.get_all_values()
    if len(raw) < 2:
        raise ValueError(f"Лист «{SHEET_DISPLAY}» должен иметь двухуровневый заголовок.")

    header_top = [str(cell).strip() for cell in raw[0]]
    existing_names = {cell for cell in header_top if cell}
    if name in existing_names:
        raise ValueError(f"Категория «{name}» уже существует.")

    col_count = max(len(row) for row in raw) if raw else 0
    cat_idx = col_count
    detail_idx = col_count + 1
    cat_letter = _col_index_to_a1(cat_idx)
    detail_letter = _col_index_to_a1(detail_idx)

    display_ws.update(
        [
            [name, name],
            [LIST_CATEGORY, LIST_DETAIL],
            [model, model if add_to_detail else ""],
        ],
        f"{cat_letter}1:{detail_letter}3",
    )

    return_ws = spreadsheet.worksheet(SHEET_RETURN)
    cat_col, weeks_col, next_row = _find_return_columns(return_ws)
    return_ws.batch_update(
        [
            {"range": f"{cat_col}{next_row}", "values": [[name]]},
            {"range": f"{weeks_col}{next_row}", "values": [[return_weeks]]},
        ],
        value_input_option="USER_ENTERED",
    )


def add_excluded_product(
    sheets_id: str,
    product_model: str,
    credentials_path: str | None = None,
    credentials_info: dict[str, Any] | None = None,
) -> None:
    """Добавляет продукт на лист «Исключённые» (не учитывать в категориях)."""
    model = product_model.strip()
    if not model:
        raise ValueError("Пустое имя продукта.")

    spreadsheet = _open_spreadsheet(sheets_id, credentials_path, credentials_info)
    worksheet = _get_or_create_excluded_worksheet(spreadsheet)
    raw = worksheet.get_all_values()
    if not raw:
        worksheet.update([["Группа3", "Дата", "Комментарий"]], "A1:C1")
        raw = worksheet.get_all_values()

    header = [str(cell).strip().lower() for cell in raw[0]]
    model_idx = 0
    for index, name in enumerate(header):
        if "группа" in name and "3" in name:
            model_idx = index
            break

    existing = {
        str(row[model_idx]).strip()
        for row in raw[1:]
        if model_idx < len(row) and str(row[model_idx]).strip()
    }
    if model in existing:
        return

    next_row = len(raw) + 1
    model_letter = _col_index_to_a1(model_idx)
    updates: list[dict[str, Any]] = [
        {"range": f"{model_letter}{next_row}", "values": [[model]]},
    ]
    if len(header) > 1:
        updates.append(
            {
                "range": f"{_col_index_to_a1(1)}{next_row}",
                "values": [[date.today().isoformat()]],
            }
        )
    if len(header) > 2:
        updates.append(
            {
                "range": f"{_col_index_to_a1(2)}{next_row}",
                "values": [["исключён пользователем"]],
            }
        )
    _batch_update_cells(worksheet, updates)


def load_spravochnik_from_sheets(
    sheets_id: str,
    credentials_path: str | None = None,
    credentials_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Загружает справочник из Google Sheets.

    Ожидаются листы: «Категории и продукты», «Недели циклов», «Возврат».
    Лист «Исключённые» опционален.
    """
    spreadsheet = _open_spreadsheet(sheets_id, credentials_path, credentials_info)
    sheet_names = [worksheet.title for worksheet in spreadsheet.worksheets()]

    display_sheet = _pick_sheet(sheet_names, SHEET_DISPLAY, fallback_index=0)
    cycles_sheet = _pick_sheet(sheet_names, SHEET_CYCLES, fallback_index=2)
    return_sheet = _pick_sheet(sheet_names, SHEET_RETURN, fallback_index=1)

    display_df = _worksheet_to_dataframe_multilevel(spreadsheet.worksheet(display_sheet))
    cycles_df = _worksheet_to_dataframe(spreadsheet.worksheet(cycles_sheet))
    return_df = _worksheet_to_dataframe(spreadsheet.worksheet(return_sheet))

    excluded_df = None
    if SHEET_EXCLUDED in sheet_names:
        excluded_df = _worksheet_to_dataframe(spreadsheet.worksheet(SHEET_EXCLUDED))

    volumes = parse_display_volumes(display_df)
    return_weeks = parse_return_weeks(return_df)
    excluded = parse_excluded_products(excluded_df)
    cycles_normalized = normalize_cycles_df(cycles_df)

    return {
        "path": f"google-sheets:{sheets_id}",
        "display": display_df,
        "cycles": cycles_df,
        "cycles_normalized": cycles_normalized,
        "return": return_df,
        "return_weeks": return_weeks,
        "volumes": volumes,
        "excluded": excluded,
        "sheets_id": sheets_id.strip(),
        "writable": True,
        "credentials_path": credentials_path,
        "credentials_info": credentials_info,
    }
