"""Olist Sales Intelligence — Streamlit dashboard (giriş noktası)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from dashboard import data, ui
from dashboard.data import DataError

st.set_page_config(page_title="Olist Sales Intelligence", page_icon="📊", layout="wide")
ui.apply_css()

# Sayfa dosyaları yalnızca dashboard.views içindeki ilgili fonksiyonu çağırır (dosya yolu: test ve gezinme için).
# Varsayılan sayfa her zaman kök adreste (/) sunulur; url_path verilmez (verilirse o adres "Page not found" gösterir).
PAGES = [
    st.Page("page_overview.py", title="Genel Bakış", default=True),
    st.Page("page_categories.py", title="Kategori Analizi", url_path="kategori"),
    st.Page("page_customers.py", title="Müşteri Analizi", url_path="musteri"),
    st.Page("page_delivery.py", title="Teslimat Performansı", url_path="teslimat"),
]

# Logo kenar çubuğunun en üstünde, gezinme menüsünün üzerinde görünür.
st.logo(str(Path(__file__).resolve().parent / "assets" / "logo.svg"), size="large")
navigation = st.navigation(PAGES, position="sidebar")

with st.sidebar:
    try:
        fresh = data.freshness()
        st.caption(f"Son başarılı yükleme: **{ui.fmt_datetime(fresh.get('last_successful_load_at'))}**")
    except DataError as exc:
        st.error(exc.user_message)
        st.stop()
    if st.button("Verileri yenile", help="Önbelleği temizler ve verileri veritabanından yeniden okur. "
                 f"Önbellek süresi: {data.DATA_TTL_SECONDS // 60} dk; yeni bir yükleme en geç "
                 f"{data.FRESHNESS_TTL_SECONDS} sn içinde fark edilir."):
        data.clear_cache()
        st.rerun()

navigation.run()

with st.sidebar:
    st.divider()
    st.caption(ui.CURRENCY_NOTE)
    st.caption("Renkler: turkuaz = ürün satış tutarı · lacivert = sipariş/müşteri sayıları · "
               "turuncu = geç teslimat · açık turkuaz = kısmi ay.")
