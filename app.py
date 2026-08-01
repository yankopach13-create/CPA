"""Streamlit-приложение для анализа клиентов в продукте."""

import streamlit as st

from metrics_calculator import (
    WEEK_SELECTOR_OPTIONS,
    calculate_all_volume_metrics,
    detect_actual_week,
    format_cycle_message,
    format_week_label,
    parse_selected_week,
)
from report_tables import build_all_metrics_tables
from excel_export import build_excel_filename, export_report_to_excel
from processor import (
    get_cycle_number,
    load_spravochnik,
    process_excel,
    validate_file,
)


st.set_page_config(
    page_title="Анализ клиентов в продукте",
    page_icon="📊",
    layout="wide",
)

st.title("🛒 👤 Анализ клиентов в продукте")

st.markdown(
    """
    <style>
    div[data-testid="stVerticalBlock"]:has(#top-controls-row)
    > div[data-testid="stHorizontalBlock"] {
        align-items: stretch !important;
    }
    div[data-testid="stVerticalBlock"]:has(#top-controls-row)
    > div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
        display: flex !important;
        flex-direction: column !important;
    }
    div[data-testid="stVerticalBlock"]:has(#top-controls-row)
    > div[data-testid="stHorizontalBlock"] .control-panel-title {
        font-size: 1.1rem;
        font-weight: 900;
        color: #111827;
        line-height: 1.25;
        min-height: 2.5rem;
        margin: 0 0 0.4rem 0;
        display: flex;
        align-items: flex-end;
    }
    div[data-testid="stVerticalBlock"]:has(#top-controls-row)
    > div[data-testid="stHorizontalBlock"] .control-panel-title strong {
        font-weight: 900;
    }
    div[data-testid="stVerticalBlock"]:has(#top-controls-row)
    > div[data-testid="stHorizontalBlock"]
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.upload-control-panel) {
        flex: 0 0 auto !important;
        min-height: 4.5rem !important;
        height: auto !important;
        box-sizing: border-box !important;
        background: #f9fafb !important;
        border: 1px solid #d1d5db !important;
        border-radius: 4px !important;
        padding: 0.5rem 1rem !important;
        margin: 0 !important;
    }
    div[data-testid="stVerticalBlock"]:has(#top-controls-row)
    > div[data-testid="stHorizontalBlock"]
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.week-control-panel) {
        flex: 1 1 auto !important;
        min-height: 8.5rem !important;
        height: 100% !important;
        box-sizing: border-box !important;
        background: #f9fafb !important;
        border: 1px solid #d1d5db !important;
        border-radius: 4px !important;
        padding: 0.75rem 1rem !important;
        margin: 0 !important;
    }
    div[data-testid="stVerticalBlock"]:has(#top-controls-row)
    > div[data-testid="stHorizontalBlock"]
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.upload-control-panel) > div {
        min-height: 100%;
        display: flex;
        align-items: center;
        width: 100%;
    }
    div[data-testid="stVerticalBlock"]:has(#top-controls-row)
    > div[data-testid="stHorizontalBlock"]
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.week-control-panel) > div {
        min-height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: flex-start;
        width: 100%;
        gap: 0.75rem;
    }
    div[data-testid="stVerticalBlock"]:has(#top-controls-row)
    > div[data-testid="stHorizontalBlock"] [data-testid="stFileUploader"] {
        width: 100%;
        border: none !important;
        background: transparent !important;
        padding: 0 !important;
        margin: 0 !important;
        min-height: auto !important;
    }
    div[data-testid="stVerticalBlock"]:has(#top-controls-row)
    > div[data-testid="stHorizontalBlock"] [data-testid="stSelectbox"] {
        max-width: 110px;
        margin: 0;
    }
    div[data-testid="stVerticalBlock"]:has(#top-controls-row)
    > div[data-testid="stHorizontalBlock"] [data-baseweb="select"] {
        background-color: #ffffff !important;
        border: 1px solid #9ca3af !important;
        border-radius: 4px !important;
        min-height: 2.25rem !important;
    }
    div[data-testid="stVerticalBlock"]:has(#top-controls-row)
    > div[data-testid="stHorizontalBlock"] [data-baseweb="select"] > div {
        font-size: 1rem !important;
        font-weight: 600 !important;
        color: #111827 !important;
        line-height: 1.2 !important;
    }
    div[data-testid="stVerticalBlock"]:has(#top-controls-row)
    > div[data-testid="stHorizontalBlock"] .actual-week-meta-block {
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: 0.15rem;
        min-height: 2.25rem;
    }
    div[data-testid="stVerticalBlock"]:has(#top-controls-row)
    > div[data-testid="stHorizontalBlock"] .actual-week-meta {
        font-size: 0.88rem;
        font-weight: 500;
        color: #4b5563;
        line-height: 1.4;
        margin: 0;
    }
    div[data-testid="stVerticalBlock"]:has(#top-controls-row)
    > div[data-testid="stHorizontalBlock"] .actual-week-placeholder {
        font-size: 0.9rem;
        font-weight: 500;
        color: #9ca3af;
        line-height: 1.4;
        margin: 0;
        width: 100%;
    }
    div[data-testid="stVerticalBlock"]:has(#top-controls-row)
    > div[data-testid="stHorizontalBlock"]
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.week-control-panel)
    [data-testid="stButton"] {
        width: 100%;
        margin-top: auto !important;
        padding-top: 0.25rem;
    }
    div[data-testid="stVerticalBlock"]:has(#top-controls-row)
    > div[data-testid="stHorizontalBlock"]
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.week-control-panel)
    [data-testid="stButton"] > button {
        width: 100%;
        min-height: 2.5rem;
        font-weight: 600;
    }
    div[data-testid="stVerticalBlock"]:has(#excel-download-marker)
    [data-testid="stDownloadButton"] {
        width: 100%;
        margin-top: 0.5rem;
    }
    div[data-testid="stVerticalBlock"]:has(#excel-download-marker)
    [data-testid="stDownloadButton"] > button {
        width: 100%;
        min-height: 2.5rem;
        font-weight: 600;
        background-color: #6b7280 !important;
        color: #ffffff !important;
        border: 1px solid #4b5563 !important;
    }
    div[data-testid="stVerticalBlock"]:has(#excel-download-marker)
    [data-testid="stDownloadButton"] > button:hover {
        background-color: #4b5563 !important;
        border-color: #374151 !important;
        color: #ffffff !important;
    }
    div[data-testid="stVerticalBlock"]:has(#excel-download-marker)
    [data-testid="stDownloadButton"] > button:focus {
        box-shadow: none !important;
        border-color: #374151 !important;
    }
    .categories-section-divider {
        border: none;
        border-top: 1px solid #d1d5db;
        margin: 1.25rem 0 0.75rem 0;
    }
    .categories-section-title {
        font-size: 2rem;
        font-weight: 800;
        color: #111827;
        line-height: 1.3;
        margin: 0 0 1rem 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "analysis_started" not in st.session_state:
    st.session_state.analysis_started = False


def _reset_analysis() -> None:
    st.session_state.analysis_started = False


@st.cache_data(ttl=300, show_spinner=False)
def _load_spravochnik_cached() -> dict:
    """Кэширует загрузку справочника; secrets читаются внутри функции."""
    return load_spravochnik(streamlit_secrets=st.secrets)


try:
    spravochnik = _load_spravochnik_cached()
except FileNotFoundError as exc:
    st.warning(str(exc))
    spravochnik = None
except Exception as exc:
    error_text = str(exc).strip() or f"{type(exc).__name__}: {exc!r}"
    st.error(f"Ошибка чтения справочника: {error_text}")
    spravochnik = None

purchase_result = None
processing_error: str | None = None
selected_week_label: str | None = None

st.markdown('<span id="top-controls-row" style="display:none;"></span>', unsafe_allow_html=True)
upload_col, week_col = st.columns([2, 1], gap="medium")

with upload_col:
    st.markdown(
        '<p class="control-panel-title"><strong>Данные о покупках клиентов за 13 недель</strong></p>',
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        st.markdown('<span class="control-panel upload-control-panel"></span>', unsafe_allow_html=True)
        uploaded_purchases = st.file_uploader(
            "Данные о покупках клиентов за 13 недель",
            type=["xlsx", "xls"],
            key="purchases_uploader",
            label_visibility="collapsed",
        )
    excel_download_slot = st.empty()

if uploaded_purchases is not None:
    try:
        if spravochnik is None:
            raise ValueError("Справочник не загружен. Проверьте Google Sheets или файл spravochnik.xlsx.")

        validate_file(uploaded_purchases)
        purchase_result = process_excel(uploaded_purchases)

        file_key = f"{uploaded_purchases.name}:{uploaded_purchases.size}"
        _, detected_week, _ = detect_actual_week(purchase_result["data"])
        detected_label = format_week_label(detected_week)

        if st.session_state.get("loaded_file_key") != file_key:
            st.session_state.loaded_file_key = file_key
            st.session_state.actual_week_select = detected_label
            st.session_state.analysis_started = False
    except Exception as exc:
        processing_error = str(exc)

with week_col:
    st.markdown(
        '<p class="control-panel-title"><strong>Актуальная неделя</strong></p>',
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        st.markdown('<span class="control-panel week-control-panel"></span>', unsafe_allow_html=True)
        if purchase_result is not None and processing_error is None:
            default_label = st.session_state.get(
                "actual_week_select",
                format_week_label(detect_actual_week(purchase_result["data"])[1]),
            )
            default_index = (
                WEEK_SELECTOR_OPTIONS.index(default_label)
                if default_label in WEEK_SELECTOR_OPTIONS
                else 0
            )

            week_sel_col, week_meta_col = st.columns(
                [1, 1.4],
                gap="small",
                vertical_alignment="center",
            )
            with week_sel_col:
                selected_week_label = st.selectbox(
                    "Актуальная неделя",
                    WEEK_SELECTOR_OPTIONS,
                    index=default_index,
                    label_visibility="collapsed",
                    key="actual_week_select",
                    on_change=_reset_analysis,
                )
            with week_meta_col:
                actual_week = parse_selected_week(selected_week_label)
                cycle_number = get_cycle_number(spravochnik["cycles"], actual_week)
                cycle_text = format_cycle_message(cycle_number)
                st.markdown(
                    f'<div class="actual-week-meta-block">'
                    f'<p class="actual-week-meta">{cycle_text}</p>'
                    "</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<p class="actual-week-placeholder">Загрузите файл</p>',
                unsafe_allow_html=True,
            )

        can_start = (
            purchase_result is not None
            and processing_error is None
            and spravochnik is not None
            and selected_week_label is not None
        )
        if st.button(
            "Начать анализ",
            type="primary",
            disabled=not can_start,
            use_container_width=True,
        ):
            st.session_state.analysis_started = True

metrics_tables = None
if (
    st.session_state.analysis_started
    and purchase_result is not None
    and processing_error is None
    and selected_week_label is not None
    and spravochnik is not None
):
    actual_week = parse_selected_week(selected_week_label)
    metrics_by_volume = calculate_all_volume_metrics(
        purchase_result["data"],
        spravochnik,
        actual_week,
    )
    metrics_tables = build_all_metrics_tables(spravochnik, metrics_by_volume)

if metrics_tables is not None:
    with excel_download_slot.container():
        st.markdown(
            '<span id="excel-download-marker" style="display:none;"></span>',
            unsafe_allow_html=True,
        )
        st.download_button(
            "Скачать отчёт в эксель",
            data=export_report_to_excel(metrics_tables),
            file_name=build_excel_filename(selected_week_label),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="excel_report_download",
        )

if metrics_tables is not None:
    st.markdown('<hr class="categories-section-divider">', unsafe_allow_html=True)
    st.markdown(
        '<p class="categories-section-title">Категории и продукты</p>',
        unsafe_allow_html=True,
    )

if processing_error:
    st.error(f"Ошибка при обработке файла с покупками: {processing_error}")
elif metrics_tables is not None:
    table_items = list(metrics_tables.items())
    for row_start in range(0, len(table_items), 3):
        row_items = table_items[row_start : row_start + 3]
        columns = st.columns(3)
        for column, (category_name, table) in zip(columns, row_items, strict=True):
            with column:
                st.markdown(f"**{category_name}**")
                st.dataframe(
                    table,
                    use_container_width=True,
                    hide_index=True,
                )
