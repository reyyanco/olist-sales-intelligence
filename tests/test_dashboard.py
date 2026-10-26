"""Dashboard testleri (sentetik veri: tests/fixtures/olist_reporting_sample).

KPI'lar iki bağımsız yoldan karşılaştırılır: (1) uygulamanın gösterdiği değer, (2) dw tablolarına doğrudan,
reporting fonksiyonlarını KULLANMADAN yazılmış SQL (tarih filtresi purchase_ts üzerinden).
Elle hesaplanan değerler (teslim edilmiş siparişler; bkz. tests/test_reporting.py başlığı):
  filtresiz: 540,00 BRL, 5 sipariş, 3 müşteri, sepet 108,00
  kategori health_beauty+sports_leisure: O1(100+50) O2(100) O6(50) = 300,00; 3 sipariş (O1 bir kez); 2 müşteri; sepet 100,00
  eyalet RJ: O2(100) O6(50) = 150,00; 2 sipariş; 1 müşteri (u2); sepet 75,00
  tarih 2017-03-01..2017-04-30: O4(200) O6(50) = 250,00; 2 sipariş; 2 müşteri; sepet 125,00
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import replace
from decimal import Decimal

import psycopg2
import pytest
import streamlit as st
from sqlalchemy import text
from streamlit.testing.v1 import AppTest

from dashboard import ui
from etl.dashboard_role import READER_ROLE, ensure_dashboard_role
from etl.pipeline import run_pipeline
from tests.conftest import PROJECT_ROOT, REPORTING_SAMPLE_DIR

APP = str(PROJECT_ROOT / "dashboard" / "app.py")
PAGES = ["page_overview.py", "page_categories.py", "page_customers.py", "page_delivery.py"]
SECRET = "should-never-appear-9f2c"


@pytest.fixture(scope="module")
def dash_db(pipeline_engine):
    assert run_pipeline(pipeline_engine, REPORTING_SAMPLE_DIR).status == "succeeded"
    return pipeline_engine


@pytest.fixture
def app_env(dash_db, monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", dash_db.url.database)
    st.cache_data.clear()
    st.cache_resource.clear()
    yield
    st.cache_data.clear()
    st.cache_resource.clear()


def run_app(page: str = "page_overview.py", **widgets) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    if page != "page_overview.py":
        at.switch_page(page).run()
    for key, value in widgets.items():
        widget = at.multiselect(key=key) if key in ("w_states", "w_categories") else at.date_input(key=key)
        widget.set_value(value)
        at.run()
    return at


def kpis(at: AppTest) -> dict:
    return {m.label: m.value for m in at.metric}


def direct_sql(engine, d_from, d_to, states=None, categories=None) -> dict:
    """Bağımsız hesap: dw tabloları, purchase_ts tarih filtresi, reporting fonksiyonu yok."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT sum(s.price) AS product_sales, count(DISTINCT s.order_id) AS orders,
                   count(DISTINCT c.customer_unique_id) AS customers
            FROM dw.fact_sales s
            JOIN dw.fact_orders o ON o.order_id = s.order_id
            JOIN dw.dim_customer c ON c.customer_id = o.customer_id
            JOIN dw.dim_product p ON p.product_id = s.product_id
            WHERE o.order_status = 'delivered'
              AND o.purchase_ts >= :f AND o.purchase_ts < CAST(:t AS date) + 1
              AND (CAST(:states AS text[]) IS NULL OR c.state = ANY (CAST(:states AS text[])))
              AND (CAST(:cats AS text[]) IS NULL OR p.category_label = ANY (CAST(:cats AS text[])))
        """), {"f": d_from, "t": d_to, "states": states, "cats": categories}).mappings().one()
    basket = (row["product_sales"] / row["orders"]).quantize(Decimal("0.01")) if row["orders"] else None
    return {"Ürün satış tutarı": ui.fmt_brl(row["product_sales"]), "Sipariş sayısı": ui.fmt_int(row["orders"]),
            "Müşteri sayısı": ui.fmt_int(row["customers"]), "Ortalama sepet tutarı": ui.fmt_brl(basket)}


COVERAGE = (dt.date(2017, 1, 5), dt.date(2017, 5, 10))


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_without_errors(app_env, page):
    at = run_app(page)
    assert not at.exception and not at.error and not at.warning
    assert at.title and at.metric


@pytest.mark.parametrize("widgets, expected", [
    ({}, {"Ürün satış tutarı": "540,00 BRL", "Sipariş sayısı": "5", "Müşteri sayısı": "3", "Ortalama sepet tutarı": "108,00 BRL"}),
    ({"w_categories": ["health_beauty", "sports_leisure"]},
     {"Ürün satış tutarı": "300,00 BRL", "Sipariş sayısı": "3", "Müşteri sayısı": "2", "Ortalama sepet tutarı": "100,00 BRL"}),
    ({"w_states": ["RJ"]},
     {"Ürün satış tutarı": "150,00 BRL", "Sipariş sayısı": "2", "Müşteri sayısı": "1", "Ortalama sepet tutarı": "75,00 BRL"}),
    ({"w_dates": (dt.date(2017, 3, 1), dt.date(2017, 4, 30))},
     {"Ürün satış tutarı": "250,00 BRL", "Sipariş sayısı": "2", "Müşteri sayısı": "2", "Ortalama sepet tutarı": "125,00 BRL"}),
])
def test_overview_kpis_match_hand_values_and_direct_sql(app_env, dash_db, widgets, expected):
    at = run_app(**widgets)
    assert kpis(at) == expected
    d_from, d_to = widgets.get("w_dates", COVERAGE)
    assert kpis(at) == direct_sql(dash_db, d_from, d_to, widgets.get("w_states"), widgets.get("w_categories"))


def test_default_date_range_is_data_coverage(app_env):
    at = run_app()
    assert at.date_input(key="w_dates").value == COVERAGE  # ilk ve son TESLİM EDİLMİŞ satın alma günü
    assert "05.01.2017 – 10.05.2017" in " ".join(m.value for m in at.markdown)


def test_monthly_series_stops_at_coverage_and_marks_partial_months(dash_db):
    with dash_db.connect() as conn:
        rows = conn.execute(text("SELECT month_start, product_sales, is_partial_month, growth_status "
                                 "FROM reporting.fn_monthly_sales('2017-01-05', '2017-05-10')")).all()
    # Haziran (yalnızca O7'nin tahmini teslim tarihi) gösterilmez; Şubat kapsam içinde gerçek sıfır.
    # Ocak ve Mayıs kapsam tarafından kesilen kısmi aylar: büyüme hesaplanmaz (sql/190).
    # Şubat'ın önceki ayı (Ocak) kapsam tarafından kesildiği için Şubat'ın büyümesi de hesaplanmaz (sql/200).
    assert [(str(m), str(v), p, s) for m, v, p, s in rows] == [
        ("2017-01-01", "250.00", True, "partial_month"),
        ("2017-02-01", "0.00", False, "previous_month_partial"),
        ("2017-03-01", "200.00", False, "previous_month_zero"),
        ("2017-04-01", "50.00", False, "computed"),
        ("2017-05-01", "40.00", True, "partial_month"),
    ]


def test_monthly_series_uses_same_date_scope_as_kpis(dash_db):
    """Ay ortasında başlayıp biten aralık (Aşama 8'de gerçek veride bulunan hata).
    10.01.2017–05.03.2017: O1 (05.01) DIŞARIDA, O2 (20.01) 100, O4 (03.03) 200 -> KPI 300,00 / 2 sipariş.
    Eski fonksiyon Ocak'ı tam ay (250) gösterip toplamı 450 yapıyordu."""
    with dash_db.connect() as conn:
        kpi = conn.execute(text("SELECT product_sales, order_count FROM "
                                "reporting.fn_overview_kpis('2017-01-10', '2017-03-05')")).one()
        rows = conn.execute(text("SELECT month_start, product_sales, order_count, prev_product_sales, growth_rate, "
                                 "growth_status, is_partial_month FROM reporting.fn_monthly_sales('2017-01-10', '2017-03-05')")).all()
    assert tuple(kpi) == (Decimal("300.00"), 2)
    assert sum(r.product_sales for r in rows) == kpi.product_sales
    assert sum(r.order_count for r in rows) == kpi.order_count
    assert [(str(r.month_start), str(r.product_sales), r.is_partial_month, r.growth_status,
             None if r.growth_rate is None else str(r.growth_rate)) for r in rows] == [
        ("2017-01-01", "100.00", True, "partial_month", None),
        # Ocak veri kapsamı tarafından da kesiliyor (ilk satın alma 05.01): oran hesaplanmaz (sql/200)
        ("2017-02-01", "0.00", False, "previous_month_partial", None),
        ("2017-03-01", "200.00", True, "partial_month", None),
    ]
    assert str(rows[1].prev_product_sales) == "250.00"


def test_monthly_growth_uses_full_previous_month_when_cut_only_by_filter(dash_db):
    """10.03.2017–05.05.2017: Mart yalnızca FİLTRE ile kesiliyor (veri kapsamı Mart'ı tamamen içerir).
    Gösterilen: Mart 0 (O4 03.03 dışarıda), Nisan 50 (O6), Mayıs 0 (O5 10.05 dışarıda) -> KPI 50,00 / 1.
    Nisan büyümesi tam ay değerlerinden: (50 - 200) / 200 = -0,7500."""
    with dash_db.connect() as conn:
        kpi = conn.execute(text("SELECT product_sales, order_count FROM "
                                "reporting.fn_overview_kpis('2017-03-10', '2017-05-05')")).one()
        rows = conn.execute(text("SELECT month_start, product_sales, prev_product_sales, growth_rate, growth_status, "
                                 "is_partial_month FROM reporting.fn_monthly_sales('2017-03-10', '2017-05-05')")).all()
    assert tuple(kpi) == (Decimal("50.00"), 1)
    assert sum(r.product_sales for r in rows) == kpi.product_sales
    assert [(str(r.month_start), str(r.product_sales), r.is_partial_month, r.growth_status,
             None if r.growth_rate is None else str(r.growth_rate)) for r in rows] == [
        ("2017-03-01", "0.00", True, "partial_month", None),
        ("2017-04-01", "50.00", False, "computed", "-0.7500"),
        ("2017-05-01", "0.00", True, "partial_month", None),
    ]
    assert str(rows[1].prev_product_sales) == "200.00"


def test_percent_format_puts_sign_before_percent():
    from dashboard.ui import fmt_pct
    assert fmt_pct(-0.75) == "-%75,0"
    assert fmt_pct(0.0677) == "%6,8"
    assert fmt_pct(-0.0001) == "%0,0"   # yuvarlanınca sıfır: "-%0,0" yazılmaz
    assert fmt_pct(None) == "—"


def test_overview_explains_growth_base_when_previous_month_cut_by_filter(app_env):
    """Aynı aralık arayüzde: Mart çubuğu 0 (filtreli), Nisan oranı tam Mart'a (200) göre -%75,0.
    Kullanıcı oranı kısmi çubukla karşılaştırmasın diye bilgi kutusu ve açıklama bunu söylemeli."""
    import json

    from dashboard.views import GROWTH_NOTE
    at = run_app(w_dates=(dt.date(2017, 3, 10), dt.date(2017, 5, 5)))
    assert not at.exception and not at.error
    assert any(GROWTH_NOTE in c.value for c in at.caption)
    spec = json.loads(at.get("plotly_chart")[0].proto.spec)
    hover = spec["data"][0]["hovertext"]
    assert "Önceki aya göre (tam aylar): -%75,0" in hover[1]       # Nisan
    assert "hesaplanmaz (kısmi ay)" in hover[0] and "Kısmi ay" in hover[0]  # Mart


def test_category_filter_does_not_duplicate_orders(dash_db):
    with dash_db.connect() as conn:
        k = conn.execute(text("SELECT * FROM reporting.fn_overview_kpis('2017-01-01', '2017-01-31', NULL, "
                              "ARRAY['health_beauty', 'sports_leisure'])")).mappings().one()
    # O1'in iki kalemi iki farklı seçili kategoride; O2 sports_leisure -> 2 sipariş, 3 kalem
    assert (k["order_count"], k["item_count"], k["product_sales"]) == (2, 3, Decimal("250.00"))


def test_empty_result_message(app_env):
    at = run_app(w_dates=(dt.date(2017, 2, 1), dt.date(2017, 2, 28)))  # yalnızca iptal sipariş
    assert not at.exception and not at.error
    assert any("sonuç bulunamadı" in i.value for i in at.info)
    assert not at.metric


def test_user_input_is_parameterized(dash_db):
    hostile = ["SP'); DROP TABLE dw.fact_orders; --"]
    with dash_db.connect() as conn:
        k = conn.execute(text("SELECT * FROM reporting.fn_overview_kpis('2017-01-01', '2017-12-31', :s, NULL)"),
                         {"s": hostile}).mappings().one()
        still_there = conn.execute(text("SELECT count(*) FROM dw.fact_orders")).scalar()
    assert k["order_count"] == 0 and still_there == 7


def test_not_loaded_state(empty_engine, monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", empty_engine.url.database)
    st.cache_data.clear()
    st.cache_resource.clear()
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert any("Henüz yüklenmiş satış verisi yok" in w.value for w in at.warning)


def test_connection_error_shows_friendly_message_without_secrets(app_env, monkeypatch):
    monkeypatch.setenv("POSTGRES_PORT", "1")  # kimse dinlemiyor
    monkeypatch.setenv("POSTGRES_PASSWORD", SECRET)
    st.cache_resource.clear()
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert [e.value for e in at.error] == [
        "Veritabanına bağlanılamadı. Veritabanının çalıştığından emin olun ve sayfayı yenileyin."]
    rendered = " ".join(str(el.value) for el in at.main if hasattr(el, "value")) + " ".join(
        str(el.value) for el in at.sidebar if hasattr(el, "value"))
    assert SECRET not in rendered and "Traceback" not in rendered and "psycopg2" not in rendered


def test_unexpected_error_shows_friendly_message(app_env):
    """Veri katmanında beklenmeyen bir hata: Türkçe mesaj, istisna metni ve iz görünmez."""
    script = f"""
import sys
sys.path.insert(0, {str(PROJECT_ROOT)!r})
from dashboard import data, views
def boom(*args, **kwargs):
    raise ValueError("internal-detail-7a1")
data.category_sales = boom
views.categories()
"""
    at = AppTest.from_string(script, default_timeout=60).run()
    assert not at.exception
    assert [e.value for e in at.error] == [
        "Bu sayfa gösterilirken beklenmeyen bir hata oluştu. Ayrıntı sunucu günlüğündedir; "
        "sayfayı yenileyin veya filtreleri değiştirin."]
    rendered = " ".join(str(el.value) for el in at.main if hasattr(el, "value"))
    assert "internal-detail-7a1" not in rendered and "ValueError" not in rendered


# --- Veritabanı yetkileri -----------------------------------------------------------------------

@pytest.fixture
def reader_login(dash_db, test_settings):
    """Geçici giriş rolü (yalnızca olist_reporting_reader üyesi); test sonunda silinir."""
    name, password = f"dash_{uuid.uuid4().hex[:8]}_test", uuid.uuid4().hex
    ensure_dashboard_role(dash_db, name, password)
    conn = psycopg2.connect(host=test_settings.host, port=test_settings.port, user=name, password=password,
                            dbname=dash_db.url.database)
    conn.autocommit = True
    yield conn
    conn.close()
    with dash_db.begin() as c:
        c.execute(text(f'DROP OWNED BY "{name}"'))
        c.execute(text(f'DROP ROLE "{name}"'))


def _fails(conn, sql: str) -> str:
    with conn.cursor() as cur:
        try:
            cur.execute(sql)
        except psycopg2.Error as exc:
            return exc.pgcode
    return "OK"


def test_dashboard_role_can_read_reporting_only(reader_login):
    with reader_login.cursor() as cur:
        cur.execute("SELECT order_count FROM reporting.fn_overview_kpis('2017-01-01', '2017-12-31', NULL, NULL)")
        assert cur.fetchone()[0] == 5
        cur.execute("SHOW default_transaction_read_only")
        assert cur.fetchone()[0] == "on"
        cur.execute("SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = current_user")
        assert cur.fetchone() == (False, False, False)
    assert _fails(reader_login, "SELECT count(*) FROM dw.fact_orders") == "42501"          # yetki yok
    assert _fails(reader_login, "SELECT count(*) FROM meta.etl_runs") == "42501"
    assert _fails(reader_login, "SELECT count(*) FROM staging.orders") == "42501"
    assert _fails(reader_login, "CALL reporting.sp_refresh_reports()") == "42501"
    assert _fails(reader_login, "CALL reporting.sp_load_monthly_summary(2017)") == "42501"
    assert _fails(reader_login, "SELECT reporting.refresh_report_objects()") == "42501"
    assert _fails(reader_login, "DELETE FROM reporting.monthly_summary") in {"42501", "25006"}


def test_ensure_dashboard_role_is_idempotent(dash_db):
    name = f"dash_{uuid.uuid4().hex[:8]}_test"
    try:
        assert ensure_dashboard_role(dash_db, name, "p1") is True
        assert ensure_dashboard_role(dash_db, name, "p2") is False
        with dash_db.connect() as conn:
            member = conn.execute(text("SELECT pg_has_role(:n, :r, 'MEMBER')"), {"n": name, "r": READER_ROLE}).scalar()
        assert member is True
    finally:
        with dash_db.begin() as c:
            c.execute(text(f'DROP ROLE IF EXISTS "{name}"'))
