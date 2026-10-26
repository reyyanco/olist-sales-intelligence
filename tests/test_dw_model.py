"""Veri ambarı modelini sentetik örnek veriyle doğrular (tests/fixtures/olist_sample).

Beklenen değerler örnek CSV dosyalarından elle hesaplanmıştır:
- Sipariş ...01: 3 kalem (aynı üründen 2 satır), 2 ödeme, 2 yorum.
- ...01 ve ...02 aynı kişiye (customer_unique_id d...01) ait iki ayrı customer_id.
- ...03 shipped, ...04 canceled (kalemsiz), ...05 delivered ama teslim tarihi boş.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

from etl.load_staging import StagingLoadError, load_staging
from etl.transform import run_sql_checks

O1 = "a" + "0" * 30 + "1"
O2 = "a" + "0" * 30 + "2"
O5 = "a" + "0" * 30 + "5"


def one(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).mappings().one()


def test_staging_preserves_raw_values(loaded_sample):
    row = one(
        loaded_sample,
        "SELECT customer_zip_code_prefix FROM staging.customers ORDER BY customer_id LIMIT 1",
    )
    assert row["customer_zip_code_prefix"] == "01001"  # baştaki sıfır korunur
    row = one(loaded_sample, "SELECT price FROM staging.order_items WHERE order_id = :o AND order_item_id = '1'", o=O1)
    assert row["price"] == "100.00"  # metin olarak, biçim değişmeden
    assert one(loaded_sample, "SELECT count(*) AS n FROM staging.order_reviews")["n"] == 5


def test_multi_item_multi_payment_order_is_not_duplicated(loaded_sample):
    # Doğrudan birleştirme (yanlış yöntem): 3 kalem x 2 ödeme x 2 yorum = 12 satır.
    naive = one(
        loaded_sample,
        """
        SELECT count(*) AS joined_rows,
               sum(i.price::numeric) AS naive_product_sales,
               sum(p.payment_value::numeric) AS naive_payment_amount
        FROM staging.order_items i
        JOIN staging.order_payments p USING (order_id)
        JOIN staging.order_reviews r USING (order_id)
        WHERE i.order_id = :o
        """,
        o=O1,
    )
    assert naive["joined_rows"] == 12
    assert naive["naive_product_sales"] == Decimal("1002.00")  # 250.50 x 4
    assert naive["naive_payment_amount"] == Decimal("1654.50")  # 275.75 x 6

    # Model: sipariş olgusunda kalem, ödeme ve yorum ayrı ayrı toplanmış.
    order = one(loaded_sample, "SELECT * FROM dw.fact_orders WHERE order_id = :o", o=O1)
    assert order["item_count"] == 3
    assert order["product_value"] == Decimal("250.50")
    assert order["freight_value"] == Decimal("25.25")
    assert order["payment_count"] == 2
    assert order["payment_value"] == Decimal("275.75")
    assert order["review_count"] == 2
    assert order["review_score_avg"] == Decimal("4.00")

    # Kalem olgusu kaynakla aynı satır sayısında; raporlama view'i de çoğaltmıyor.
    items = one(
        loaded_sample,
        "SELECT count(*) AS n, sum(price) AS product_sales FROM reporting.v_sales_items WHERE order_id = :o",
        o=O1,
    )
    assert (items["n"], items["product_sales"]) == (3, Decimal("250.50"))
    monthly = one(loaded_sample, "SELECT * FROM reporting.mv_monthly_sales WHERE purchase_month = '2017-01-01'")
    assert monthly["product_sales"] == Decimal("250.50")
    assert monthly["payment_amount"] == Decimal("275.75")
    assert monthly["item_count"] == 3


def test_sales_kpis_use_delivered_scope_and_unique_customers(loaded_sample):
    k = one(loaded_sample, "SELECT * FROM reporting.v_sales_kpis")
    assert k["order_count"] == 3  # delivered: ...01, ...02, ...05
    assert k["customer_count"] == 2  # customer_unique_id: d...01 (2 sipariş), d...04
    assert k["item_count"] == 5
    assert k["product_sales"] == Decimal("360.50")
    assert k["freight_amount"] == Decimal("37.25")
    assert k["payment_amount"] == Decimal("397.75")
    assert k["avg_basket_value"] == Decimal("120.17")  # 360.50 / 3
    assert k["repeat_customer_count"] == 1
    assert k["repeat_purchase_rate"] == Decimal("0.5000")


def test_delivery_metrics_exclude_missing_delivery_dates(loaded_sample):
    k = one(loaded_sample, "SELECT * FROM reporting.v_sales_kpis")
    # ...05 delivered ama teslim zamanı boş: hata sayılmaz, süre ve gecikme paydasına girmez.
    assert k["delivery_measured_orders"] == 2
    assert k["delivery_unmeasured_orders"] == 1
    assert k["avg_delivery_days"] == Decimal("10.25")  # (5.00 + 15.50) / 2
    assert k["late_orders"] == 1  # ...02: 2017-02-20 > 2017-02-18
    assert k["late_delivery_rate"] == Decimal("0.5000")

    o5 = one(loaded_sample, "SELECT delivery_days, is_late, delivered_customer_date_key FROM dw.fact_orders WHERE order_id = :o", o=O5)
    assert o5 == {"delivery_days": None, "is_late": None, "delivered_customer_date_key": None}


def test_other_statuses_are_kept_but_outside_sales_scope(loaded_sample):
    with loaded_sample.connect() as conn:
        rows = dict(conn.execute(text("SELECT order_status, count(*) FROM reporting.v_orders GROUP BY 1")).all())
        canceled = conn.execute(text("SELECT item_count, payment_value, in_sales_scope FROM reporting.v_orders WHERE order_status = 'canceled'")).one()
    assert rows == {"delivered": 3, "shipped": 1, "canceled": 1}
    assert (canceled.item_count, canceled.payment_value, canceled.in_sales_scope) == (0, Decimal("25.00"), False)


def test_rfm_uses_customer_unique_id_and_observation_date(loaded_sample):
    obs = one(loaded_sample, "SELECT * FROM reporting.v_rfm_observation")
    assert str(obs["last_purchase_date"]) == "2017-02-15"
    assert str(obs["observation_date"]) == "2017-02-16"
    with loaded_sample.connect() as conn:
        rfm = {
            r.customer_unique_id: (r.recency_days, r.frequency, r.monetary)
            for r in conn.execute(text("SELECT * FROM reporting.v_customer_rfm_base"))
        }
    assert rfm == {
        "d" + "0" * 30 + "1": (11, 2, Decimal("330.50")),
        "d" + "0" * 30 + "4": (1, 1, Decimal("30.00")),
    }


def test_dim_date_range_comes_from_data(loaded_sample):
    d = one(loaded_sample, "SELECT min(full_date) AS lo, max(full_date) AS hi, count(*) AS n FROM dw.dim_date")
    assert (str(d["lo"]), str(d["hi"]), d["n"]) == ("2017-01-10", "2017-03-10", 60)


def test_product_dimension_keeps_missing_category_and_translation(loaded_sample):
    with loaded_sample.connect() as conn:
        rows = {r.product_id[-1]: (r.category_name, r.category_name_english) for r in conn.execute(text("SELECT * FROM dw.dim_product"))}
    assert rows == {"1": ("beleza_saude", "health_beauty"), "2": ("pc_gamer", None), "3": (None, None)}


def test_timestamps_are_not_converted(loaded_sample):
    row = one(loaded_sample, "SELECT purchase_ts, pg_typeof(purchase_ts)::text AS t FROM dw.fact_orders WHERE order_id = :o", o=O1)
    assert row["t"] == "timestamp without time zone"
    assert str(row["purchase_ts"]) == "2017-01-10 10:00:00"


def test_sql_checks_pass_on_sample(loaded_sample):
    failed = {r.name: r.failing_rows for r in run_sql_checks(loaded_sample) if not r.passed}
    assert failed == {}


def test_header_mismatch_is_rejected(tmp_path, test_engine):
    from tests.conftest import SAMPLE_DIR

    for src in SAMPLE_DIR.iterdir():
        (tmp_path / src.name).write_bytes(src.read_bytes())
    bad = tmp_path / "olist_sellers_dataset.csv"
    bad.write_text("seller_id,zip,seller_city,seller_state\n", encoding="utf-8")
    with pytest.raises(StagingLoadError, match="başlığı"):
        load_staging(test_engine, tmp_path)
