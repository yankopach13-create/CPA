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
LIST_CATEGORY = "Категория"
LIST_DETAIL = "Детализация"


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


def _read_excel(uploaded_file) -> dict[str, pd.DataFrame]:
    """Читает все листы Excel-файла."""
    content = uploaded_file.read()
    uploaded_file.seek(0)

    name = uploaded_file.name.lower()
    engine = "openpyxl" if name.endswith(".xlsx") else "xlrd"
    return pd.read_excel(BytesIO(content), sheet_name=None, engine=engine)


def _build_column_info(df: pd.DataFrame) -> pd.DataFrame:
    """Формирует сводку по столбцам основного листа."""
    rows = []
    for column in df.columns:
        series = df[column]
        rows.append(
            {
                "Столбец": column,
                "Тип": str(series.dtype),
                "Заполнено": int(series.notna().sum()),
                "Пусто": int(series.isna().sum()),
                "Уникальных": int(series.nunique(dropna=True)),
            }
        )
    return pd.DataFrame(rows)


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

    result: dict[str, int] = {}
    for _, row in return_df.iterrows():
        category = row[category_column]
        weeks = row[weeks_column]
        if pd.isna(category) or pd.isna(weeks):
            continue
        category_name = str(category).strip()
        if not category_name:
            continue
        result[category_name] = int(weeks)

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


def _normalize_cycles_df(cycles_df: pd.DataFrame) -> pd.DataFrame:
    """Приводит лист «Недели циклов» к столбцам week и cycle."""
    normalized = cycles_df.copy()
    column_map = {
        str(column).strip().lower(): column for column in normalized.columns
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
            "week": pd.to_numeric(normalized[week_column], errors="coerce"),
            "cycle": pd.to_numeric(normalized[cycle_column], errors="coerce"),
        }
    )
    return result.dropna(subset=["week", "cycle"]).astype({"week": int, "cycle": int})


def get_cycle_number(cycles_df: pd.DataFrame, week_number: int) -> int | None:
    """Возвращает номер цикла для указанной недели."""
    cycles = _normalize_cycles_df(cycles_df)
    matched = cycles[cycles["week"].eq(week_number)]
    if matched.empty:
        return None
    return int(matched.iloc[0]["cycle"])


def get_cycle_weeks(cycles_df: pd.DataFrame, week_number: int) -> list[int]:
    """Возвращает все недели цикла для выбранной недели."""
    cycles = _normalize_cycles_df(cycles_df)
    matched = cycles[cycles["week"].eq(week_number)]
    if matched.empty:
        return []

    cycle_number = int(matched.iloc[0]["cycle"])
    return cycles[cycles["cycle"].eq(cycle_number)]["week"].tolist()


def load_spravochnik() -> dict[str, Any]:
    """Загружает справочник из папки проекта."""
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

    return {
        "path": SPRAVOCHNIK_PATH,
        "display": display_df,
        "cycles": cycles_df,
        "return": return_df,
        "return_weeks": return_weeks,
        "volumes": volumes,
    }


def process_excel(uploaded_file) -> dict[str, Any]:
    """
    Обрабатывает загруженный Excel-файл.

    Возвращает словарь с предпросмотром, сводкой и данными по листам.
    """
    sheets = _read_excel(uploaded_file)

    if not sheets:
        raise ValueError("Файл не содержит данных.")

    main_sheet_name = next(iter(sheets))
    main_df = sheets[main_sheet_name].copy()

    numeric_cols = main_df.select_dtypes(include="number").columns
    numeric_summary = main_df[numeric_cols].describe() if len(numeric_cols) else None

    return {
        "main_sheet": main_sheet_name,
        "row_count": len(main_df),
        "column_count": len(main_df.columns),
        "preview": main_df.head(100),
        "column_info": _build_column_info(main_df),
        "numeric_summary": numeric_summary,
        "sheets": sheets,
        "data": main_df,
    }
