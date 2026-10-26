"""Gerçek veri doğrulama kontrolleri. Beklenen değerler reporting nesnelerinden BAĞIMSIZ hesaplanır
(doğrudan dw/staging tabloları); gerçek değerler raporlama katmanından okunur.

Kullanım (ayrı doğrulama veritabanında; .\\scripts\\validate-clean-install.ps1 çağırır):
  python -m validation.checks snapshot --output <json>
  python -m validation.checks invariants --output <json>
  python -m validation.checks routines --output <json>
  python -m validation.checks controlled-failure --output <json>
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import tempfile
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Engine, text

from etl.db import create_db_engine
from etl.pipeline import QualityCheckError, run_pipeline
from etl.settings import load_settings

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

SNAPSHOT_OBJECTS = ["dw.dim_customer", "dw.dim_product", "dw.dim_seller", "dw.dim_date", "dw.fact_orders",
                    "dw.fact_sales", "dw.fact_payments", "reporting.mv_monthly_sales", "reporting.mv_category_sales",
                    "reporting.monthly_summary", "reporting.v_sales_kpis"]


def one(conn, sql: str, **params):
    return conn.execute(text(sql), params).one()


# loaded_at her yüklemede değişir; içerik karşılaştırmasına girmez.
SNAPSHOT_SOURCES = {t: t for t in SNAPSHOT_OBJECTS}
SNAPSHOT_SOURCES["reporting.monthly_summary"] = (
    "(SELECT month_start, order_count, customer_count, item_count, product_sales, freight_amount, payment_amount, "
    "avg_basket_value, prev_product_sales, product_sales_change, growth_rate, growth_status, is_partial_month, "
    "observed_from, observed_to FROM reporting.monthly_summary)")


def snapshot(engine: Engine) -> dict:
    with engine.connect() as conn:
        return {t: list(one(conn, f"SELECT count(*), md5(COALESCE(string_agg(x::text, '|' ORDER BY x::text), '')) FROM {src} x"))
                for t, src in SNAPSHOT_SOURCES.items()}


def check(name: str, purpose: str, expected, actual, ok: bool | None = None) -> dict:
    passed = (expected == actual) if ok is None else ok
    return {"check": name, "purpose": purpose, "expected": expected, "actual": actual,
            "status": "geçti" if passed else "başarısız"}


def invariants(engine: Engine) -> list[dict]:
    out = []
    with engine.connect() as conn:
        k = conn.execute(text("SELECT * FROM reporting.v_sales_kpis")).mappings().one()
        # Bağımsız taban: teslim edilmiş siparişler ve kalemleri (dw tabloları, reporting yok)
        base = one(conn, """
            SELECT (SELECT sum(s.price) FROM dw.fact_sales s JOIN dw.fact_orders o USING (order_id) WHERE o.order_status = 'delivered'),
                   (SELECT sum(p.payment_value) FROM dw.fact_payments p JOIN dw.fact_orders o USING (order_id) WHERE o.order_status = 'delivered'),
                   (SELECT count(*) FROM dw.fact_orders WHERE order_status = 'delivered'),
                   (SELECT count(*) FROM dw.fact_sales s JOIN dw.fact_orders o USING (order_id) WHERE o.order_status = 'delivered'),
                   (SELECT count(DISTINCT c.customer_unique_id) FROM dw.fact_orders o JOIN dw.dim_customer c USING (customer_id) WHERE o.order_status = 'delivered'),
                   (SELECT count(DISTINCT o.customer_id) FROM dw.fact_orders o WHERE o.order_status = 'delivered')""")
        prod, pay, orders, items, uniq, cust_ids = base
        # Staging'den (dönüşümden bağımsız) aynı tutar
        staged = one(conn, """SELECT sum(i.price::numeric) FROM staging.order_items i JOIN staging.orders o USING (order_id)
                              WHERE o.order_status = 'delivered'""")[0]
        naive = one(conn, """SELECT sum(i.price::numeric) FROM staging.order_items i
                             JOIN staging.order_payments p USING (order_id) JOIN staging.order_reviews r USING (order_id)
                             JOIN staging.orders o USING (order_id) WHERE o.order_status = 'delivered'""")[0]
        out.append(check("product_sales_no_join_duplication",
                         "Ürün satış tutarı kalem/ödeme/yorum join'leriyle çoğalmıyor (staging'den bağımsız toplam)",
                         str(staged), str(k["product_sales"])))
        out.append(check("naive_join_would_inflate",
                         "Bilgi: kalem×ödeme×yorum doğrudan join edilseydi tutar şişerdi (modelin bunu yapmadığını gösterir)",
                         f"> {staged}", str(naive), ok=naive > staged))
        out.append(check("payment_not_mixed_with_product_sales",
                         "Ödeme tutarı ürün satış tutarından ayrı tutuluyor ve doğru kaynaktan geliyor",
                         {"product_sales": str(prod), "payment_amount": str(pay)},
                         {"product_sales": str(k["product_sales"]), "payment_amount": str(k["payment_amount"])}))
        out.append(check("order_count_not_item_count", "Sipariş sayısı kalem sayısından ayrı ve doğru",
                         {"orders": orders, "items": items}, {"orders": k["order_count"], "items": k["item_count"]}))
        out.append(check("customer_count_uses_unique_id",
                         f"Müşteri sayısı customer_unique_id ile ({uniq}); customer_id ile sayılsaydı {cust_ids} olurdu",
                         uniq, k["customer_count"], ok=(k["customer_count"] == uniq and uniq != cust_ids)))

        # Teslimat paydaları (bağımsız: delivery_days kolonu yerine ham zamanlardan)
        d = one(conn, """
            SELECT round(avg(round(EXTRACT(EPOCH FROM (delivered_customer_ts - purchase_ts)) / 86400.0, 2)), 2),
                   count(delivered_customer_ts),
                   count(*) FILTER (WHERE delivered_customer_ts::date > estimated_delivery_date),
                   count(*) - count(delivered_customer_ts)
            FROM dw.fact_orders WHERE order_status = 'delivered'""")
        late_rate = (Decimal(d[2]) / d[1]).quantize(Decimal("0.0001"))
        out.append(check("delivery_denominators",
                         "Teslimat süresi ve geç teslim oranı paydası = teslim zamanı DOLU teslim edilmiş siparişler",
                         {"avg_days": str(d[0]), "measured": d[1], "late": d[2], "late_rate": str(late_rate), "unmeasured": d[3]},
                         {"avg_days": str(k["avg_delivery_days"]), "measured": k["delivery_measured_orders"],
                          "late": k["late_orders"], "late_rate": str(k["late_delivery_rate"]),
                          "unmeasured": k["delivery_unmeasured_orders"]}))

        # RFM: gözlem tarihinden sonraki satın almalar dışlanmalı
        as_of = dt.date(2018, 1, 1)
        rfm = one(conn, "SELECT count(*), sum(frequency), max(last_purchase_date), sum(monetary) FROM reporting.fn_customer_rfm(:a)", a=as_of)
        exp = one(conn, """
            SELECT count(DISTINCT c.customer_unique_id), count(*), max(o.purchase_ts::date),
                   (SELECT sum(s.price) FROM dw.fact_sales s JOIN dw.fact_orders o2 USING (order_id)
                    WHERE o2.order_status = 'delivered' AND o2.purchase_ts < :a)
            FROM dw.fact_orders o JOIN dw.dim_customer c USING (customer_id)
            WHERE o.order_status = 'delivered' AND o.purchase_ts < :a""", a=as_of)
        out.append(check("rfm_excludes_purchases_after_as_of",
                         f"RFM (as_of={as_of}) yalnızca bu günden önceki satın almaları içerir; frequency = farklı sipariş",
                         {"customers": exp[0], "frequency_sum": exp[1], "max_last_purchase": str(exp[2]), "monetary": str(exp[3])},
                         {"customers": rfm[0], "frequency_sum": rfm[1], "max_last_purchase": str(rfm[2]), "monetary": str(rfm[3])}))

        # Tekrar satın alma: customer_unique_id ve farklı siparişler
        rp = one(conn, """SELECT count(*), count(*) FILTER (WHERE n >= 2) FROM (
                            SELECT c.customer_unique_id, count(DISTINCT o.order_id) n FROM dw.fact_orders o
                            JOIN dw.dim_customer c USING (customer_id) WHERE o.order_status = 'delivered' GROUP BY 1) x""")
        out.append(check("repeat_purchase_unique_and_distinct_orders", "Tekrar satın alma: customer_unique_id, ≥2 farklı sipariş",
                         {"customers": rp[0], "repeaters": rp[1]},
                         {"customers": k["customer_count"], "repeaters": k["repeat_customer_count"]}))

        # Ay ortası aralıkta KPI = aylık seri toplamı (Aşama 8'de bulunan hata)
        mid = one(conn, """SELECT o.product_sales, o.order_count,
                                  (SELECT sum(m.product_sales) FROM reporting.fn_monthly_sales('2018-01-15', '2018-03-10') m),
                                  (SELECT sum(m.order_count) FROM reporting.fn_monthly_sales('2018-01-15', '2018-03-10') m),
                                  (SELECT sum(s.price) FROM dw.fact_sales s JOIN dw.fact_orders o2 USING (order_id)
                                   WHERE o2.order_status = 'delivered' AND o2.purchase_ts >= '2018-01-15' AND o2.purchase_ts < '2018-03-11')
                           FROM reporting.fn_overview_kpis('2018-01-15', '2018-03-10') o""")
        out.append(check("dashboard_monthly_same_scope_as_kpis",
                         "Dashboard: 15.01–10.03.2018 aralığında aylık seri toplamı = KPI = doğrudan SQL",
                         {"direct_sql_sales": str(mid[4]), "kpi_orders": mid[1]},
                         {"kpi_sales": str(mid[0]), "monthly_sum_sales": str(mid[2]), "monthly_sum_orders": mid[3]},
                         ok=(mid[0] == mid[2] == mid[4] and mid[1] == mid[3])))

        # Aylık raporlar yalnızca satış gözlem aralığını içerir; aralık içi sıfır aylar ile gözlem dışı aylar ayrı (sql/200)
        lo, hi = one(conn, "SELECT min(purchase_ts)::date, max(purchase_ts)::date FROM dw.fact_orders "
                           "WHERE order_status = 'delivered'")
        months_of = lambda sql: [str(r[0]) for r in conn.execute(text(sql)).all()]  # noqa: E731
        next_month = lambda d: dt.date(d.year + d.month // 12, d.month % 12 + 1, 1)  # noqa: E731
        exp_months, m = [], lo.replace(day=1)
        while m <= hi:
            exp_months.append(str(m))
            m = next_month(m)
        partial = sorted(({str(lo.replace(day=1))} if lo.day != 1 else set())
                         | ({str(hi.replace(day=1))} if hi != next_month(hi) - dt.timedelta(days=1) else set()))
        sold = set(months_of("SELECT DISTINCT date_trunc('month', purchase_ts)::date FROM dw.fact_orders "
                             "WHERE order_status = 'delivered'"))
        dim_months = months_of("SELECT DISTINCT month_start FROM dw.dim_date ORDER BY 1")
        expected = {
            "window": [str(lo), str(hi)],
            "months": exp_months,
            "real_zero_months": [x for x in exp_months if x not in sold],
            "partial_months": partial,
            "not_observed_months": [x for x in dim_months if x not in exp_months],
            "dim_date_end": str(one(conn, "SELECT greatest(max(purchase_ts::date), max(delivered_customer_ts::date), "
                                          "max(estimated_delivery_date)) FROM dw.fact_orders")[0]),
            "growth_rates_on_partial": 0,
        }
        actual = {
            "window": [str(x) for x in one(conn, "SELECT min(observed_from), max(observed_to) FROM reporting.v_sales_observation_months")],
            "months": months_of("SELECT month_start FROM reporting.v_monthly_sales_growth ORDER BY 1"),
            "summary_months": months_of("SELECT month_start FROM reporting.monthly_summary ORDER BY 1"),
            "real_zero_months": months_of("SELECT month_start FROM reporting.v_monthly_sales_growth WHERE order_count = 0 ORDER BY 1"),
            "partial_months": months_of("SELECT month_start FROM reporting.v_monthly_sales_growth WHERE is_partial_month ORDER BY 1"),
            "not_observed_months": months_of("SELECT month_start FROM reporting.v_sales_observation_months "
                                             "WHERE observation_status = 'not_observed' ORDER BY 1"),
            "dim_date_end": str(one(conn, "SELECT max(full_date) FROM dw.dim_date")[0]),
            "growth_rates_on_partial": one(conn, """SELECT count(*) FROM (SELECT growth_rate, is_partial_month,
                                                    LAG(is_partial_month) OVER (ORDER BY month_start) AS pp
                                                    FROM reporting.v_monthly_sales_growth) x
                                                    WHERE growth_rate IS NOT NULL AND (is_partial_month OR pp)""")[0],
        }
        out.append(check("monthly_reports_observation_window",
                         "Aylık raporlar yalnızca satış gözlem aralığını (ilk..son delivered satın alma) içerir; aralık içi "
                         "sıfır aylar 0 olarak kalır; tahmini teslim tarihlerinin uzattığı aylar gözlem dışıdır; dim_date korunur",
                         expected, actual,
                         ok=all(actual[key] == expected[key] for key in expected) and actual["summary_months"] == exp_months))
        out[-1]["detail"] = {"orders_any_status_in_not_observed_months": {
            str(r[0]): r[1] for r in conn.execute(text(
                "SELECT d.month_start, count(o.order_id) FROM (SELECT DISTINCT month_start FROM dw.dim_date) d "
                "LEFT JOIN dw.fact_orders o ON date_trunc('month', o.purchase_ts)::date = d.month_start "
                "WHERE d.month_start::text = ANY (:m) GROUP BY 1 ORDER BY 1"), {"m": expected["not_observed_months"]}).all()}}

        # Sipariş durumu kuralları: reporting'deki tüm view/fonksiyon tanımlarındaki order_status karşılaştırmaları
        defs = conn.execute(text("""
            SELECT 'view ' || viewname, definition FROM pg_views WHERE schemaname = 'reporting'
            UNION ALL SELECT 'matview ' || matviewname, definition FROM pg_matviews WHERE schemaname = 'reporting'
            UNION ALL SELECT 'function ' || p.proname, p.prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                      WHERE n.nspname = 'reporting'""")).all()
        rules = {}
        for name, body in defs:
            for op, lit in re.findall(r"order_status\s*(=|<>|!=|IN)\s*\(?'(\w+)'", body or "", flags=re.I):
                rules.setdefault(f"{op.upper()} '{lit}'", []).append(name)
        out.append(check("single_sales_scope_rule",
                         "Raporlama nesnelerinde satış kapsamı tek kural: order_status = 'delivered' (başka durum literali yok)",
                         ["= 'delivered'"], sorted(rules), ok=set(rules) <= {"= 'delivered'"}))
        out[-1]["detail"] = {r: sorted(set(v)) for r, v in rules.items()}
    return out


def routines(engine: Engine) -> list[dict]:
    out = []
    auto = engine.execution_options(isolation_level="AUTOCOMMIT")
    with auto.connect() as conn:
        before = conn.execute(text("SELECT count(*), md5(string_agg(x::text, '|' ORDER BY month_start)) "
                                   "FROM (SELECT month_start, product_sales, order_count, growth_rate FROM reporting.monthly_summary) x")).one()
        months = conn.execute(text("SELECT count(*) FROM reporting.v_sales_observation_months "
                                   "WHERE observation_status <> 'not_observed'")).scalar()
        runs0 = conn.execute(text("SELECT count(*) FROM meta.report_refresh_runs WHERE status = 'succeeded'")).scalar()
        for _ in range(2):
            conn.execute(text("CALL reporting.sp_refresh_reports()"))
        for _ in range(2):
            conn.execute(text("CALL reporting.sp_load_monthly_summary(2017)"))
        after = conn.execute(text("SELECT count(*), md5(string_agg(x::text, '|' ORDER BY month_start)) "
                                  "FROM (SELECT month_start, product_sales, order_count, growth_rate FROM reporting.monthly_summary) x")).one()
        runs1 = conn.execute(text("SELECT count(*) FROM meta.report_refresh_runs WHERE status = 'succeeded'")).scalar()
        mv = conn.execute(text("SELECT matviewname, ispopulated FROM pg_matviews WHERE schemaname = 'reporting' ORDER BY 1")).all()
    out.append(check("routines_repeat_no_duplication",
                     "sp_refresh_reports ×2 ve sp_load_monthly_summary(2017) ×2: monthly_summary satır sayısı = gözlem aralığındaki ay sayısı, içerik değişmez",
                     {"rows": months, "content_md5": before[1]}, {"rows": after[0], "content_md5": after[1]},
                     ok=(after[0] == months and after[1] == before[1])))
    out.append(check("refresh_runs_recorded", "Her sp_refresh_reports çağrısı 'succeeded' kaydı bırakır", 2, runs1 - runs0))
    out.append(check("materialized_views_populated", "Tüm reporting MV'leri doldurulmuş",
                     [[m, True] for m, _ in mv], [[m, p] for m, p in mv]))
    return out


def controlled_failure(engine: Engine) -> list[dict]:
    before = snapshot(engine)
    checks_dir = Path(tempfile.mkdtemp())
    (checks_dir / "999_controlled_failure.sql").write_text("SELECT 'controlled failure' AS problem", encoding="utf-8")
    failed = False
    try:
        run_pipeline(engine, RAW_DIR, tests_dir=checks_dir)
    except QualityCheckError:
        failed = True
    after = snapshot(engine)
    with engine.connect() as conn:
        last = conn.execute(text("SELECT status, error_message FROM meta.etl_runs ORDER BY started_at DESC LIMIT 1")).one()
    return [check("failed_load_keeps_previous_data",
                  "Gerçek veriyle tam yeniden yükleme, son kalite kontrolünde bilerek başarısız olur: dw/raporlar değişmemeli, "
                  "çalışma 'failed' kaydedilmeli",
                  {"raised": True, "snapshot_unchanged": True, "run_status": "failed"},
                  {"raised": failed, "snapshot_unchanged": before == after, "run_status": last[0]},
                  ok=(failed and before == after and last[0] == "failed"))]


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m validation.checks")
    parser.add_argument("mode", choices=["snapshot", "invariants", "routines", "controlled-failure"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = load_settings()
    engine = create_db_engine(settings)
    try:
        result = {"snapshot": lambda: snapshot(engine), "invariants": lambda: invariants(engine),
                  "routines": lambda: routines(engine), "controlled-failure": lambda: controlled_failure(engine)}[args.mode]()
    finally:
        engine.dispose()
    doc = {"database": settings.database, "data": "GERÇEK Olist verisi (data/raw)", "mode": args.mode,
           "at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "result": result}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    if isinstance(result, list):
        for r in result:
            print(f"{r['status']:10s} {r['check']}")
        return 0 if all(r["status"] == "geçti" for r in result) else 1
    print(json.dumps(result, ensure_ascii=False)[:300])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
