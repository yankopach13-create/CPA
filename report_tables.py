"""Шаблон и построение таблицы метрик анализа клиентов."""

from typing import Any

import pandas as pd

COLUMN_CYCLE = "Накопительно за цикл"
COLUMN_WEEK = "Актуальная неделя цикла"
METRIC_COLUMN = "Метрики:"

METRICS = [
    "Продажи итого:",
    "Продажи с БК",
    "Продажи без БК",
    "Уник.клиентов с БК (накоп.)",
    "Возврат %",
    "Среднее в шт. на клиента с БК",
    "Повторные клиенты",
]

GENERAL_METRICS = METRICS
DETAILED_METRICS = METRICS


def _format_metric_value(metric_name: str, value: Any) -> Any:
    if value is None or pd.isna(value):
        return ""
    if metric_name == "Возврат %":
        return f"{float(value):.2f}%"
    if metric_name == "Среднее в шт. на клиента с БК":
        return f"{float(value):.2f}".replace(".", ",")
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, float):
        return round(value, 2)
    return value


def _make_row(
    label: str,
    *,
    week_value: Any = None,
    cycle_value: Any = None,
    is_detail: bool = False,
    metric_key: str | None = None,
) -> dict[str, Any]:
    display_label = f"    {label}" if is_detail else label
    format_key = metric_key or label.strip()
    return {
        METRIC_COLUMN: display_label,
        COLUMN_CYCLE: _format_metric_value(format_key, cycle_value),
        COLUMN_WEEK: _format_metric_value(format_key, week_value),
    }


def _metric_value(metrics: dict[str, Any], metric_name: str) -> Any:
    return metrics.get(metric_name)


def build_metrics_table(
    volume_config: dict[str, list[str]],
    metrics_data: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Строит таблицу метрик для одного объёма ОЭС.

    metrics_data:
        aggregate — current_week / cycle
        detail — метрики по моделям детализации
    """
    detail_models = volume_config.get("detail", [])
    metrics_data = metrics_data or {"aggregate": {}, "detail": {}}
    aggregate = metrics_data.get("aggregate", {})
    aggregate_current = aggregate.get("current_week", {})
    aggregate_cycle = aggregate.get("cycle", {})
    detail = metrics_data.get("detail", {})

    rows: list[dict[str, Any]] = []

    for metric in GENERAL_METRICS:
        rows.append(
            _make_row(
                metric,
                week_value=_metric_value(aggregate_current, metric),
                cycle_value=_metric_value(aggregate_cycle, metric),
                metric_key=metric,
            )
        )

    if detail_models:
        for metric in DETAILED_METRICS:
            rows.append(_make_row(metric))
            for model in detail_models:
                model_metrics = detail.get(model, {})
                model_current = model_metrics.get("current_week", {})
                model_cycle = model_metrics.get("cycle", {})
                rows.append(
                    _make_row(
                        model,
                        week_value=_metric_value(model_current, metric),
                        cycle_value=_metric_value(model_cycle, metric),
                        is_detail=True,
                        metric_key=metric,
                    )
                )

    return pd.DataFrame(rows, columns=[METRIC_COLUMN, COLUMN_CYCLE, COLUMN_WEEK])


def build_all_metrics_tables(
    spravochnik: dict[str, Any],
    metrics_by_volume: dict[str, dict[str, Any]] | None = None,
) -> dict[str, pd.DataFrame]:
    """Строит отдельные таблицы метрик для каждого объёма из справочника."""
    volumes = spravochnik.get("volumes", {})
    metrics_by_volume = metrics_by_volume or {}

    return {
        volume: build_metrics_table(
            config,
            metrics_by_volume.get(volume),
        )
        for volume, config in volumes.items()
        if config.get("category")
    }
