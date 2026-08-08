"""Расчёт метрик по покупкам клиентов."""

from typing import Any

import pandas as pd

from processor import get_cycle_weeks, get_return_weeks, normalize_cycles_df
from purchases import filter_by_models, prepare_purchases

WEEK_53_PLUS_1 = 54

CURRENT_WEEK_METRIC_KEYS = (
    "Продажи итого:",
    "Продажи с БК",
    "Продажи без БК",
    "Уник.клиентов с БК (накоп.)",
    "Возврат %",
    "Среднее в шт. на клиента с БК",
    "Повторные клиенты",
)

WEEK_SELECTOR_OPTIONS = [str(week) for week in range(1, 54)] + ["53+1"]


def format_week_label(week_number: int) -> str:
    """Форматирует номер недели для отображения."""
    if week_number == WEEK_53_PLUS_1:
        return "53+1"
    return str(week_number)


def format_cycle_message(cycle_number: int | None) -> str:
    """Формирует текст о цикле для расчёта накопительных показателей."""
    if cycle_number is None:
        return "Цикл для расчёта накопительных показателей не определён"
    return f"Определён {cycle_number} цикл для расчёта накопительных показателей"


def detect_actual_week(purchases_df: pd.DataFrame) -> tuple[int, int, int]:
    """
    Определяет актуальную неделю как последнюю по хронологии в файле.

    Возвращает (год, номер недели, внутренний номер недели для расчётов).
    """
    purchases = prepare_purchases(purchases_df)
    weeks = _sorted_weeks(purchases)
    if not weeks:
        raise ValueError("В файле не найдены данные по неделям.")

    year, week = weeks[-1]
    return year, week, week


def get_reporting_year_week(
    purchases_df: pd.DataFrame,
    week_number: int,
) -> tuple[int, int] | None:
    """Возвращает (год, неделя) для отчётной недели по данным файла."""
    purchases = prepare_purchases(purchases_df)
    return _resolve_actual_year_week(purchases, week_number)


def parse_selected_week(selected_week: str) -> int:
    """Преобразует выбранную неделю из интерфейса во внутренний номер."""
    if selected_week == "53+1":
        return WEEK_53_PLUS_1
    return int(selected_week)


def _empty_metrics() -> dict[str, float | int | None]:
    return {metric: None for metric in CURRENT_WEEK_METRIC_KEYS}


def _sorted_weeks(purchases: pd.DataFrame) -> list[tuple[int, int]]:
    unique_weeks = purchases[["year", "week"]].drop_duplicates()
    sorted_weeks = unique_weeks.sort_values(["year", "week"])
    return [tuple(row) for row in sorted_weeks.to_numpy()]


def _resolve_actual_year_week(
    purchases: pd.DataFrame,
    actual_week: int,
) -> tuple[int, int] | None:
    """Находит актуальную (год, неделя) по выбранному номеру недели."""
    matching = purchases[purchases["week"].eq(actual_week)]
    if matching.empty:
        return None

    weeks = _sorted_weeks(matching)
    return weeks[-1]


def _week_slice(purchases: pd.DataFrame, year_week: tuple[int, int]) -> pd.DataFrame:
    year, week = year_week
    return purchases[(purchases["year"].eq(year)) & (purchases["week"].eq(week))]


def _filter_weeks(purchases: pd.DataFrame, weeks: list[tuple[int, int]]) -> pd.DataFrame:
    if not weeks:
        return purchases.iloc[0:0]
    week_index = pd.MultiIndex.from_tuples(weeks, names=["year", "week"])
    keys = pd.MultiIndex.from_frame(purchases[["year", "week"]])
    return purchases[keys.isin(week_index)]


def _client_codes(frame: pd.DataFrame) -> set[str]:
    if frame.empty:
        return set()
    codes = frame.loc[frame["has_bc"], "client_code"].astype("string").str.strip()
    codes = codes[codes.ne("") & codes.notna()]
    return set(codes.unique())


def calculate_current_week_metrics(
    purchases: pd.DataFrame,
    actual_week: int,
    return_weeks: int | None = None,
    *,
    all_weeks: list[tuple[int, int]] | None = None,
    current_year_week: tuple[int, int] | None = None,
) -> dict[str, float | int | None]:
    """Считает метрики за выбранную актуальную неделю."""
    metrics = _empty_metrics()
    if purchases.empty:
        return metrics

    weeks = all_weeks if all_weeks is not None else _sorted_weeks(purchases)
    if not weeks:
        return metrics

    resolved_week = (
        current_year_week
        if current_year_week is not None
        else _resolve_actual_year_week(purchases, actual_week)
    )
    if resolved_week is None:
        return metrics

    lookback_weeks = max(0, return_weeks - 1) if return_weeks else 0
    try:
        week_index = weeks.index(resolved_week)
    except ValueError:
        return metrics
    prior_weeks = weeks[max(0, week_index - lookback_weeks) : week_index]

    current = _week_slice(purchases, resolved_week)
    prior = _filter_weeks(purchases, prior_weeks)

    total_qty = float(current["quantity"].sum())
    with_bc = current[current["has_bc"]]
    without_bc = current[~current["has_bc"]]

    current_clients = _client_codes(current)
    prior_clients = _client_codes(prior)
    returned_clients = current_clients & prior_clients

    metrics["Продажи итого:"] = total_qty
    metrics["Продажи с БК"] = float(with_bc["quantity"].sum())
    metrics["Продажи без БК"] = float(without_bc["quantity"].sum())
    metrics["Уник.клиентов с БК (накоп.)"] = len(current_clients)
    metrics["Повторные клиенты"] = len(returned_clients)
    metrics["Среднее в шт. на клиента с БК"] = (
        float(with_bc["quantity"].sum()) / len(current_clients)
        if current_clients
        else None
    )
    metrics["Возврат %"] = (
        len(returned_clients) / len(current_clients) * 100
        if current_clients
        else None
    )

    return metrics


def calculate_cycle_metrics(
    purchases: pd.DataFrame,
    cycle_weeks: list[int],
) -> dict[str, float | int | None]:
    """Считает накопительные метрики за все недели выбранного цикла."""
    metrics = _empty_metrics()
    if purchases.empty or not cycle_weeks:
        return metrics

    cycle_data = purchases[purchases["week"].isin(cycle_weeks)]
    if cycle_data.empty:
        return metrics

    metrics["Уник.клиентов с БК (накоп.)"] = len(_client_codes(cycle_data))
    return metrics


def calculate_volume_metrics(
    purchases: pd.DataFrame,
    volume_config: dict[str, list[str]],
    actual_week: int,
    cycles_df: pd.DataFrame,
    category_name: str,
    return_weeks_map: dict[str, int],
    *,
    cycle_weeks: list[int] | None = None,
) -> dict[str, Any]:
    """Считает метрики по категории и по моделям детализации."""
    category_models = volume_config.get("category", [])
    detail_models = volume_config.get("detail", [])
    resolved_cycle_weeks = (
        cycle_weeks if cycle_weeks is not None else get_cycle_weeks(cycles_df, actual_week)
    )
    category_return_weeks = get_return_weeks(return_weeks_map, category_name)

    category_purchases = filter_by_models(purchases, category_models)
    all_weeks = _sorted_weeks(category_purchases) if not category_purchases.empty else []
    current_year_week = (
        _resolve_actual_year_week(category_purchases, actual_week)
        if not category_purchases.empty
        else None
    )

    result: dict[str, Any] = {
        "aggregate": {
            "current_week": calculate_current_week_metrics(
                category_purchases,
                actual_week,
                category_return_weeks,
                all_weeks=all_weeks,
                current_year_week=current_year_week,
            ),
            "cycle": calculate_cycle_metrics(category_purchases, resolved_cycle_weeks),
        },
        "detail": {},
    }

    if not detail_models:
        return result

    detail_set = {model.strip() for model in detail_models}
    detail_purchases = purchases[purchases["model"].isin(detail_set)]
    grouped = (
        detail_purchases.groupby("model", sort=False)
        if not detail_purchases.empty
        else None
    )

    for model in detail_models:
        model_key = model.strip()
        model_purchases = (
            grouped.get_group(model_key)
            if grouped is not None and model_key in grouped.groups
            else purchases.iloc[0:0]
        )
        detail_return_weeks = get_return_weeks(
            return_weeks_map,
            category_name,
            detail_name=model,
        )
        model_weeks = _sorted_weeks(model_purchases) if not model_purchases.empty else []
        model_current_week = (
            _resolve_actual_year_week(model_purchases, actual_week)
            if not model_purchases.empty
            else None
        )
        result["detail"][model] = {
            "current_week": calculate_current_week_metrics(
                model_purchases,
                actual_week,
                detail_return_weeks,
                all_weeks=model_weeks,
                current_year_week=model_current_week,
            ),
            "cycle": calculate_cycle_metrics(model_purchases, resolved_cycle_weeks),
        }

    return result


def calculate_all_volume_metrics(
    purchases_df: pd.DataFrame,
    spravochnik: dict[str, Any],
    actual_week: int,
) -> dict[str, dict[str, Any]]:
    """Считает метрики для всех категорий из справочника."""
    purchases = prepare_purchases(purchases_df)
    volumes = spravochnik.get("volumes", {})
    cycles_df = spravochnik.get("cycles_normalized")
    if cycles_df is None:
        cycles_df = normalize_cycles_df(spravochnik.get("cycles"))
    return_weeks_map = spravochnik.get("return_weeks", {})
    cycle_weeks = get_cycle_weeks(cycles_df, actual_week)

    return {
        volume: calculate_volume_metrics(
            purchases,
            config,
            actual_week,
            cycles_df,
            volume,
            return_weeks_map,
            cycle_weeks=cycle_weeks,
        )
        for volume, config in volumes.items()
        if config.get("category")
    }
