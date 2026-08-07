"""Подготовка данных о покупках клиентов."""

import re
from typing import Any

import pandas as pd

GROUP_LEVEL_PATTERN = re.compile(
    r"^группа\s*(?:ур\.?\s*)?(\d+)\s*$",
    re.IGNORECASE,
)
YEAR_WEEK_PATTERN = re.compile(r"год\s*[-\s]?\s*нед", re.IGNORECASE)
WEEK_PATTERN = re.compile(r"^неделя$", re.IGNORECASE)
QUANTITY_PATTERN = re.compile(r"количество", re.IGNORECASE)
CLIENT_CODE_PATTERN = re.compile(r"код\s*клиента", re.IGNORECASE)


def _normalize_column_name(name: Any) -> str:
    return str(name).strip().lower()


def _find_column(columns: list[Any], pattern: re.Pattern[str]) -> str:
    for column in columns:
        if pattern.search(_normalize_column_name(column)):
            return column
    raise ValueError(f"Не найден столбец по шаблону: {pattern.pattern}")


def _find_group_level_column(columns: list[Any], level: int) -> str | None:
    """Ищет столбец «ГруппаN» / «Группа ур.N». Возвращает None, если не найден."""
    for column in columns:
        match = GROUP_LEVEL_PATTERN.match(_normalize_column_name(column))
        if match and int(match.group(1)) == level:
            return column
    return None


def _find_group_column(columns: list[Any]) -> str:
    """Ищет столбец уровня 3 (Группа3 / Группа ур.3) для фильтрации продуктов."""
    column = _find_group_level_column(columns, 3)
    if column is None:
        raise ValueError("Не найден столбец «Группа3» (уровень 3).")
    return column


def _clean_group_label(value: Any) -> str:
    """Нормализует значение группы: пустые и nan → пустая строка."""
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none"}:
        return ""
    return text


def _has_client_code(value: Any) -> bool:
    if pd.isna(value):
        return False
    code = str(value).strip()
    return code != "" and code.lower() != "nan"


def _parse_week_number(week_part: str) -> int:
    """Преобразует номер недели, включая вариант «53+1»."""
    normalized = week_part.strip().replace(" ", "")
    if normalized in {"53+1", "53+1.0"}:
        return 54
    return int(float(normalized))


def _parse_year_week(value: Any) -> tuple[int, int] | None:
    if pd.isna(value):
        return None

    text = str(value).strip().replace("\\", "/")
    if "/" in text:
        year_part, week_part = text.split("/", 1)
        return int(float(year_part)), _parse_week_number(week_part)

    normalized = text.replace(" ", "")
    if normalized in {"53+1", "53+1.0"}:
        return None

    if text.isdigit():
        return None

    try:
        week = int(float(text))
    except ValueError:
        return None
    return None


def _parse_week_column_value(value: Any) -> int | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    normalized = text.replace(" ", "")
    if normalized in {"53+1", "53+1.0"}:
        return 54
    try:
        return int(float(text))
    except ValueError:
        return None


def prepare_purchases(df: pd.DataFrame) -> pd.DataFrame:
    """Приводит загруженные покупки к рабочему формату для расчёта метрик."""
    if df.empty:
        raise ValueError("Файл с покупками не содержит строк.")

    work_df = df.copy()
    columns = list(work_df.columns)

    group_col = _find_group_column(columns)
    group1_col = _find_group_level_column(columns, 1)
    quantity_col = _find_column(columns, QUANTITY_PATTERN)
    client_col = _find_column(columns, CLIENT_CODE_PATTERN)

    year_week_col = None
    week_col = None
    for column in columns:
        name = _normalize_column_name(column)
        if YEAR_WEEK_PATTERN.search(name):
            year_week_col = column
        elif WEEK_PATTERN.match(name):
            week_col = column

    if year_week_col is None and week_col is None:
        raise ValueError("Не найден столбец «Год-Неделя» или «Неделя».")

    first_col = work_df.columns[0]
    work_df = work_df[~work_df[first_col].astype(str).str.strip().str.lower().eq("итоги")]

    group1_values = (
        work_df[group1_col].map(_clean_group_label)
        if group1_col is not None
        else pd.Series([""] * len(work_df), index=work_df.index)
    )

    prepared = pd.DataFrame(
        {
            "model": work_df[group_col].map(_clean_group_label),
            "group1": group1_values,
            "quantity": pd.to_numeric(work_df[quantity_col], errors="coerce").fillna(0),
            "client_code": work_df[client_col],
            "has_bc": work_df[client_col].map(_has_client_code),
        }
    )

    parsed_weeks = (
        work_df[year_week_col].map(_parse_year_week)
        if year_week_col is not None
        else pd.Series([None] * len(work_df))
    )
    prepared["year"] = parsed_weeks.map(lambda item: item[0] if item else pd.NA)
    prepared["week"] = parsed_weeks.map(lambda item: item[1] if item else pd.NA)

    if prepared["week"].isna().any() and week_col is not None:
        fallback_weeks = work_df[week_col].map(_parse_week_column_value)
        prepared["week"] = prepared["week"].fillna(fallback_weeks)

    if prepared["year"].isna().any():
        known_year = prepared["year"].dropna()
        fallback_year = known_year.iloc[0] if not known_year.empty else None
        if fallback_year is not None:
            prepared["year"] = prepared["year"].fillna(fallback_year)

    prepared = prepared.dropna(subset=["year"])
    prepared = prepared.dropna(subset=["week"])
    prepared["week"] = prepared["week"].astype(int)
    prepared["year"] = prepared["year"].astype(int)
    prepared["year_week"] = list(zip(prepared["year"], prepared["week"], strict=True))

    prepared = prepared[prepared["model"].ne("") & prepared["model"].str.lower().ne("nan")]
    prepared = prepared.reset_index(drop=True)

    if prepared.empty:
        raise ValueError("После обработки не осталось строк с покупками.")

    return prepared


def filter_by_models(purchases: pd.DataFrame, models: list[str]) -> pd.DataFrame:
    """Фильтрует покупки по списку моделей из справочника."""
    if not models:
        return purchases.iloc[0:0].copy()
    model_set = {model.strip() for model in models}
    return purchases[purchases["model"].isin(model_set)].copy()


def collect_known_models(
    volumes: dict[str, dict[str, list[str]]],
    excluded: list[str] | set[str] | None = None,
) -> set[str]:
    """Собирает все известные модели: категории, детализация и исключённые."""
    known: set[str] = set()
    for config in volumes.values():
        for model in config.get("category", []):
            cleaned = str(model).strip()
            if cleaned:
                known.add(cleaned)
        for model in config.get("detail", []):
            cleaned = str(model).strip()
            if cleaned:
                known.add(cleaned)
    if excluded:
        for model in excluded:
            cleaned = str(model).strip()
            if cleaned:
                known.add(cleaned)
    return known


def format_product_display_name(model: str, group1: str = "") -> str:
    """Формирует подпись продукта для UI: «Группа1 / Группа3»."""
    model_name = str(model).strip()
    group1_name = str(group1).strip() if group1 else ""
    if group1_name:
        return f"{group1_name} / {model_name}"
    return model_name


def find_unknown_products(
    purchases_df: pd.DataFrame,
    volumes: dict[str, dict[str, list[str]]],
    excluded: list[str] | set[str] | None = None,
) -> list[dict[str, str]]:
    """
    Находит продукты из файла, которых нет в справочнике и в исключённых.

    Возвращает список словарей: model (Группа3), group1, display_name.
    """
    purchases = (
        purchases_df
        if "model" in purchases_df.columns
        else prepare_purchases(purchases_df)
    )
    known = collect_known_models(volumes, excluded)
    unknown: list[dict[str, str]] = []
    seen: set[str] = set()

    for _, row in purchases.iterrows():
        model = str(row["model"]).strip()
        if not model or model in known or model in seen:
            continue
        group1 = ""
        if "group1" in purchases.columns:
            group1 = _clean_group_label(row["group1"])
        unknown.append(
            {
                "model": model,
                "group1": group1,
                "display_name": format_product_display_name(model, group1),
            }
        )
        seen.add(model)

    return unknown
