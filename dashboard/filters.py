"""Kenar çubuğu filtreleri. Seçimler sayfalar arasında korunur (st.session_state); her sayfa yalnızca
kendisini etkileyen filtreleri gösterir ve kapsam satırında hangi filtrenin uygulandığını yazar."""

from __future__ import annotations

import datetime as dt

import streamlit as st

from dashboard import data
from dashboard.data import Filters

DATE_KEY, STATES_KEY, CATS_KEY = "filter_dates", "filter_states", "filter_categories"


def _persisted(widget_key: str, store_key: str):
    st.session_state[store_key] = st.session_state[widget_key]


def sidebar_filters(run_id: str | None, cov: dict, *, states: bool, categories: bool) -> Filters | None:
    first, last = cov["first_purchase_date"], cov["last_purchase_date"]
    st.session_state.setdefault(DATE_KEY, (first, last))
    st.session_state.setdefault(STATES_KEY, [])
    st.session_state.setdefault(CATS_KEY, [])

    with st.sidebar:
        st.markdown("### Filtreler")
        picked = st.date_input(
            "Satın alma tarihi",
            value=st.session_state[DATE_KEY],
            min_value=first,
            max_value=last,
            format="DD.MM.YYYY",
            key="w_dates",
            on_change=_persisted, args=("w_dates", DATE_KEY),
            help=f"Veri kapsamı: {first:%d.%m.%Y} – {last:%d.%m.%Y} (teslim edilmiş siparişlerin satın alma günleri).",
        )
        if st.button("Tüm veri kapsamı", width="stretch"):
            st.session_state[DATE_KEY] = (first, last)
            st.session_state.pop("w_dates", None)
            st.rerun()

        cat_options, state_df = data.filter_options(run_id)
        chosen_states: tuple[str, ...] = ()
        chosen_cats: tuple[str, ...] = ()
        if states:
            labels = {r.state: f"{r.state} · {r.region}" for r in state_df.itertuples()}
            chosen_states = tuple(st.multiselect(
                "Müşteri eyaleti", options=list(labels), format_func=labels.get,
                default=[s for s in st.session_state[STATES_KEY] if s in labels],
                key="w_states", on_change=_persisted, args=("w_states", STATES_KEY),
                placeholder="Tümü", help="Siparişi veren müşterinin eyaleti. Boş = tüm eyaletler.",
            ))
        if categories:
            chosen_cats = tuple(st.multiselect(
                "Ürün kategorisi", options=cat_options,
                default=[c for c in st.session_state[CATS_KEY] if c in cat_options],
                key="w_categories", on_change=_persisted, args=("w_categories", CATS_KEY),
                placeholder="Tümü",
                help="Yalnızca seçili kategorilerdeki kalemler; sipariş, seçili kategoride kalemi olan farklı sipariş olarak bir kez sayılır.",
            ))

    if not isinstance(picked, (tuple, list)) or len(picked) != 2:
        st.info("Tarih aralığı için başlangıç ve bitiş günlerini seçin.")
        return None
    date_from, date_to = picked
    return Filters(date_from=date_from, date_to=date_to, states=chosen_states, categories=chosen_cats)


def date_label(f: Filters) -> str:
    return f"{f.date_from:%d.%m.%Y} – {f.date_to:%d.%m.%Y} (satın alma günü)"


def rfm_as_of(f: Filters) -> dt.date:
    """RFM gözlem tarihi = seçili bitiş günü + 1 (bitiş günü dahil tüm satın almalar)."""
    return f.date_to + dt.timedelta(days=1)
