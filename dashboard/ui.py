"""Görünüm yardımcıları: renk anlamları, Türkçe sayı biçimi, grafik şablonu, durum mesajları.

Burada yalnızca BİÇİMLENDİRME yapılır; metrik hesabı yapılmaz.
"""

from __future__ import annotations

import datetime as dt
import math

import plotly.graph_objects as go
import streamlit as st

# Renk anlamları (tüm sayfalarda aynı)
TEAL = "#0E9AA7"       # ürün satış tutarı / ana metrik
TEAL_LIGHT = "#9ED8DC"  # aynı metrik, kısmi dönem
NAVY = "#0B1F3A"       # sipariş ve sayımlar, metin
ORANGE = "#E07A1F"     # geç teslimat / risk
GRAY = "#9AA9B8"       # referans, eksik veri
GRID = "#DCE6EC"

CURRENCY_NOTE = ("Para birimi kaynakta belirtilmemiştir; veri Brezilya'ya ait olduğu için BRL varsayılmıştır. "
                 "Ürün satış tutarı kalem fiyatlarının brüt toplamıdır (kargo hariç; net gelir veya kâr değildir).")

CSS = f"""
<style>
  .block-container {{ padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1280px; }}
  h1, h2, h3 {{ color: {NAVY}; letter-spacing: -0.01em; }}
  [data-testid="stMetric"] {{ background: #FFFFFF; border-color: {GRID}; }}
  [data-testid="stMetricLabel"] p {{ color: #44546A; font-size: 0.9rem; }}
  [data-testid="stMetricValue"] {{ color: {NAVY}; font-size: 1.6rem; }}
  .scope {{ color: #44546A; font-size: 0.88rem; margin: -0.4rem 0 1rem 0; }}
  .scope b {{ color: {NAVY}; }}
</style>
"""


def _group(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def fmt_int(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    return _group(int(value))


def fmt_decimal(value, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    s = f"{float(value):,.{digits}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_brl(value) -> str:
    text = fmt_decimal(value, 2)
    return "—" if text == "—" else f"{text} BRL"


def fmt_pct(ratio, digits: int = 1) -> str:
    if ratio is None or (isinstance(ratio, float) and math.isnan(ratio)):
        return "—"
    value = float(ratio) * 100
    sign = "-" if value < 0 and fmt_decimal(-value, digits) != fmt_decimal(0, digits) else ""
    return f"{sign}%{fmt_decimal(abs(value), digits)}"  # Türkçe: işaret yüzde işaretinden önce (-%75,0)


def growth_text(rate, status: str) -> str:
    """fn_monthly_sales growth_status kurallarına göre metin (oranı yeniden hesaplamaz)."""
    if status == "previous_month_zero":
        return "hesaplanamaz (önceki ay 0)"
    if status == "no_previous_month":
        return "önceki ay yok"
    if status == "partial_month":
        return "hesaplanmaz (kısmi ay)"
    if status == "previous_month_partial":
        return "hesaplanmaz (önceki ay kısmi)"
    return fmt_pct(rate)


def fmt_date(value: dt.date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else "—"


def fmt_datetime(value) -> str:
    """timestamptz değerini UTC olarak gösterir; boş veya NaT ise '—'."""
    try:
        return value.strftime("%d.%m.%Y %H:%M UTC")
    except (AttributeError, ValueError):
        return "—"


def apply_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def scope_caption(parts: list[tuple[str, str]]) -> None:
    """Filtre kapsamı satırı: [("Tarih", "..."), ("Eyalet", "...")]"""
    body = " · ".join(f"<b>{label}:</b> {value}" for label, value in parts)
    st.markdown(f'<div class="scope">Filtre kapsamı — {body}</div>', unsafe_allow_html=True)


def list_or_all(values: tuple[str, ...], all_label: str = "tümü") -> str:
    if not values:
        return all_label
    shown = ", ".join(values[:6])
    return shown + (f" (+{len(values) - 6})" if len(values) > 6 else "")


def style_figure(fig: go.Figure, height: int = 360, y_title: str | None = None) -> go.Figure:
    """Ortak görünüm. y_title YALNIZCA birincil y eksenine uygulanır (ikincil eksen kendi başlığını alır)."""
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=36, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#FFFFFF",
        font=dict(color=NAVY, size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hoverlabel=dict(bgcolor="#FFFFFF", font_color=NAVY),
        separators=",.",  # ondalık virgül, binlik nokta
        yaxis_title_text=y_title,
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def nice_step(max_value: float) -> float:
    """Eksen için yuvarlak adım (en fazla ~6 çizgi): 1, 2, 5, 10, 20, 25, 50."""
    for step in (1, 2, 5, 10, 20, 25, 50):
        if max_value / step <= 6:
            return step
    return 100


def percent_axis(max_percent: float | None = None, **overrides) -> dict:
    """Türkçe yüzde ekseni: değerler 0-100, etiketler %0, %5, ...

    Bindirilmiş eksende Plotly çizgileri birincil eksene hizalayıp %19,35 gibi düzensiz değerler üretebiliyor;
    bu yüzden aralık ve adım açıkça verilir.
    """
    axis = dict(tickprefix="%", ticksuffix="", showgrid=False, tickmode="auto", rangemode="tozero")
    if max_percent is not None:
        top = max(float(max_percent), 1.0)
        step = nice_step(top)
        axis.update(tickmode="linear", tick0=0, range=[0, (int(top // step) + 1) * step], dtick=step)
    axis.update(overrides)
    if "dtick" in overrides:
        axis.update(tickmode="linear", tick0=0)
    return axis


INT_TICKS = ",.0f"  # binlik ayraçlı tam sayı (separators ile '1.000.000')


def show_chart(fig: go.Figure) -> None:
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False, "locale": "tr"})


def empty_state(message: str = "Seçilen filtrelerle sonuç bulunamadı. Tarih aralığını genişletin veya filtreleri azaltın.") -> None:
    st.info(message)
