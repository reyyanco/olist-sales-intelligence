"""Raporlama analizleri ve rutinleri. Beklenen sonuçlar tests/fixtures/olist_reporting_sample
CSV dosyalarından ELLE hesaplanmıştır (sentetik veri).

Siparişler (S = satış kapsamı, delivered):
  O1 S u1 2017-01-05  ürün 100+50 (health_beauty, sports_leisure), kargo 15, ödeme 100+65 (2 ödeme), 5,00 gün, zamanında
  O2 S u2 2017-01-20  ürün 100 (sports_leisure), kargo 8,  ödeme 108, 16,00 gün, GEÇ (02-05 > 02-01)
  O3 - u3 2017-02-10  canceled (Şubat'ta satış yok)
  O4 S u1 2017-03-03  ürün 200 (pc_gamer, çevirisiz), kargo 20, ödeme 220, 7,50 gün, tahmini günle aynı -> geç değil
  O6 S u2 2017-04-02  ürün 50 (health_beauty), kargo 5, ödeme 55, 10,00 gün, GEÇ (04-12 > 04-10)
  O5 S u4 2017-05-10  ürün 40 (kategorisiz), kargo 4, ödeme 44, teslim zamanı BOŞ
  O7 - u5 2017-04-28  shipped (kapsam dışı); tahmini teslim 2017-06-15 -> dim_date Haziran'ı kapsar
"""

from __future__ import annotations

from decimal import Decimal as D

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from etl.pipeline import run_pipeline
from tests.conftest import REPORTING_SAMPLE_DIR

U1, U2, U4 = ("d" + str(n).zfill(31) for n in (1, 2, 4))


@pytest.fixture(scope="module")
def reporting_db(pipeline_engine):
    result = run_pipeline(pipeline_engine, REPORTING_SAMPLE_DIR)
    assert result.status == "succeeded"
    return pipeline_engine


def rows(engine, sql, **params):
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings()]


def autocommit(engine):
    return engine.execution_options(isolation_level="AUTOCOMMIT")


# --- Ortak metrikler -------------------------------------------------------------------------

def test_kpis_match_hand_calculation(reporting_db):
    k = rows(reporting_db, "SELECT * FROM reporting.v_sales_kpis")[0]
    assert (k["order_count"], k["customer_count"], k["item_count"]) == (5, 3, 6)
    assert (k["product_sales"], k["freight_amount"], k["payment_amount"]) == (D("540.00"), D("52.00"), D("592.00"))
    assert k["avg_basket_value"] == D("108.00")
    assert (k["delivery_measured_orders"], k["delivery_unmeasured_orders"]) == (4, 1)
    assert k["avg_delivery_days"] == D("9.63")  # 38,50 / 4 = 9,625
    assert (k["late_orders"], k["late_delivery_rate"]) == (2, D("0.5000"))
    assert (k["repeat_customer_count"], k["repeat_purchase_rate"]) == (2, D("0.6667"))


# --- Aylık satış ve büyüme --------------------------------------------------------------------

# Satış gözlem aralığı = ilk/son delivered satın alma: 2017-01-05 .. 2017-05-10 (sql/200).
# Ocak ve Mayıs kısmi; Şubat aralık içinde GERÇEK sıfır; Haziran yalnızca O7'nin tahmini teslim tarihi
# nedeniyle dim_date'te var -> gözlem dışı, aylık raporlarda yok.
EXPECTED_MONTHS = [
    # month, orders, customers, items, product, freight, payment, basket, prev, change, growth, status,
    # is_partial, observed_from, observed_to
    ("2017-01-01", 2, 2, 3, "250.00", "23.00", "273.00", "125.00", None, None, None, "partial_month",
     True, "2017-01-05", "2017-01-31"),
    ("2017-02-01", 0, 0, 0, "0.00", "0.00", "0.00", None, "250.00", "-250.00", None, "previous_month_partial",
     False, "2017-02-01", "2017-02-28"),
    ("2017-03-01", 1, 1, 1, "200.00", "20.00", "220.00", "200.00", "0.00", "200.00", None, "previous_month_zero",
     False, "2017-03-01", "2017-03-31"),
    ("2017-04-01", 1, 1, 1, "50.00", "5.00", "55.00", "50.00", "200.00", "-150.00", "-0.7500", "computed",
     False, "2017-04-01", "2017-04-30"),
    ("2017-05-01", 1, 1, 1, "40.00", "4.00", "44.00", "40.00", "50.00", "-10.00", None, "partial_month",
     True, "2017-05-01", "2017-05-10"),
]


def _as_tuple(r):
    dec = lambda v: None if v is None else str(v)  # noqa: E731
    return (str(r["month_start"]), r["order_count"], r["customer_count"], r["item_count"], dec(r["product_sales"]),
            dec(r["freight_amount"]), dec(r["payment_amount"]), dec(r["avg_basket_value"]), dec(r["prev_product_sales"]),
            dec(r["product_sales_change"]), dec(r["growth_rate"]), r["growth_status"],
            r["is_partial_month"], str(r["observed_from"]), str(r["observed_to"]))


def test_monthly_growth_limited_to_observation_window(reporting_db):
    got = [_as_tuple(r) for r in rows(reporting_db, "SELECT * FROM reporting.v_monthly_sales_growth ORDER BY month_start")]
    assert got == EXPECTED_MONTHS


def test_observation_months_separate_real_zero_from_unobserved(reporting_db):
    got = [(str(r["month_start"]), r["observation_status"], r["observed_from"] and str(r["observed_from"]),
            r["observed_to"] and str(r["observed_to"]))
           for r in rows(reporting_db, "SELECT * FROM reporting.v_sales_observation_months ORDER BY month_start")]
    assert got == [
        ("2017-01-01", "partial", "2017-01-05", "2017-01-31"),
        ("2017-02-01", "observed", "2017-02-01", "2017-02-28"),   # satış yok ama gözlendi: gerçek sıfır
        ("2017-03-01", "observed", "2017-03-01", "2017-03-31"),
        ("2017-04-01", "observed", "2017-04-01", "2017-04-30"),
        ("2017-05-01", "partial", "2017-05-01", "2017-05-10"),
        ("2017-06-01", "not_observed", None, None),
    ]
    # Tarih boyutu teslimat için gereken kapsamı korur (O7 tahmini teslim 2017-06-15)
    assert rows(reporting_db, "SELECT max(full_date) AS d FROM dw.dim_date")[0]["d"].isoformat() == "2017-06-15"


def test_multi_payment_order_counted_once_in_month(reporting_db):
    jan = rows(reporting_db, "SELECT * FROM reporting.v_monthly_sales_growth WHERE month_start = '2017-01-01'")[0]
    # O1 iki ödeme (100 + 65) + O2 108; ödeme satırları ürün tutarını ve sipariş sayısını çoğaltmaz
    assert (jan["order_count"], jan["product_sales"], jan["payment_amount"]) == (2, D("250.00"), D("273.00"))


# --- sp_load_monthly_summary ------------------------------------------------------------------

def test_load_monthly_summary_twice_does_not_duplicate(reporting_db):
    with autocommit(reporting_db).connect() as conn:
        conn.execute(text("CALL reporting.sp_load_monthly_summary(2017)"))
        conn.execute(text("CALL reporting.sp_load_monthly_summary(2017)"))
    with reporting_db.begin() as conn:  # aynı işlem içinde iki çağrı da güvenli
        conn.execute(text("CALL reporting.sp_load_monthly_summary(2017)"))
        conn.execute(text("CALL reporting.sp_load_monthly_summary(2017)"))
    got = [_as_tuple(r) for r in rows(reporting_db, "SELECT * FROM reporting.monthly_summary ORDER BY month_start")]
    assert got == EXPECTED_MONTHS


def test_load_monthly_summary_rejects_year_outside_dim_date(reporting_db):
    before = rows(reporting_db, "SELECT count(*) AS n FROM reporting.monthly_summary")[0]["n"]
    with pytest.raises(DBAPIError, match="2016 yılı tarih boyutunda"):
        with reporting_db.begin() as conn:
            conn.execute(text("CALL reporting.sp_load_monthly_summary(2016)"))
    assert rows(reporting_db, "SELECT count(*) AS n FROM reporting.monthly_summary")[0]["n"] == before == 5


# --- Kategori satışları ---------------------------------------------------------------------

def test_category_cumulative_share_is_deterministic_on_ties(reporting_db):
    got = [
        (r["sales_rank"], r["category_label"], r["item_count"], r["order_count"], str(r["product_sales"]),
         str(r["sales_share"]), str(r["cumulative_sales"]), str(r["cumulative_share"]))
        for r in rows(reporting_db, "SELECT * FROM reporting.mv_category_sales ORDER BY sales_rank")
    ]
    assert got == [
        (1, "pc_gamer", 1, 1, "200.00", "0.3704", "200.00", "0.3704"),
        # 150 = 150: eşitlikte category_label artan; ROWS çerçevesi sayesinde kümülatif 350 ve 500 (RANGE olsaydı ikisi de 500)
        (2, "health_beauty", 2, 2, "150.00", "0.2778", "350.00", "0.6481"),
        (3, "sports_leisure", 2, 2, "150.00", "0.2778", "500.00", "0.9259"),
        (4, "uncategorized", 1, 1, "40.00", "0.0741", "540.00", "1.0000"),
    ]


# --- Teslimat performansı ---------------------------------------------------------------------

def test_delivery_rollup_and_zero_denominator(reporting_db):
    got = [
        (r["grouping_level"], r["purchase_month"] and str(r["purchase_month"]), r["order_count"],
         r["delivery_measured_orders"], r["delivery_unmeasured_orders"],
         None if r["avg_delivery_days"] is None else str(r["avg_delivery_days"]), r["late_orders"],
         None if r["late_delivery_rate"] is None else str(r["late_delivery_rate"]),
         (r["days_0_7"], r["days_7_14"], r["days_14_30"], r["days_over_30"]))
        for r in rows(reporting_db, "SELECT * FROM reporting.v_delivery_performance "
                                    "ORDER BY purchase_year NULLS LAST, purchase_month NULLS LAST")
    ]
    assert got == [
        ("month", "2017-01-01", 2, 2, 0, "10.50", 1, "0.5000", (1, 0, 1, 0)),
        ("month", "2017-03-01", 1, 1, 0, "7.50", 0, "0.0000", (0, 1, 0, 0)),
        ("month", "2017-04-01", 1, 1, 0, "10.00", 1, "1.0000", (0, 1, 0, 0)),
        # Mayıs: tek sipariş teslim zamanı boş -> payda 0, oran ve ortalama NULL
        ("month", "2017-05-01", 1, 0, 1, None, 0, None, (0, 0, 0, 0)),
        ("year", None, 5, 4, 1, "9.63", 2, "0.5000", (1, 2, 1, 0)),
        ("total", None, 5, 4, 1, "9.63", 2, "0.5000", (1, 2, 1, 0)),
    ]


# --- Tekrar satın alma ----------------------------------------------------------------------

def test_repeat_purchase_by_unique_customer(reporting_db):
    got = [(r["grouping_level"], r["cohort_month"] and str(r["cohort_month"]), r["customer_count"],
            r["repeat_customer_count"], str(r["repeat_purchase_rate"]))
           for r in rows(reporting_db, "SELECT * FROM reporting.v_repeat_purchase ORDER BY cohort_month NULLS LAST")]
    # u1 (c1, c2) ve u2 (c3, c6) farklı customer_id'lerle tekrar aldı; u4 bir kez; u3 yalnızca iptal (sayılmaz)
    assert got == [
        ("cohort", "2017-01-01", 2, 2, "1.0000"),
        ("cohort", "2017-05-01", 1, 0, "0.0000"),
        ("total", None, 3, 2, "0.6667"),
    ]


# --- RFM --------------------------------------------------------------------------------------

def rfm(engine, as_of):
    return {
        r["customer_unique_id"]: (r["recency_days"], r["frequency"], str(r["monetary"]), r["rfm_code"], r["segment"])
        for r in rows(engine, "SELECT * FROM reporting.fn_customer_rfm(CAST(:d AS date))", d=as_of)
    }


def test_rfm_at_observation_date(reporting_db):
    obs = rows(reporting_db, "SELECT * FROM reporting.v_rfm_observation")[0]
    assert str(obs["observation_date"]) == "2017-05-11"
    assert rfm(reporting_db, "2017-05-11") == {
        # frequency = farklı sipariş (u1'in O1 siparişi 2 kalemli ama 1 sipariş)
        U1: (69, 2, "350.00", "125", "at_risk"),
        U2: (39, 2, "150.00", "224", "at_risk"),
        U4: (1, 1, "40.00", "412", "recent"),
    }


def test_rfm_excludes_purchases_on_or_after_as_of(reporting_db):
    # O4 2017-03-03 08:00: as_of 2017-03-04 -> dahil; as_of 2017-03-03 -> dışarıda (gözlem günü başı)
    assert rfm(reporting_db, "2017-03-04") == {
        U1: (1, 2, "350.00", "325", "loyal"),
        U2: (43, 1, "100.00", "113", "lost"),
    }
    assert rfm(reporting_db, "2017-03-03") == {
        U1: (57, 1, "150.00", "115", "hibernating_high_value"),
        U2: (42, 1, "100.00", "313", "needs_attention"),
    }
    assert rfm(reporting_db, "2016-12-31") == {}


def test_rfm_requires_as_of(reporting_db):
    with pytest.raises(DBAPIError, match="as_of zorunludur"):
        rows(reporting_db, "SELECT * FROM reporting.fn_customer_rfm(NULL)")


def test_rfm_function_does_not_use_current_date():
    from tests.conftest import SQL_DIR

    body = (SQL_DIR / "110_report_customer_rfm.sql").read_text(encoding="utf-8")
    code = "\n".join(line.split("--")[0] for line in body.splitlines())  # yorumlar hariç
    assert "current_date" not in code.lower() and "now()" not in code.lower()


# --- Tutarlılık kontrolü (ETL içinde de çalışır) ---------------------------------------------

def test_reporting_consistency_check_passes(reporting_db):
    from tests.conftest import SQL_DIR

    sql = (SQL_DIR / "tests" / "080_reporting_analyses_consistent.sql").read_text(encoding="utf-8")
    assert rows(reporting_db, sql) == []


# --- sp_refresh_reports ve materialized view kuralları ----------------------------------------

def last_refresh(engine):
    return rows(engine, "SELECT * FROM meta.report_refresh_runs ORDER BY refresh_id DESC LIMIT 1")[0]


def test_materialized_views_have_concurrent_refresh_prerequisites(reporting_db):
    got = rows(reporting_db, """
        SELECT m.matviewname, m.ispopulated,
               EXISTS (SELECT 1 FROM pg_index i
                       WHERE i.indrelid = (m.schemaname || '.' || m.matviewname)::regclass
                         AND i.indisunique AND i.indpred IS NULL AND i.indexprs IS NULL) AS has_unique_index
        FROM pg_matviews m WHERE m.schemaname = 'reporting' ORDER BY 1""")
    assert got == [
        {"matviewname": "mv_category_sales", "ispopulated": True, "has_unique_index": True},
        {"matviewname": "mv_monthly_sales", "ispopulated": True, "has_unique_index": True},
    ]


def test_refresh_reports_first_population_then_concurrently(empty_engine):
    # Boş veritabanı: mv_monthly_sales WITH NO DATA oluşturuldu (doldurulmamış), mv_category_sales WITH DATA.
    with autocommit(empty_engine).connect() as conn:
        conn.execute(text("CALL reporting.sp_refresh_reports()"))
        first = last_refresh(empty_engine)
        conn.execute(text("CALL reporting.sp_refresh_reports()"))
        second = last_refresh(empty_engine)
    modes = lambda r: {d["object"]: d.get("mode", d.get("years")) for d in r["details"]}  # noqa: E731
    assert first["status"] == "succeeded" and first["finished_at"] is not None
    assert modes(first) == {
        "reporting.mv_category_sales": "concurrently",
        "reporting.mv_monthly_sales": "initial_population",
        "reporting.monthly_summary": [],
    }
    assert modes(second)["reporting.mv_monthly_sales"] == "concurrently"


def test_refresh_reports_repeated_calls_are_idempotent(reporting_db):
    before = rows(reporting_db, "SELECT * FROM reporting.mv_category_sales ORDER BY sales_rank")
    with autocommit(reporting_db).connect() as conn:
        conn.execute(text("CALL reporting.sp_refresh_reports()"))
        conn.execute(text("CALL reporting.sp_refresh_reports()"))
    assert last_refresh(reporting_db)["status"] == "succeeded"
    assert rows(reporting_db, "SELECT * FROM reporting.mv_category_sales ORDER BY sales_rank") == before
    summary = [_as_tuple(r) for r in rows(reporting_db, "SELECT * FROM reporting.monthly_summary ORDER BY month_start")]
    assert summary == EXPECTED_MONTHS


def test_refresh_reports_inside_explicit_transaction_is_rejected(reporting_db):
    # PostgreSQL 16: prosedürdeki COMMIT, açık bir işlem bloğu içinden çağrıldığında geçersizdir.
    count_before = rows(reporting_db, "SELECT count(*) AS n FROM meta.report_refresh_runs")[0]["n"]
    with pytest.raises(DBAPIError, match="invalid transaction termination"):
        with reporting_db.begin() as conn:
            conn.execute(text("CALL reporting.sp_refresh_reports()"))
    assert rows(reporting_db, "SELECT count(*) AS n FROM meta.report_refresh_runs")[0]["n"] == count_before


def test_refresh_failure_is_recorded_and_survives(reporting_db):
    summary_before = rows(reporting_db, "SELECT month_start, loaded_at FROM reporting.monthly_summary ORDER BY 1")
    # Başka bir oturum monthly_summary'yi kilitler; yenileme lock_timeout ile başarısız olur.
    with reporting_db.connect() as locker:
        tx = locker.begin()
        locker.execute(text("LOCK TABLE reporting.monthly_summary IN ACCESS EXCLUSIVE MODE"))
        with autocommit(reporting_db).connect() as conn:
            conn.execute(text("SET lock_timeout = '500ms'"))
            with pytest.raises(DBAPIError, match="Rapor yenileme başarısız") as excinfo:
                conn.execute(text("CALL reporting.sp_refresh_reports()"))
        tx.rollback()

    assert excinfo.value.orig.pgcode == "55P03"  # lock_not_available, özgün SQLSTATE korunur
    failed = last_refresh(reporting_db)  # yeni bir oturumdan okunur: kayıt kalıcı
    assert failed["status"] == "failed" and failed["finished_at"] is not None
    assert failed["error_message"].startswith("55P03:") and "lock timeout" in failed["error_message"]
    # Hata bloğundaki işler geri alındı: özet tablosu değişmedi
    assert rows(reporting_db, "SELECT month_start, loaded_at FROM reporting.monthly_summary ORDER BY 1") == summary_before
