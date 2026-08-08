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


def _clean_group_series(series: pd.Series) -> pd.Series:
    """Векторизованная нормализация значений группы."""
    text = series.astype("string").str.strip()
    empty_mask = text.isna() | text.str.lower().isin({"", "nan", "none", "<na>"})
    return text.mask(empty_mask, "").fillna("")


def _has_client_code_series(series: pd.Series) -> pd.Series:
    """Векторизованная проверка наличия кода клиента (БК)."""
    text = series.astype("string").str.strip()
    return ~(text.isna() | text.eq("") | text.str.lower().isin({"nan", "<na>"}))


def _parse_week_number_series(week_part: pd.Series) -> pd.Series:
    """Преобразует номера недель, включая вариант «53+1»."""
    normalized = week_part.astype("string").str.strip().str.replace(" ", "", regex=False)
    result = pd.Series(pd.NA, index=week_part.index, dtype="Float64")
    special = normalized.isin({"53+1", "53+1.0"})
    result = result.mask(special, 54)
    numeric = pd.to_numeric(normalized.mask(special), errors="coerce")
    return result.fillna(numeric)


def _parse_year_week_series(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Парсит столбец «Год-Неделя» в пару серий year / week."""
    text = series.astype("string").str.strip().str.replace("\\", "/", regex=False)
    has_slash = text.str.contains("/", na=False)

    year = pd.Series(pd.NA, index=series.index, dtype="Float64")
    week = pd.Series(pd.NA, index=series.index, dtype="Float64")

    if has_slash.any():
        parts = text.loc[has_slash].str.split("/", n=1, expand=True)
        year.loc[has_slash] = pd.to_numeric(parts[0], errors="coerce")
        week.loc[has_slash] = _parse_week_number_series(parts[1])

    return year, week


def _parse_week_column_series(series: pd.Series) -> pd.Series:
    """Парсит отдельный столбец «Неделя»."""
    text = series.astype("string").str.strip()
    normalized = text.str.replace(" ", "", regex=False)
    result = pd.Series(pd.NA, index=series.index, dtype="Float64")
    special = normalized.isin({"53+1", "53+1.0"})
    result = result.mask(special, 54)
    numeric = pd.to_numeric(normalized.mask(special), errors="coerce")
    return result.fillna(numeric)


def prepare_purchases(df: pd.DataFrame) -> pd.DataFrame:
    """Приводит загруженные покупки к рабочему формату для расчёта метрик."""
    if df.empty:
        raise ValueError("Файл с покупками не содержит строк.")

    # Уже подготовленный кадр — не парсим повторно.
    if {"model", "quantity", "client_code", "has_bc", "year", "week"}.issubset(df.columns):
        return df

    columns = list(df.columns)
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

    first_col = df.columns[0]
    totals_mask = df[first_col].astype("string").str.strip().str.lower().eq("итоги")
    work_df = df.loc[~totals_mask]

    group1_values = (
        _clean_group_series(work_df[group1_col])
        if group1_col is not None
        else pd.Series("", index=work_df.index, dtype="string")
    )

    prepared = pd.DataFrame(
        {
            "model": _clean_group_series(work_df[group_col]),
            "group1": group1_values,
            "quantity": pd.to_numeric(work_df[quantity_col], errors="coerce").fillna(0),
            "client_code": work_df[client_col],
            "has_bc": _has_client_code_series(work_df[client_col]),
        },
        index=work_df.index,
    )

    if year_week_col is not None:
        year_values, week_values = _parse_year_week_series(work_df[year_week_col])
        prepared["year"] = year_values
        prepared["week"] = week_values
    else:
        prepared["year"] = pd.Series(pd.NA, index=work_df.index, dtype="Float64")
        prepared["week"] = pd.Series(pd.NA, index=work_df.index, dtype="Float64")

    if prepared["week"].isna().any() and week_col is not None:
        fallback_weeks = _parse_week_column_series(work_df[week_col])
        prepared["week"] = prepared["week"].fillna(fallback_weeks)

    if prepared["year"].isna().any():
        known_year = prepared["year"].dropna()
        if not known_year.empty:
            prepared["year"] = prepared["year"].fillna(known_year.iloc[0])

    prepared = prepared.dropna(subset=["year", "week"])
    prepared["week"] = prepared["week"].astype(int)
    prepared["year"] = prepared["year"].astype(int)

    model_ok = prepared["model"].ne("") & prepared["model"].str.lower().ne("nan")
    prepared = prepared.loc[model_ok].reset_index(drop=True)

    if prepared.empty:
        raise ValueError("После обработки не осталось строк с покупками.")

    return prepared


def filter_by_models(purchases: pd.DataFrame, models: list[str]) -> pd.DataFrame:
    """Фильтрует покупки по списку моделей из справочника."""
    if not models:
        return purchases.iloc[0:0]
    model_set = {model.strip() for model in models}
    return purchases[purchases["model"].isin(model_set)]


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

    unique = purchases.loc[:, ["model"]].copy()
    if "group1" in purchases.columns:
        unique["group1"] = _clean_group_series(purchases["group1"])
    else:
        unique["group1"] = ""

    unique["model"] = unique["model"].astype(str).str.strip()
    unique = unique[unique["model"].ne("") & ~unique["model"].isin(known)]
    unique = unique.drop_duplicates(subset=["model"], keep="first")

    return [
        {
            "model": row.model,
            "group1": row.group1,
            "display_name": format_product_display_name(row.model, row.group1),
        }
        for row in unique.itertuples(index=False)
    ]
