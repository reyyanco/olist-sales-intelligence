"""D1: Dashboard'un gerçekten çalıştırdığı sorgular; (a) ek indeks yok, (b) ana modeldeki ek indeksler.

Amaç: dashboard için hangi indekslerin gerçekten kullanıldığını ve gerekli olup olmadığını planlarla göstermek.
Sorgular dashboard/data.py'nin çağırdığı reporting fonksiyonlarıdır; parametreler gerçek veri kapsamındandır.
"""

from __future__ import annotations

import time
from pathlib import Path

from perf.harness import execute, explain_or_estimate, fetch, measure_or_timeout, plan_summary, save_json

# Ana modeldeki ek (PK/UNIQUE olmayan) indeksler: sql/030_dw_dimensions.sql, sql/040_dw_facts.sql
MODEL_INDEXES = {
    "dim_customer_unique_id_idx": "CREATE INDEX dim_customer_unique_id_idx ON dw.dim_customer (customer_unique_id)",
    "fact_orders_purchase_date_idx": "CREATE INDEX fact_orders_purchase_date_idx ON dw.fact_orders (purchase_date_key)",
    "fact_orders_status_idx": "CREATE INDEX fact_orders_status_idx ON dw.fact_orders (order_status)",
    "fact_sales_product_idx": "CREATE INDEX fact_sales_product_idx ON dw.fact_sales (product_id)",
    "fact_sales_purchase_date_idx": "CREATE INDEX fact_sales_purchase_date_idx ON dw.fact_sales (purchase_date_key)",
    "fact_sales_seller_idx": "CREATE INDEX fact_sales_seller_idx ON dw.fact_sales (seller_id)",
}


def queries(conn) -> list[tuple[str, str, dict]]:
    first, last = fetch(conn, "SELECT first_purchase_date, last_purchase_date FROM reporting.v_data_coverage")[0]
    full = {"f": first, "t": last}
    month = {"f": "2018-03-01", "t": "2018-03-31"}
    return [
        ("overview_full", "SELECT * FROM reporting.fn_overview_kpis(%(f)s, %(t)s, NULL, NULL)", full),
        ("overview_one_month", "SELECT * FROM reporting.fn_overview_kpis(%(f)s, %(t)s, NULL, NULL)", month),
        ("overview_states_SP_RJ_full", "SELECT * FROM reporting.fn_overview_kpis(%(f)s, %(t)s, ARRAY['SP','RJ'], NULL)", full),
        ("overview_category_full", "SELECT * FROM reporting.fn_overview_kpis(%(f)s, %(t)s, NULL, ARRAY['health_beauty'])", full),
        ("monthly_full", "SELECT * FROM reporting.fn_monthly_sales(%(f)s, %(t)s, NULL, NULL)", full),
        ("monthly_state_RJ", "SELECT * FROM reporting.fn_monthly_sales(%(f)s, %(t)s, ARRAY['RJ'], NULL)", full),
        ("category_full", "SELECT * FROM reporting.fn_category_sales(%(f)s, %(t)s, NULL)", full),
        ("category_one_month", "SELECT * FROM reporting.fn_category_sales(%(f)s, %(t)s, NULL)", month),
        ("delivery_region_full", "SELECT * FROM reporting.fn_delivery_by_region(%(f)s, %(t)s, NULL)", full),
        ("delivery_region_one_month", "SELECT * FROM reporting.fn_delivery_by_region(%(f)s, %(t)s, NULL)", month),
        ("delivery_monthly_full", "SELECT * FROM reporting.fn_delivery_monthly(%(f)s, %(t)s, NULL)", full),
        ("repeat_full", "SELECT * FROM reporting.fn_repeat_purchase(%(f)s, %(t)s)", full),
        ("repeat_one_month", "SELECT * FROM reporting.fn_repeat_purchase(%(f)s, %(t)s)", month),
        ("rfm_segments", "SELECT * FROM reporting.fn_rfm_segments(%(t)s::date + 1)", full),
    ]


def _measure_all(conn, qs, label: str, plans_dir: Path) -> dict:
    out = {}
    for name, sql, params in qs:
        m = measure_or_timeout(conn, sql, params)
        plan, analyzed = explain_or_estimate(conn, sql, params)
        save_json(plans_dir / f"D1_{name}_{label}.json", plan)
        out[name] = {"sql": sql, "params": params, "measurement": m, "plan_analyzed": analyzed,
                     "plan_file": f"D1_{name}_{label}.json", "plan": plan_summary(plan)}
    return out


def run(conn, plans_dir: Path) -> dict:
    present = {r[0] for r in fetch(conn, "SELECT indexname FROM pg_indexes WHERE schemaname = 'dw'")}
    if present & set(MODEL_INDEXES):
        raise RuntimeError(f"Başlangıç durumunda ek indeks olmamalı: {sorted(present & set(MODEL_INDEXES))}")
    qs = queries(conn)
    result = {"queries": [q[0] for q in qs], "states": {}}
    result["states"]["no_extra_indexes"] = _measure_all(conn, qs, "no_extra_indexes", plans_dir)
    started = time.perf_counter()
    try:
        for ddl in MODEL_INDEXES.values():
            execute(conn, ddl)
        result["model_indexes_build_ms_single_run"] = round((time.perf_counter() - started) * 1000, 3)
        result["states"]["model_indexes"] = _measure_all(conn, qs, "model_indexes", plans_dir)
    finally:
        for name in MODEL_INDEXES:
            execute(conn, f"DROP INDEX IF EXISTS dw.{name}")
    a, b = result["states"]["no_extra_indexes"], result["states"]["model_indexes"]
    result["comparison"] = {
        n: {
            "median_no_extra_ms": a[n]["measurement"].get("median_ms"),
            "median_model_ms": b[n]["measurement"].get("median_ms"),
            "result_equal": a[n]["measurement"].get("result_md5") == b[n]["measurement"].get("result_md5"),
            "model_indexes_used": b[n]["plan"]["indexes_used"],
        }
        for n in result["queries"]
    }
    used = sorted({i for c in result["comparison"].values() for i in c["model_indexes_used"] if i in MODEL_INDEXES})
    result["model_indexes_used_by_any_dashboard_query"] = used
    result["model_indexes_unused_by_dashboard"] = sorted(set(MODEL_INDEXES) - set(used))
    return result
