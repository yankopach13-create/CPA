"""Streamlit-приложение для анализа клиентов в продукте."""

import html

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
from google_sheets import (
    add_excluded_product,
    add_product_to_category,
    create_category_with_product,
)
from purchases import find_unknown_products, prepare_purchases
from spravochnik_config import (
    build_google_sheets_url,
    DEFAULT_SHEETS_ID,
    get_google_credentials_from_secrets,
    get_sheets_id_from_env_or_secrets,
    has_google_secrets_config,
)
from processor import (
    NEW_CATEGORY_OPTION,
    get_cycle_number,
    load_spravochnik,
    process_excel,
    validate_file,
)

# TTL кэша справочника (секунды). После записи продуктов кэш сбрасывается явно.
SPRAVOCHNIK_CACHE_TTL = 300


st.set_page_config(
    page_title="Анализ клиентов в продукте",
    page_icon="🛒",
    layout="wide",
)

# Текст подсказки для загрузки файла — замените позже на финальный.
UPLOAD_HINT_TEXT = (
    "Здесь будет подсказка о том, какой файл нужно загрузить."
)


def _upload_hint_html() -> str:
    hint_text = html.escape(UPLOAD_HINT_TEXT).replace("\n", "<br>")
    return (
        f'<div class="upload-hint-wrap" id="upload-hint-marker">'
        f'<span class="upload-hint-label">ℹ️ Подсказка по загрузке файла</span>'
        f'<span class="upload-hint-tooltip">{hint_text}</span>'
        "</div>"
    )


st.title("🛒 👤 Анализ клиентов в продукте")

_sheets_id = get_sheets_id_from_env_or_secrets(st.secrets) or DEFAULT_SHEETS_ID
st.markdown(
    f'<p style="margin: 0 0 0.5rem 0;">'
    f'<a href="{build_google_sheets_url(_sheets_id)}" target="_blank" rel="noopener noreferrer">'
    "База данных"
    "</a></p>",
    unsafe_allow_html=True,
)
st.markdown(_upload_hint_html(), unsafe_allow_html=True)

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
        min-height: 2rem;
        margin: 0 0 0.25rem 0;
        display: flex;
        align-items: flex-end;
    }
    .upload-hint-wrap {
        position: relative;
        display: inline-block;
        margin: 0 0 0.35rem 0;
    }
    .upload-hint-label {
        font-size: 0.9rem;
        font-weight: 500;
        color: #4b5563;
        cursor: help;
        border-bottom: 1px dotted #9ca3af;
        line-height: 1.3;
    }
    .upload-hint-tooltip {
        visibility: hidden;
        opacity: 0;
        position: absolute;
        left: 0;
        top: calc(100% + 4px);
        z-index: 1000;
        min-width: 260px;
        max-width: 420px;
        padding: 0.6rem 0.8rem;
        background: #1f2937;
        color: #f9fafb;
        font-size: 0.86rem;
        font-weight: 400;
        line-height: 1.45;
        border-radius: 6px;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.18);
        transition: opacity 0.12s ease;
        white-space: normal;
        pointer-events: none;
    }
    .upload-hint-wrap:hover .upload-hint-tooltip {
        visibility: visible;
        opacity: 1;
    }
    div[data-testid="stVerticalBlock"]:has(#upload-hint-marker) {
        margin-bottom: 0 !important;
        padding-bottom: 0 !important;
    }
    div[data-testid="stVerticalBlock"]:has(#top-controls-row) {
        margin-top: 0 !important;
        padding-top: 0 !important;
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
    div[data-testid="stVerticalBlock"]:has(#top-controls-row)
    > div[data-testid="stHorizontalBlock"]
    [data-testid="stButton"] > button:disabled,
    div[data-testid="stVerticalBlock"]:has(#excel-download-marker)
    [data-testid="stDownloadButton"] > button:disabled {
        opacity: 0.45 !important;
        cursor: not-allowed !important;
        filter: grayscale(0.15);
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
if "pending_new_products" not in st.session_state:
    st.session_state.pending_new_products = []
if "pending_new_products_total" not in st.session_state:
    st.session_state.pending_new_products_total = 0
if "purchases_raw" not in st.session_state:
    st.session_state.purchases_raw = None
if "purchases_prepared" not in st.session_state:
    st.session_state.purchases_prepared = None
if "metrics_tables" not in st.session_state:
    st.session_state.metrics_tables = None
if "excel_report_bytes" not in st.session_state:
    st.session_state.excel_report_bytes = None
if "metrics_cache_key" not in st.session_state:
    st.session_state.metrics_cache_key = None


def _reset_analysis() -> None:
    """Сбрасывает результат анализа при смене недели."""
    st.session_state.analysis_started = False
    st.session_state.metrics_tables = None
    st.session_state.excel_report_bytes = None
    st.session_state.metrics_cache_key = None


def _clear_purchase_cache() -> None:
    """Очищает кэш загруженного файла покупок."""
    st.session_state.purchases_raw = None
    st.session_state.purchases_prepared = None
    st.session_state.metrics_tables = None
    st.session_state.excel_report_bytes = None
    st.session_state.metrics_cache_key = None
    st.session_state.analysis_started = False


def _resolve_sheets_credentials(spravochnik: dict) -> tuple[str | None, str | None, dict | None]:
    """Достаёт sheets_id и учётные данные для записи в Google Sheets."""
    sheets_id = spravochnik.get("sheets_id")
    credentials_path = spravochnik.get("credentials_path")
    credentials_info = spravochnik.get("credentials_info")

    if not sheets_id or (not credentials_path and not credentials_info):
        secrets_id, secrets_info = get_google_credentials_from_secrets(st.secrets)
        sheets_id = sheets_id or secrets_id or DEFAULT_SHEETS_ID
        credentials_info = credentials_info or secrets_info

    return sheets_id, credentials_path, credentials_info


@st.cache_data(ttl=SPRAVOCHNIK_CACHE_TTL, show_spinner="Загрузка справочника…")
def _cached_load_spravochnik(
    use_google_secrets: bool,
    sheets_id: str | None,
    credentials_info: dict | None,
) -> dict:
    """Кэшированная загрузка справочника (Google Sheets или локальный Excel)."""
    if use_google_secrets:
        return load_spravochnik(
            sheets_id=sheets_id or DEFAULT_SHEETS_ID,
            credentials_info=credentials_info,
        )
    return load_spravochnik(streamlit_secrets=st.secrets)


def _invalidate_spravochnik_cache() -> None:
    """Сбрасывает кэш справочника после записи в Google Sheets."""
    _cached_load_spravochnik.clear()


@st.dialog("Найден новый продукт")
def _new_product_dialog(spravochnik: dict) -> None:
    """Диалог назначения неизвестного продукта в категорию или исключения."""
    pending: list[dict[str, str]] = st.session_state.pending_new_products
    if not pending:
        return

    product = pending[0]
    product_key = product["model"]
    total = st.session_state.pending_new_products_total or len(pending)
    remaining = len(pending)

    st.markdown(f"**{product['display_name']}**")
    st.caption(f"Осталось обработать: {remaining} из {total}")

    categories = list(spravochnik.get("volumes", {}).keys())
    options = [*categories, NEW_CATEGORY_OPTION]
    selected = st.selectbox(
        "Отнесите продукт в категорию",
        options,
        key=f"new_prod_category_{product_key}",
    )

    new_category_name = ""
    return_weeks_value = 4
    if selected == NEW_CATEGORY_OPTION:
        new_category_name = st.text_input(
            "Название новой категории",
            key=f"new_prod_cat_name_{product_key}",
        )
        return_weeks_value = int(
            st.number_input(
                "Возврат (недель)",
                min_value=1,
                value=4,
                step=1,
                key=f"new_prod_return_{product_key}",
            )
        )

    add_to_detail = (
        st.radio(
            "Добавить продукт в детализацию по категории?",
            ["Нет", "Да"],
            horizontal=True,
            key=f"new_prod_detail_{product_key}",
        )
        == "Да"
    )

    error_slot = st.empty()
    save_col, skip_col = st.columns(2)

    def _finish_current() -> None:
        pending.pop(0)
        st.session_state.pending_new_products = pending
        _invalidate_spravochnik_cache()
        st.rerun()

    with save_col:
        if st.button("Сохранить", type="primary", use_container_width=True):
            try:
                sheets_id, credentials_path, credentials_info = _resolve_sheets_credentials(
                    spravochnik
                )
                if not sheets_id or not spravochnik.get("writable"):
                    raise ValueError(
                        "Добавление продуктов доступно только при подключении к Google Sheets. "
                        "Service account должен иметь право «Редактор»."
                    )

                if selected == NEW_CATEGORY_OPTION:
                    if not new_category_name.strip():
                        raise ValueError("Укажите название новой категории.")
                    create_category_with_product(
                        sheets_id=sheets_id,
                        category_name=new_category_name,
                        product_model=product["model"],
                        return_weeks=return_weeks_value,
                        add_to_detail=add_to_detail,
                        credentials_path=credentials_path,
                        credentials_info=credentials_info,
                    )
                else:
                    add_product_to_category(
                        sheets_id=sheets_id,
                        category_name=selected,
                        product_model=product["model"],
                        add_to_detail=add_to_detail,
                        credentials_path=credentials_path,
                        credentials_info=credentials_info,
                    )
                _finish_current()
            except Exception as exc:
                error_slot.error(str(exc))

    with skip_col:
        if st.button("Пропустить", use_container_width=True):
            try:
                sheets_id, credentials_path, credentials_info = _resolve_sheets_credentials(
                    spravochnik
                )
                if not sheets_id or not spravochnik.get("writable"):
                    raise ValueError(
                        "Исключение продуктов доступно только при подключении к Google Sheets."
                    )
                add_excluded_product(
                    sheets_id=sheets_id,
                    product_model=product["model"],
                    credentials_path=credentials_path,
                    credentials_info=credentials_info,
                )
                _finish_current()
            except Exception as exc:
                error_slot.error(str(exc))


def _load_spravochnik_for_app() -> dict:
    """Загружает справочник с кэшированием между rerun."""
    if has_google_secrets_config(st.secrets):
        sheets_id, credentials_info = get_google_credentials_from_secrets(st.secrets)
        return _cached_load_spravochnik(
            use_google_secrets=True,
            sheets_id=sheets_id or DEFAULT_SHEETS_ID,
            credentials_info=credentials_info,
        )
    return _cached_load_spravochnik(
        use_google_secrets=False,
        sheets_id=None,
        credentials_info=None,
    )


try:
    spravochnik = _load_spravochnik_for_app()
except FileNotFoundError as exc:
    st.warning(str(exc))
    spravochnik = None
except Exception as exc:
    error_text = str(exc).strip() or f"{type(exc).__name__} (без текста)"
    st.error(f"Ошибка чтения справочника: {error_text}")
    with st.expander("Что проверить"):
        st.markdown(
            """
            1. **Google Cloud** → APIs & Services → включены **Google Sheets API** и **Google Drive API** для проекта `b2b-rnp`.
            2. **Google Sheets** → Поделиться → добавлен `cpa-951@b2b-rnp.iam.gserviceaccount.com` с правом **Редактор** (нужно для новых продуктов).
            3. **Streamlit Cloud Secrets** → секции `[google]` и `[google.service_account]` заполнены.
            4. После изменений — **Reboot app** на Streamlit Cloud.
            """
        )
    spravochnik = None

purchase_result = None
purchases_prepared = st.session_state.purchases_prepared
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
        file_key = f"{uploaded_purchases.name}:{uploaded_purchases.size}"

        # Парсим Excel и готовим данные только при смене файла.
        if st.session_state.get("loaded_file_key") != file_key:
            purchase_result = process_excel(uploaded_purchases)
            purchases_prepared = prepare_purchases(purchase_result["data"])
            _, detected_week, _ = detect_actual_week(purchases_prepared)
            detected_label = format_week_label(detected_week)

            st.session_state.loaded_file_key = file_key
            st.session_state.purchases_raw = purchase_result["data"]
            st.session_state.purchases_prepared = purchases_prepared
            st.session_state.actual_week_select = detected_label
            _reset_analysis()

            if spravochnik.get("writable"):
                unknowns = find_unknown_products(
                    purchases_prepared,
                    spravochnik.get("volumes", {}),
                    spravochnik.get("excluded", []),
                )
                st.session_state.pending_new_products = unknowns
                st.session_state.pending_new_products_total = len(unknowns)
            else:
                st.session_state.pending_new_products = []
                st.session_state.pending_new_products_total = 0
        else:
            purchases_prepared = st.session_state.purchases_prepared
            purchase_result = {
                "data": st.session_state.purchases_raw,
                "row_count": len(st.session_state.purchases_raw)
                if st.session_state.purchases_raw is not None
                else 0,
            }
    except Exception as exc:
        processing_error = str(exc)
        _clear_purchase_cache()
        purchases_prepared = None
        purchase_result = None
elif st.session_state.get("loaded_file_key"):
    # Файл убрали из uploader — очищаем кэш.
    _clear_purchase_cache()
    st.session_state.loaded_file_key = None
    st.session_state.pending_new_products = []
    st.session_state.pending_new_products_total = 0
    purchases_prepared = None

has_pending_products = bool(st.session_state.get("pending_new_products"))
if (
    has_pending_products
    and purchases_prepared is not None
    and processing_error is None
    and spravochnik is not None
):
    _new_product_dialog(spravochnik)

with week_col:
    st.markdown(
        '<p class="control-panel-title"><strong>Актуальная неделя</strong></p>',
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        st.markdown('<span class="control-panel week-control-panel"></span>', unsafe_allow_html=True)
        if purchases_prepared is not None and processing_error is None and spravochnik is not None:
            default_label = st.session_state.get(
                "actual_week_select",
                format_week_label(detect_actual_week(purchases_prepared)[1]),
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
                cycles_source = spravochnik.get("cycles_normalized", spravochnik["cycles"])
                cycle_number = get_cycle_number(cycles_source, actual_week)
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
            purchases_prepared is not None
            and processing_error is None
            and spravochnik is not None
            and selected_week_label is not None
            and not has_pending_products
        )
        if has_pending_products:
            st.warning(
                f"Найдены новые продукты ({len(st.session_state.pending_new_products)}). "
                "Назначьте или пропустите их, затем нажмите «Начать анализ»."
            )
        if st.button(
            "Начать анализ",
            type="primary",
            disabled=not can_start,
            use_container_width=True,
        ):
            st.session_state.analysis_started = True

metrics_tables = st.session_state.metrics_tables
if (
    st.session_state.analysis_started
    and purchases_prepared is not None
    and processing_error is None
    and selected_week_label is not None
    and spravochnik is not None
):
    actual_week = parse_selected_week(selected_week_label)
    cache_key = f"{st.session_state.get('loaded_file_key')}:{actual_week}"
    if st.session_state.metrics_cache_key != cache_key or metrics_tables is None:
        metrics_by_volume = calculate_all_volume_metrics(
            purchases_prepared,
            spravochnik,
            actual_week,
        )
        metrics_tables = build_all_metrics_tables(spravochnik, metrics_by_volume)
        st.session_state.metrics_tables = metrics_tables
        st.session_state.metrics_cache_key = cache_key
        st.session_state.excel_report_bytes = export_report_to_excel(metrics_tables)
    else:
        metrics_tables = st.session_state.metrics_tables

can_download_excel = metrics_tables is not None
excel_bytes = st.session_state.excel_report_bytes or b""
with excel_download_slot.container():
    st.markdown(
        '<span id="excel-download-marker" style="display:none;"></span>',
        unsafe_allow_html=True,
    )
    st.download_button(
        "Скачать отчёт в эксель",
        data=excel_bytes if can_download_excel else b"",
        file_name=build_excel_filename(selected_week_label) if can_download_excel else "report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        disabled=not can_download_excel,
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
        for column, (category_name, table) in zip(columns, row_items):
            with column:
                st.markdown(f"**{category_name}**")
                st.dataframe(
                    table,
                    use_container_width=True,
                    hide_index=True,
                )
