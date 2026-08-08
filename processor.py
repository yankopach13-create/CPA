"""Обработка Excel-файлов для анализа клиентов (категория ОЭС)."""

from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent
SPRAVOCHNIK_PATH = PROJECT_DIR / "spravochnik.xlsx"
SHEET_DISPLAY = "Категории и продукты"
SHEET_CYCLES = "Недели циклов"
SHEET_RETURN = "Возврат"
SHEET_EXCLUDED = "Исключённые"
LIST_CATEGORY = "Категория"
LIST_DETAIL = "Детализация"
NEW_CATEGORY_OPTION = "Добавить новую категорию"
CATEGORY_PLACEHOLDER = "— Выберите категорию —"


def _pick_sheet(sheet_names: list[str], preferred_name: str, fallback_index: int) -> str:
    """Возвращает имя листа по точному совпадению или запасному индексу."""
    if preferred_name in sheet_names:
        return preferred_name
    if 0 <= fallback_index < len(sheet_names):
        return sheet_names[fallback_index]
    raise ValueError(
        f"Лист «{preferred_name}» не найден. Доступные листы: {', '.join(sheet_names)}"
    )


def validate_file(uploaded_file) -> None:
    """Проверяет, что загружен файл допустимого формата."""
    if uploaded_file is None:
        raise ValueError("Файл не загружен.")

    name = uploaded_file.name.lower()
    if not name.endswith((".xlsx", ".xls")):
        raise ValueError("Поддерживаются только файлы .xlsx и .xls.")


def _read_main_excel_sheet(uploaded_file) -> tuple[str, pd.DataFrame]:
    """Читает первый (основной) лист Excel-файла с покупками."""
    content = uploaded_file.read()
    uploaded_file.seek(0)

    name = uploaded_file.name.lower()
    engine = "openpyxl" if name.endswith(".xlsx") else "xlrd"
    excel_file = pd.ExcelFile(BytesIO(content), engine=engine)
    if not excel_file.sheet_names:
        raise ValueError("Файл не содержит данных.")

    main_sheet_name = excel_file.sheet_names[0]
    main_df = pd.read_excel(excel_file, sheet_name=main_sheet_name)
    return main_sheet_name, main_df


def _parse_model_list(series: pd.Series) -> list[str]:
    """Извлекает непустой список моделей из столбца справочника."""
    models: list[str] = []
    for value in series:
        if pd.isna(value):
            continue
        model = str(value).strip()
        if model:
            models.append(model)
    return models


def parse_return_weeks(return_df: pd.DataFrame) -> dict[str, int]:
    """
    Парсит лист «Возврат».

    Возвращает словарь «категория / продукт» → количество недель возврата.
    """
    column_map = {str(column).strip().lower(): column for column in return_df.columns}

    category_column = None
    weeks_column = None
    for name, original in column_map.items():
        if "категор" in name:
            category_column = original
        if "возврат" in name and "недел" in name:
            weeks_column = original

    if category_column is None or weeks_column is None:
        raise ValueError(
            "Лист «Возврат» должен содержать столбцы «Категория» и «Возврат (недель)»."
        )

    categories = return_df[category_column].astype("string").str.strip()
    weeks = pd.to_numeric(return_df[weeks_column], errors="coerce")
    valid = categories.notna() & categories.ne("") & weeks.notna()
    return {
        str(category): int(week)
        for category, week in zip(
            categories[valid].tolist(),
            weeks[valid].tolist(),
            strict=True,
        )
    }


def parse_excluded_products(excluded_df: pd.DataFrame | None) -> list[str]:
    """
    Парсит лист «Исключённые».

    Ожидает столбец «Группа3» (или первый столбец). Возвращает список моделей.
    """
    if excluded_df is None or excluded_df.empty:
        return []

    column_map = {
        str(column).strip().lower(): column for column in excluded_df.columns
    }
    model_column = None
    for name, original in column_map.items():
        if "группа" in name and "3" in name:
            model_column = original
            break
    if model_column is None:
        model_column = excluded_df.columns[0]

    result: list[str] = []
    seen: set[str] = set()
    for value in excluded_df[model_column]:
        if pd.isna(value):
            continue
        model = str(value).strip()
        if not model or model.lower() == "nan" or model in seen:
            continue
        result.append(model)
        seen.add(model)
    return result


def get_return_weeks(
    return_weeks: dict[str, int],
    category_name: str,
    detail_name: str | None = None,
) -> int | None:
    """
    Возвращает период возврата в неделях для категории или детализации.

    Если для детализации нет отдельной строки — используется значение категории.
    """
    if detail_name:
        weeks = return_weeks.get(detail_name)
        if weeks is not None:
            return weeks
    return return_weeks.get(category_name)


def parse_display_volumes(display_df: pd.DataFrame) -> dict[str, dict[str, list[str]]]:
    """
    Парсит лист «Категории и продукты».

    Возвращает словарь категорий с моделями для категории и детализации.
    """
    if not isinstance(display_df.columns, pd.MultiIndex):
        raise ValueError(
            "Лист «Категории и продукты» должен иметь двухуровневый заголовок: "
            "объём ОЭС и тип списка (Категория / Детализация)."
        )

    volumes: dict[str, dict[str, list[str]]] = {}
    seen_volumes: set[str] = set()

    for volume, list_type in display_df.columns:
        volume_name = str(volume).strip()
        list_name = str(list_type).strip()

        if volume_name not in seen_volumes:
            volumes[volume_name] = {"category": [], "detail": []}
            seen_volumes.add(volume_name)

        if list_name == LIST_CATEGORY:
            volumes[volume_name]["category"] = _parse_model_list(display_df[(volume, list_type)])
        elif list_name == LIST_DETAIL:
            volumes[volume_name]["detail"] = _parse_model_list(display_df[(volume, list_type)])

    return volumes


def normalize_cycles_df(cycles_df: pd.DataFrame) -> pd.DataFrame:
    """Приводит лист «Недели циклов» к столбцам week и cycle."""
    if {"week", "cycle"}.issubset(cycles_df.columns):
        return cycles_df

    column_map = {
        str(column).strip().lower(): column for column in cycles_df.columns
    }

    week_column = None
    cycle_column = None
    for name, original in column_map.items():
        if "нед" in name:
            week_column = original
        if "цикл" in name:
            cycle_column = original

    if week_column is None or cycle_column is None:
        raise ValueError(
            "Лист «Недели циклов» должен содержать столбцы «Неделя» и «Цикл»."
        )

    result = pd.DataFrame(
        {
            "week": pd.to_numeric(cycles_df[week_column], errors="coerce"),
            "cycle": pd.to_numeric(cycles_df[cycle_column], errors="coerce"),
        }
    )
    return result.dropna(subset=["week", "cycle"]).astype({"week": int, "cycle": int})


def get_cycle_number(cycles_df: pd.DataFrame, week_number: int) -> int | None:
    """Возвращает номер цикла для указанной недели."""
    cycles = normalize_cycles_df(cycles_df)
    matched = cycles[cycles["week"].eq(week_number)]
    if matched.empty:
        return None
    return int(matched.iloc[0]["cycle"])


def get_cycle_weeks(cycles_df: pd.DataFrame, week_number: int) -> list[int]:
    """Возвращает все недели цикла для выбранной недели."""
    cycles = normalize_cycles_df(cycles_df)
    matched = cycles[cycles["week"].eq(week_number)]
    if matched.empty:
        return []

    cycle_number = int(matched.iloc[0]["cycle"])
    return cycles[cycles["cycle"].eq(cycle_number)]["week"].tolist()


def load_spravochnik_from_excel() -> dict[str, Any]:
    """Загружает справочник из локального файла spravochnik.xlsx."""
    if not SPRAVOCHNIK_PATH.exists():
        raise FileNotFoundError(
            f"Справочник не найден: {SPRAVOCHNIK_PATH.name}. "
            f"Положите файл в папку проекта."
        )

    excel_file = pd.ExcelFile(SPRAVOCHNIK_PATH)
    sheet_names = excel_file.sheet_names

    display_sheet = _pick_sheet(sheet_names, SHEET_DISPLAY, fallback_index=0)
    cycles_sheet = _pick_sheet(sheet_names, SHEET_CYCLES, fallback_index=2)
    return_sheet = _pick_sheet(sheet_names, SHEET_RETURN, fallback_index=1)

    display_df = pd.read_excel(
        excel_file,
        sheet_name=display_sheet,
        header=[0, 1],
    )
    cycles_df = pd.read_excel(excel_file, sheet_name=cycles_sheet)
    return_df = pd.read_excel(excel_file, sheet_name=return_sheet)
    volumes = parse_display_volumes(display_df)
    return_weeks = parse_return_weeks(return_df)
    cycles_normalized = normalize_cycles_df(cycles_df)

    return {
        "path": SPRAVOCHNIK_PATH,
        "display": display_df,
        "cycles": cycles_df,
        "cycles_normalized": cycles_normalized,
        "return": return_df,
        "return_weeks": return_weeks,
        "volumes": volumes,
        "excluded": [],
        "sheets_id": None,
        "writable": False,
    }


def load_spravochnik(
    sheets_id: str | None = None,
    credentials_path: str | None = None,
    credentials_info: dict[str, Any] | None = None,
    streamlit_secrets: Any | None = None,
    prefer_excel: bool = False,
) -> dict[str, Any]:
    """
    Загружает справочник из Google Sheets или локального Excel.

    Если задан GOOGLE_SHEETS_ID (или sheets_id), по умолчанию используется Google Sheets.
    При prefer_excel=True или отсутствии настроек Google — локальный spravochnik.xlsx.
    """
    from spravochnik_config import resolve_spravochnik_settings

    settings = resolve_spravochnik_settings(
        sheets_id=sheets_id,
        credentials_path=credentials_path,
        credentials_info=credentials_info,
        streamlit_secrets=streamlit_secrets,
    )

    if not prefer_excel and settings["sheets_id"]:
        from spravochnik_config import validate_spravochnik_settings
        from google_sheets import load_spravochnik_from_sheets

        validate_spravochnik_settings(settings)

        return load_spravochnik_from_sheets(
            sheets_id=settings["sheets_id"],
            credentials_path=settings["credentials_path"],
            credentials_info=settings["credentials_info"],
        )

    return load_spravochnik_from_excel()


def process_excel(uploaded_file) -> dict[str, Any]:
    """
    Обрабатывает загруженный Excel-файл с покупками.

    Читает только основной лист — без лишней статистики.
    """
    main_sheet_name, main_df = _read_main_excel_sheet(uploaded_file)

    return {
        "main_sheet": main_sheet_name,
        "row_count": len(main_df),
        "column_count": len(main_df.columns),
        "data": main_df,
    }
