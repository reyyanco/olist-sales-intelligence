"""Dashboard sayfaları. KPI kartları ve grafikler aynı Filters nesnesiyle aynı reporting fonksiyonlarından beslenir."""

from __future__ import annotations

import logging

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard import data, ui
from dashboard.data import DataError, Filters
from dashboard.filters import date_label, rfm_as_of, sidebar_filters

log = logging.getLogger("dashboard")

# Teslimat eğilim grafiğinde gösterilecek ay için en az ölçülen sipariş sayısı (yalnızca görüntü kuralı).
MIN_ORDERS_FOR_TREND = 30
# fn_monthly_sales büyüme kuralı (sql/190, sql/200): oran takvim ayları arasındadır, çubuklar seçili aralıktır.
GROWTH_NOTE = ("Önceki aya göre büyüme tam takvim ayları üzerinden hesaplanır: tarih filtresi önceki ayı kesse de "
               "o ayın tamamı kullanılır; bu yüzden oran, yandaki kısmi çubukla karşılaştırılamaz. Ay kısmiyse veya "
               "önceki ay veri kapsamı tarafından kesiliyorsa oran hesaplanmaz.")

SEGMENT_LABELS = {
    "champions": "Şampiyonlar",
    "at_risk": "Risk altında",
    "loyal": "Sadık",
    "new_high_value": "Yeni, yüksek değerli",
    "recent": "Yeni / yakın zamanlı",
    "hibernating_high_value": "Uykuda, yüksek değerli",
    "lost": "Kaybedilmiş",
    "needs_attention": "İlgi bekleyen",
}
SEGMENT_RULES = {
    "champions": "R ≥ 4, F ≥ 2, M ≥ 4",
    "at_risk": "F ≥ 2, R ≤ 2",
    "loyal": "F ≥ 2 (diğer)",
    "new_high_value": "F = 1, R ≥ 4, M ≥ 4",
    "recent": "F = 1, R ≥ 4",
    "hibernating_high_value": "F = 1, R ≤ 2, M ≥ 4",
    "lost": "F = 1, R ≤ 2",
    "needs_attention": "diğer (F = 1, R = 3)",
}


def _context(*, states: bool, categories: bool) -> tuple[str | None, Filters] | None:
    """Ortak hazırlık: tazelik, veri kapsamı ve filtreler. Gösterilecek bir şey yoksa None."""
    fresh = data.freshness()
    run_id = fresh.get("run_id")
    cov = data.coverage(run_id)
    if not run_id or not cov.get("order_count"):
        st.warning("Henüz yüklenmiş satış verisi yok. Yükleme için: `.\\scripts\\etl.ps1`")
        return None
    f = sidebar_filters(run_id, cov, states=states, categories=categories)
    if f is None:
        return None
    return run_id, f


def _guard(render):
    """Sayfa gövdesini DataError'a karşı korur: teknik ayrıntı yerine anlaşılır mesaj."""
    def wrapper():
        try:
            render()
        except DataError as exc:
            st.error(exc.user_message)
        except Exception:
            # Beklenmeyen hata: ayrıntı yalnızca sunucu günlüğüne; arayüzde teknik çıktı gösterilmez.
            # (st.stop/st.rerun istisnaları BaseException'dır, burada yakalanmaz.)
            log.exception("Sayfa çizilirken beklenmeyen hata: %s", render.__name__)
            st.error("Bu sayfa gösterilirken beklenmeyen bir hata oluştu. Ayrıntı sunucu günlüğündedir; "
                     "sayfayı yenileyin veya filtreleri değiştirin.")
    wrapper.__name__ = render.__name__
    return wrapper


# --- Genel Bakış ------------------------------------------------------------------------------

@_guard
def overview() -> None:
    st.title("Genel Bakış")
    ctx = _context(states=True, categories=True)
    if ctx is None:
        return
    run_id, f = ctx
    ui.scope_caption([("Tarih", date_label(f)), ("Eyalet", ui.list_or_all(f.states)),
                      ("Kategori", ui.list_or_all(f.categories)), ("Kapsam", "teslim edilmiş siparişler")])

    k = data.overview_kpis(run_id, f)
    if not k["order_count"]:
        ui.empty_state()
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ürün satış tutarı", ui.fmt_brl(k["product_sales"]), border=True,
              help="Kalem fiyatlarının toplamı (kargo hariç). " + ui.CURRENCY_NOTE)
    c2.metric("Sipariş sayısı", ui.fmt_int(k["order_count"]), border=True,
              help="Farklı sipariş sayısı. Kategori filtresinde: seçili kategoride kalemi olan siparişler, bir kez.")
    c3.metric("Müşteri sayısı", ui.fmt_int(k["customer_count"]), border=True,
              help="Farklı kişi (customer_unique_id) sayısı.")
    c4.metric("Ortalama sepet tutarı", ui.fmt_brl(k["avg_basket_value"]), border=True,
              help="Ürün satış tutarı / sipariş sayısı (kargo hariç).")

    m = data.monthly_sales(run_id, f)
    st.subheader("Aylık ürün satış tutarı")
    if m.empty:
        ui.empty_state()
        return
    colors = [ui.TEAL_LIGHT if p else ui.TEAL for p in m["is_partial_month"]]
    hover = [
        f"{ms:%m.%Y}<br>Ürün satış tutarı: {ui.fmt_brl(v)}<br>Sipariş: {ui.fmt_int(o)}"
        f"<br>Önceki aya göre (tam aylar): {ui.growth_text(g, s)}{'<br><i>Kısmi ay</i>' if p else ''}"
        for ms, v, o, g, s, p in zip(m["month_start"], m["product_sales"], m["order_count"], m["growth_rate"],
                                     m["growth_status"], m["is_partial_month"])
    ]
    # Ay etiketleri kategori ekseninde: Plotly etiket sıklığını tarayıcıdaki eksen genişliğine göre seçer
    # (geniş ekranda her ay, dar ekranda daha seyrek) ve sığarsa yatay, sığmazsa dik yazar. Eğik (45°) açı
    # kullanılmaz: eğik paralel etiketlerin aralığını yazı yüksekliği belirler ve 390 px'te etiketler birbirine
    # değiyordu (docs/dashboard.md). Her ayın çubuğu ve bilgi kutusu her genişlikte kalır.
    fig = go.Figure(go.Bar(x=[f"{ms:%m.%Y}" for ms in m["month_start"]], y=m["product_sales"].astype(float),
                           marker_color=colors, hovertext=hover, hoverinfo="text", name="Ürün satış tutarı (BRL)"))
    fig.update_xaxes(type="category", autotickangles=[0, 90])
    fig.update_yaxes(tickformat=ui.INT_TICKS)
    ui.show_chart(ui.style_figure(fig, y_title="Ürün satış tutarı (BRL)"))
    zero_months = [f"{d:%m.%Y}" for d, v, p in zip(m["month_start"], m["product_sales"], m["is_partial_month"]) if v == 0 and not p]
    notes = ["Açık renkli çubuklar kısmi aylardır (seçili aralık veya veri kapsamı ayın tamamını içermiyor).",
             GROWTH_NOTE,
             "Grafik veri kapsamının son ayında biter; tahmini teslim tarihlerinden doğan gelecek aylar gösterilmez."]
    if zero_months:
        notes.append(f"Satış 0 olan aylar ({', '.join(zero_months)}): veri kapsamı içinde, kaynakta bu ayda teslim edilmiş sipariş yok.")
    st.caption(" ".join(notes))


# --- Kategori Analizi ---------------------------------------------------------------------------

@_guard
def categories() -> None:
    st.title("Kategori Analizi")
    ctx = _context(states=True, categories=False)
    if ctx is None:
        return
    run_id, f = ctx
    ui.scope_caption([("Tarih", date_label(f)), ("Eyalet", ui.list_or_all(f.states)),
                      ("Kategori", "tüm kategoriler (bu sayfada filtre yok)")])
    df = data.category_sales(run_id, f)
    if df.empty:
        ui.empty_state()
        return

    total = float(df["product_sales"].sum())
    top = df.iloc[0]
    reach80 = df.loc[df["cumulative_share"] >= 0.8, "sales_rank"].min()
    c1, c2, c3 = st.columns(3)
    c1.metric("Kategori sayısı", ui.fmt_int(len(df)), border=True)
    c2.metric("En çok satan kategori", str(top["category_label"]), border=True,
              help=f"{ui.fmt_brl(top['product_sales'])} · payı {ui.fmt_pct(top['sales_share'])}")
    c3.metric("Satışın %80'ine ulaşılan sıra", ui.fmt_int(reach80) if pd.notna(reach80) else "—", border=True,
              help="Kümülatif payın ilk kez %80'i geçtiği kategori sırası.")

    options = sorted({v for v in (10, 20) if v < len(df)} | {len(df)})
    n = st.segmented_control("Gösterilen kategori", options=options, default=min(20, len(df)),
                             format_func=lambda v: "Tümü" if v == len(df) else f"İlk {v}", key="cat_top_n")
    view = df.head(int(n or min(20, len(df))))
    # Yatay çubuk: kategori adları dar ekranda da okunur. Kümülatif pay üst eksende çizgi.
    fig = go.Figure()
    fig.add_bar(y=view["category_label"], x=view["product_sales"].astype(float), orientation="h", marker_color=ui.TEAL,
                name="Ürün satış tutarı (BRL)",
                hovertext=[f"{c}<br>{ui.fmt_brl(v)}<br>Pay: {ui.fmt_pct(s)}" for c, v, s in
                           zip(view["category_label"], view["product_sales"], view["sales_share"])], hoverinfo="text")
    fig.add_scatter(y=view["category_label"], x=view["cumulative_share"].astype(float) * 100, xaxis="x2",
                    mode="lines+markers", line=dict(color=ui.NAVY, width=2), name="Kümülatif pay",
                    hovertext=[f"{c}<br>Kümülatif pay: {ui.fmt_pct(s)}" for c, s in
                               zip(view["category_label"], view["cumulative_share"])], hoverinfo="text")
    fig.update_layout(
        xaxis=dict(tickformat=ui.INT_TICKS, title_text="Ürün satış tutarı (BRL)", showgrid=True, gridcolor=ui.GRID),
        xaxis2=dict(overlaying="x", side="top", title_text="Kümülatif pay",
                    **ui.percent_axis(range=[0, 100], dtick=20)),
        yaxis=dict(autorange="reversed", automargin=True),
    )
    fig = ui.style_figure(fig, height=160 + 26 * len(view))
    # Gösterge yok: iki eksen başlığı serileri adlandırır (gösterge dar ekranda eksen başlığıyla çakışıyordu).
    fig.update_layout(showlegend=False, margin=dict(l=8, r=8, t=56, b=8))
    ui.show_chart(fig)
    st.caption("Çubuklar: ürün satış tutarı (alt eksen, BRL). Çizgi: kümülatif pay (üst eksen).")
    st.caption(f"Toplam ürün satış tutarı {ui.fmt_brl(total)}. Eşit tutarlarda sıralama kategori adına göredir. "
               "Bir sipariş birden fazla kategoride kalem içerebileceği için kategori sipariş sayılarının toplamı "
               "toplam sipariş sayısını aşabilir.")

    table = pd.DataFrame({
        "Sıra": df["sales_rank"], "Kategori": df["category_label"],
        "Ürün satış tutarı (BRL)": df["product_sales"].map(ui.fmt_decimal),
        "Pay": df["sales_share"].map(ui.fmt_pct), "Kümülatif pay": df["cumulative_share"].map(ui.fmt_pct),
        "Sipariş": df["order_count"].map(ui.fmt_int), "Kalem": df["item_count"].map(ui.fmt_int),
    })
    st.dataframe(table, hide_index=True, width="stretch", height=380)


# --- Müşteri Analizi ---------------------------------------------------------------------------

@_guard
def customers() -> None:
    st.title("Müşteri Analizi")
    ctx = _context(states=False, categories=False)
    if ctx is None:
        return
    run_id, f = ctx
    as_of = rfm_as_of(f)
    ui.scope_caption([("Tekrar satın alma", date_label(f)),
                      ("RFM gözlem tarihi", f"{as_of:%d.%m.%Y} (bitiş günü + 1; o güne kadarki tüm satın almalar)"),
                      ("Eyalet/kategori", "bu sayfada uygulanmaz (müşteri düzeyi)")])

    r = data.repeat_purchase(run_id, f)
    st.subheader("Tekrar satın alma")
    if not r["customer_count"]:
        ui.empty_state()
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Müşteri sayısı", ui.fmt_int(r["customer_count"]), border=True,
              help="Seçili aralıkta en az bir teslim edilmiş siparişi olan kişi (customer_unique_id).")
    c2.metric("Tekrar eden müşteri", ui.fmt_int(r["repeat_customer_count"]), border=True,
              help="Seçili aralıkta en az 2 farklı siparişi olan kişi.")
    c3.metric("Tekrar satın alma oranı", ui.fmt_pct(r["repeat_purchase_rate"], 2), border=True)

    st.subheader("RFM segmentleri")
    seg = data.rfm_segments(run_id, as_of)
    if seg.empty:
        ui.empty_state()
        return
    seg = seg.assign(label=seg["segment"].map(SEGMENT_LABELS).fillna(seg["segment"]))
    fig = go.Figure(go.Bar(
        y=seg["label"], x=seg["customer_count"], orientation="h", marker_color=ui.NAVY,
        hovertext=[f"{l}<br>Müşteri: {ui.fmt_int(c)}<br>Ort. recency: {ui.fmt_decimal(rc, 1)} gün"
                   f"<br>Ort. frequency: {ui.fmt_decimal(fq)}<br>Ort. monetary: {ui.fmt_brl(mo)}"
                   for l, c, rc, fq, mo in zip(seg["label"], seg["customer_count"], seg["avg_recency_days"],
                                                seg["avg_frequency"], seg["avg_monetary"])],
        hoverinfo="text", name="Müşteri"))
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(tickformat=ui.INT_TICKS, title_text="Müşteri sayısı", showgrid=True, gridcolor=ui.GRID)
    ui.show_chart(ui.style_figure(fig, height=380, y_title=None))
    table = pd.DataFrame({
        "Segment": seg["label"], "Kural": seg["segment"].map(SEGMENT_RULES),
        "Müşteri": seg["customer_count"].map(ui.fmt_int),
        "Ort. recency (gün)": seg["avg_recency_days"].map(lambda v: ui.fmt_decimal(v, 1)),
        "Ort. frequency": seg["avg_frequency"].map(ui.fmt_decimal),
        "Ort. monetary (BRL)": seg["avg_monetary"].map(ui.fmt_decimal),
        "Toplam monetary (BRL)": seg["total_monetary"].map(ui.fmt_decimal),
    })
    st.dataframe(table, hide_index=True, width="stretch")
    st.caption("R ve M puanları müşterilerin kümülatif dağılımına göre beşli dilimdir (eşit değerler aynı puanı alır); "
               "F puanı sipariş sayısıdır (5+ = 5). Recency'de düşük, frequency ve monetary'de yüksek değer daha iyidir. "
               "Monetary = ürün satış tutarı (kargo hariç). Ayrıntı: docs/reporting.md")


# --- Teslimat Performansı -----------------------------------------------------------------------

@_guard
def delivery() -> None:
    st.title("Teslimat Performansı")
    ctx = _context(states=True, categories=False)
    if ctx is None:
        return
    run_id, f = ctx
    ui.scope_caption([("Tarih", date_label(f)), ("Eyalet", ui.list_or_all(f.states)),
                      ("Kategori", "uygulanmaz (sipariş düzeyi)"), ("Kapsam", "teslim edilmiş siparişler")])
    reg = data.delivery_by_region(run_id, f)
    total = reg[reg["grouping_level"] == "total"]
    if total.empty or not total.iloc[0]["order_count"]:
        ui.empty_state()
        return
    t = total.iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ortalama teslimat süresi", f"{ui.fmt_decimal(t['avg_delivery_days'])} gün", border=True,
              help="Satın almadan müşteriye teslime geçen süre; teslim zamanı boş siparişler hariç.")
    c2.metric("Geç teslimat oranı", ui.fmt_pct(t["late_delivery_rate"], 2), border=True,
              help="Teslim günü > tahmini teslim günü olan siparişler / teslim zamanı ölçülen siparişler.")
    c3.metric("Ölçülen sipariş", ui.fmt_int(t["delivery_measured_orders"]), border=True)
    c4.metric("Teslim zamanı boş", ui.fmt_int(int(t["order_count"]) - int(t["delivery_measured_orders"])), border=True,
              help="Durumu 'delivered' ama teslim zamanı kaynakta boş; süre ve orandan dışlanır, hata sayılmaz.")

    left, right = st.columns(2)
    with left:
        st.subheader("Bölgelere göre")
        regions = reg[reg["grouping_level"] == "region"].sort_values("late_delivery_rate", ascending=False)
        # Yatay çubuk: bölge adları dar ekranda üst üste binmez.
        rates = regions["late_delivery_rate"].astype(float) * 100
        fig = go.Figure(go.Bar(
            y=regions["customer_region"], x=rates, orientation="h", marker_color=ui.ORANGE,
            hovertext=[f"{r}<br>Geç teslimat: {ui.fmt_pct(v, 2)}<br>Ort. süre: {ui.fmt_decimal(d)} gün<br>Sipariş: {ui.fmt_int(o)}"
                       for r, v, d, o in zip(regions["customer_region"], regions["late_delivery_rate"],
                                             regions["avg_delivery_days"], regions["order_count"])],
            hoverinfo="text", name="Geç teslimat oranı"))
        fig.update_layout(xaxis=dict(title_text="Geç teslimat oranı",
                                     **ui.percent_axis(rates.max() if len(rates) else None, showgrid=True, gridcolor=ui.GRID)),
                          yaxis=dict(autorange="reversed", automargin=True))
        ui.show_chart(ui.style_figure(fig, height=330))
    with right:
        st.subheader("Aylık eğilim")
        mon = data.delivery_monthly(run_id, f)
        # Çok az ölçülen siparişi olan aylar (ör. 2016 sonu) ekseni sıkıştırıp eğilimi okunmaz kılar;
        # bu aylar yalnızca BU grafikte gösterilmez (KPI'lar ve tablolar değişmez) ve altta listelenir.
        small = mon["delivery_measured_orders"] < MIN_ORDERS_FOR_TREND
        shown, hidden = mon[~small], mon[small]
        fig = go.Figure()
        fig.add_scatter(x=shown["month_start"], y=shown["avg_delivery_days"].astype(float), mode="lines+markers",
                        line=dict(color=ui.NAVY), name="Ort. teslimat süresi (gün)",
                        hovertext=[f"{d:%m.%Y}<br>Ort. süre: {ui.fmt_decimal(v)} gün<br>Ölçülen sipariş: {ui.fmt_int(n)}"
                                   for d, v, n in zip(shown["month_start"], shown["avg_delivery_days"], shown["delivery_measured_orders"])],
                        hoverinfo="text")
        fig.add_scatter(x=shown["month_start"], y=shown["late_delivery_rate"].astype(float) * 100, mode="lines+markers",
                        line=dict(color=ui.ORANGE), name="Geç teslimat oranı", yaxis="y2",
                        hovertext=[f"{d:%m.%Y}<br>Geç teslimat: {ui.fmt_pct(v, 2)}"
                                   for d, v in zip(shown["month_start"], shown["late_delivery_rate"])],
                        hoverinfo="text")
        late_max = float(shown["late_delivery_rate"].astype(float).max() * 100) if not shown.empty else None
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", title_text="Geç teslimat oranı",
                                      **ui.percent_axis(late_max)))
        fig.update_layout(yaxis=dict(rangemode="tozero"))
        fig.update_xaxes(tickformat="%m.%Y")
        ui.show_chart(ui.style_figure(fig, height=330, y_title="Ortalama süre (gün)"))
        if not hidden.empty:
            listed = ", ".join(f"{d:%m.%Y} ({ui.fmt_int(n)})" for d, n in zip(hidden["month_start"], hidden["delivery_measured_orders"]))
            st.caption(f"{MIN_ORDERS_FOR_TREND}'dan az ölçülen siparişi olan aylar bu grafikte gösterilmez: {listed}. "
                       "Bu aylar KPI'lara ve tablolara dahildir.")

    st.subheader("Eyaletlere göre")
    states = reg[reg["grouping_level"] == "state"].sort_values(["customer_region", "customer_state"])
    table = pd.DataFrame({
        "Bölge": states["customer_region"], "Eyalet": states["customer_state"],
        "Sipariş": states["order_count"].map(ui.fmt_int),
        "Ölçülen": states["delivery_measured_orders"].map(ui.fmt_int),
        "Ort. süre (gün)": states["avg_delivery_days"].map(ui.fmt_decimal),
        "Geç teslimat": states["late_delivery_rate"].map(lambda v: ui.fmt_pct(v, 2)),
    })
    st.dataframe(table, hide_index=True, width="stretch", height=360)
    st.caption("Bölge: müşteri eyaletinin IBGE coğrafi bölgesi. Aylar satın alma ayına göredir.")
