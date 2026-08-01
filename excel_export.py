"""Экспорт таблиц метрик в Excel."""

from io import BytesIO

import pandas as pd
from openpyxl.utils import get_column_letter

from report_tables import COLUMN_CYCLE, COLUMN_WEEK, METRIC_COLUMN

COLUMN_WIDTHS = {
    METRIC_COLUMN: 38,
    COLUMN_CYCLE: 22,
    COLUMN_WEEK: 24,
}


def _sanitize_sheet_name(name: str) -> str:
    """Ограничивает имя листа Excel (макс. 31 символ, без запрещённых символов)."""
    forbidden = set(r"[]:*?/\\")
    cleaned = "".join(ch if ch not in forbidden else "_" for ch in name)
    return cleaned[:31] or "Лист"


def build_excel_filename(week_label: str) -> str:
    """Формирует имя файла отчёта: CPA *номер недели* неделя.xlsx."""
    return f"CPA {week_label} неделя.xlsx"


def export_report_to_excel(metrics_tables: dict[str, pd.DataFrame]) -> bytes:
    """
    Экспортирует все таблицы метрик в Excel.
    Каждая категория — отдельный лист с настроенной шириной столбцов.
    """
    buffer = BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for category_name, table in metrics_tables.items():
            sheet_name = _sanitize_sheet_name(category_name)
            table.to_excel(writer, sheet_name=sheet_name, index=False)
            worksheet = writer.sheets[sheet_name]

            for col_idx, col_name in enumerate(table.columns, start=1):
                letter = get_column_letter(col_idx)
                width = COLUMN_WIDTHS.get(col_name, 18)
                worksheet.column_dimensions[letter].width = width

    buffer.seek(0)
    return buffer.getvalue()
