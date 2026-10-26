"""Deney tanımları. Her deney: başlangıç (baseline) sorgusu + tek tek uygulanıp geri alınan değişiklikler."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from perf.harness import (
    execute,
    explain_or_estimate,
    fetch,
    measure_or_timeout,
    plan_summary,
    save_json,
    time_statement,
)


@dataclass
class Change:
    name: str
    description: str
    apply_sql: list[str] = field(default_factory=list)   # DDL veya oturum ayarı; geri alınır
    revert_sql: list[str] = field(default_factory=list)
    index_names: list[str] = field(default_factory=list)
    sql: str | None = None                               # sorgu düzenleme: başlangıç sorgusunun yerine
    write_cost: tuple[str, str] | None = None            # (tablo, "{t}" yer tutuculu indeks DDL)


@dataclass
class Experiment:
    id: str
    title: str
    technique: str
    sql: str
    params: dict
    ordered: bool
    changes: list[Change]
    baseline_write_cost_table: str | None = None


def write_cost(conn, table: str, index_ddl: str | None) -> dict:
    """Tablonun tüm satırlarını boş bir geçici kopyaya ekleme süresi; indeksli ve indekssiz karşılaştırma için."""
    setup = ["DROP TABLE IF EXISTS pg_temp.perf_write", f"CREATE TEMP TABLE perf_write (LIKE {table})"]
    if index_ddl:
        setup.append(index_ddl.format(t="pg_temp.perf_write"))
    m = time_statement(conn, [f"INSERT INTO pg_temp.perf_write SELECT * FROM {table}"],
                       setup=setup, teardown=["DROP TABLE pg_temp.perf_write"])
    rows = fetch(conn, f"SELECT count(*) FROM {table}")[0][0]
    return {"table": table, "index_ddl": index_ddl, "rows_inserted": rows, **m.to_dict()}


def _state(conn, exp: Experiment, sql: str, label: str, plans_dir: Path) -> dict:
    m = measure_or_timeout(conn, sql, exp.params, ordered=exp.ordered)
    plan, analyzed = explain_or_estimate(conn, sql, exp.params)
    plan_file = plans_dir / f"{exp.id}_{label}.json"
    save_json(plan_file, plan)
    return {"state": label, "sql": sql, "measurement": m, "plan_file": plan_file.name,
            "plan_analyzed": analyzed, "plan": plan_summary(plan)}


def _compare(state: dict, reference: dict | None, baseline: dict) -> dict:
    """Sonuç eşitliği ve hızlanma. Başlangıç zaman aşımına uğradıysa oran uydurulmaz, alt sınır verilir."""
    m, b = state["measurement"], baseline["measurement"]
    out: dict = {}
    if m.get("timed_out"):
        out["result_equal_to_reference"] = None
    elif reference is not None:
        r = reference["measurement"]
        out["result_reference_state"] = reference["state"]
        out["result_equal_to_reference"] = m["result_md5"] == r["result_md5"] and m["row_count"] == r["row_count"]
    if not m.get("timed_out"):
        if b.get("timed_out"):
            out["median_speedup_lower_bound"] = round(b["timeout_ms"] / m["median_ms"], 1)
        else:
            out["median_speedup_vs_baseline"] = round(b["median_ms"] / m["median_ms"], 2)
    return out


def run_experiment(conn, exp: Experiment, plans_dir: Path) -> dict:
    result = {"id": exp.id, "title": exp.title, "technique": exp.technique, "params": exp.params, "states": []}
    baseline = _state(conn, exp, exp.sql, "baseline", plans_dir)
    if exp.baseline_write_cost_table:
        baseline["write_cost"] = write_cost(conn, exp.baseline_write_cost_table, None)
    result["states"].append(baseline)
    # Sonuç karşılaştırmasının referansı: başlangıç; o zaman aşımına uğradıysa ölçülebilen ilk durum.
    reference = None if baseline["measurement"].get("timed_out") else baseline

    for change in exp.changes:
        try:
            started = time.perf_counter()
            for s in change.apply_sql:
                execute(conn, s)
            build_ms = round((time.perf_counter() - started) * 1000, 3)
            state = _state(conn, exp, change.sql or exp.sql, change.name, plans_dir)
            if reference is None and not state["measurement"].get("timed_out"):
                reference = state
            state.update({
                "description": change.description,
                "apply_sql": change.apply_sql,
                "apply_ms_single_run": build_ms if change.apply_sql else None,
                "index_sizes_bytes": {
                    n: fetch(conn, "SELECT pg_relation_size(%(n)s::regclass)", {"n": n})[0][0] for n in change.index_names
                },
                **_compare(state, reference if reference is not state else None, baseline),
            })
            if change.write_cost:
                state["write_cost"] = write_cost(conn, *change.write_cost)
            result["states"].append(state)
        finally:
            for s in change.revert_sql:
                execute(conn, s)
    return result


# --- Parametre seçimi (belirlenimci) --------------------------------------------------------

PARAM_QUERIES = {
    "customer_unique_id": (
        "SELECT customer_unique_id FROM dw.dim_customer GROUP BY customer_unique_id "
        "ORDER BY count(*) DESC, customer_unique_id LIMIT 1"
    ),
    "seller_id": "SELECT seller_id FROM dw.fact_sales GROUP BY seller_id ORDER BY count(*) DESC, seller_id LIMIT 1",
    "as_of": "SELECT observation_date FROM reporting.v_rfm_observation",
}


def choose_params(conn) -> dict:
    return {name: fetch(conn, sql)[0][0] for name, sql in PARAM_QUERIES.items()}


def build_experiments(conn, p: dict) -> list[Experiment]:
    mv_def = fetch(conn, "SELECT pg_get_viewdef('reporting.mv_category_sales'::regclass, true)")[0][0].strip().rstrip(";")
    return [
        Experiment(
            id="E1_customer_history",
            title="Bir kişinin (customer_unique_id) sipariş geçmişi",
            technique="B-tree indeks",
            sql=(
                "SELECT o.order_id, o.purchase_ts, o.order_status, o.product_value, o.payment_value "
                "FROM dw.fact_orders o JOIN dw.dim_customer c ON c.customer_id = o.customer_id "
                "WHERE c.customer_unique_id = %(customer_unique_id)s ORDER BY o.purchase_ts, o.order_id"
            ),
            params={"customer_unique_id": p["customer_unique_id"]},
            ordered=True,
            baseline_write_cost_table="dw.dim_customer",
            changes=[
                Change(
                    name="btree_customer_unique_id",
                    description="dim_customer(customer_unique_id) B-tree indeksi",
                    apply_sql=["CREATE INDEX perf_dim_customer_unique_idx ON dw.dim_customer (customer_unique_id)"],
                    revert_sql=["DROP INDEX IF EXISTS dw.perf_dim_customer_unique_idx"],
                    index_names=["dw.perf_dim_customer_unique_idx"],
                    write_cost=("dw.dim_customer", "CREATE INDEX ON {t} (customer_unique_id)"),
                )
            ],
        ),
        Experiment(
            id="E2_seller_date_range",
            title="En çok kalemi olan satıcının 2018-01..03 günlük satışları",
            technique="tek kolon / birleşik / INCLUDE indeks",
            sql=(
                "SELECT purchase_date_key, count(*) AS items, sum(price) AS product_sales FROM dw.fact_sales "
                "WHERE seller_id = %(seller_id)s AND purchase_date_key BETWEEN %(from_key)s AND %(to_key)s "
                "GROUP BY purchase_date_key ORDER BY purchase_date_key"
            ),
            params={"seller_id": p["seller_id"], "from_key": 20180101, "to_key": 20180331},
            ordered=True,
            baseline_write_cost_table="dw.fact_sales",
            changes=[
                Change(
                    name="btree_seller",
                    description="fact_sales(seller_id) tek kolon B-tree",
                    apply_sql=["CREATE INDEX perf_sales_seller_idx ON dw.fact_sales (seller_id)"],
                    revert_sql=["DROP INDEX IF EXISTS dw.perf_sales_seller_idx"],
                    index_names=["dw.perf_sales_seller_idx"],
                    write_cost=("dw.fact_sales", "CREATE INDEX ON {t} (seller_id)"),
                ),
                Change(
                    name="composite_seller_date",
                    description="fact_sales(seller_id, purchase_date_key) birleşik B-tree",
                    apply_sql=["CREATE INDEX perf_sales_seller_date_idx ON dw.fact_sales (seller_id, purchase_date_key)"],
                    revert_sql=["DROP INDEX IF EXISTS dw.perf_sales_seller_date_idx"],
                    index_names=["dw.perf_sales_seller_date_idx"],
                    write_cost=("dw.fact_sales", "CREATE INDEX ON {t} (seller_id, purchase_date_key)"),
                ),
                Change(
                    name="composite_include_price",
                    description="fact_sales(seller_id, purchase_date_key) INCLUDE (price) (index-only scan adayı)",
                    apply_sql=[
                        "CREATE INDEX perf_sales_seller_date_incl_idx ON dw.fact_sales (seller_id, purchase_date_key) INCLUDE (price)"
                    ],
                    revert_sql=["DROP INDEX IF EXISTS dw.perf_sales_seller_date_incl_idx"],
                    index_names=["dw.perf_sales_seller_date_incl_idx"],
                    write_cost=("dw.fact_sales", "CREATE INDEX ON {t} (seller_id, purchase_date_key) INCLUDE (price)"),
                ),
            ],
        ),
        Experiment(
            id="E3_open_orders",
            title="Teslim edilmemiş son 50 sipariş",
            technique="durum indeksi / tam indeks / partial index",
            sql=(
                "SELECT order_id, order_status, purchase_ts, estimated_delivery_date FROM dw.fact_orders "
                "WHERE order_status <> 'delivered' ORDER BY purchase_ts DESC, order_id LIMIT 50"
            ),
            params={},
            ordered=True,
            baseline_write_cost_table="dw.fact_orders",
            changes=[
                Change(
                    name="btree_status",
                    description="fact_orders(order_status) B-tree (ana modeldeki fact_orders_status_idx ile aynı tanım)",
                    apply_sql=["CREATE INDEX perf_orders_status_idx ON dw.fact_orders (order_status)"],
                    revert_sql=["DROP INDEX IF EXISTS dw.perf_orders_status_idx"],
                    index_names=["dw.perf_orders_status_idx"],
                    write_cost=("dw.fact_orders", "CREATE INDEX ON {t} (order_status)"),
                ),
                Change(
                    name="full_purchase_desc",
                    description="fact_orders(purchase_ts DESC, order_id) tam indeks",
                    apply_sql=["CREATE INDEX perf_orders_purchase_full_idx ON dw.fact_orders (purchase_ts DESC, order_id)"],
                    revert_sql=["DROP INDEX IF EXISTS dw.perf_orders_purchase_full_idx"],
                    index_names=["dw.perf_orders_purchase_full_idx"],
                    write_cost=("dw.fact_orders", "CREATE INDEX ON {t} (purchase_ts DESC, order_id)"),
                ),
                Change(
                    name="partial_open_orders",
                    description="fact_orders(purchase_ts DESC, order_id) WHERE order_status <> 'delivered' partial indeks",
                    apply_sql=[
                        "CREATE INDEX perf_orders_open_partial_idx ON dw.fact_orders (purchase_ts DESC, order_id) "
                        "WHERE order_status <> 'delivered'"
                    ],
                    revert_sql=["DROP INDEX IF EXISTS dw.perf_orders_open_partial_idx"],
                    index_names=["dw.perf_orders_open_partial_idx"],
                    write_cost=("dw.fact_orders", "CREATE INDEX ON {t} (purchase_ts DESC, order_id) WHERE order_status <> 'delivered'"),
                ),
            ],
        ),
        Experiment(
            id="E4_repeat_purchase_rewrite",
            title="Tekrar satın alma oranı (reporting.v_repeat_purchase)",
            technique="sorgu düzenleme",
            sql="SELECT * FROM reporting.v_repeat_purchase ORDER BY cohort_month NULLS LAST",
            params={},
            ordered=True,
            changes=[
                Change(
                    name="btree_customer_unique_id",
                    description="dim_customer(customer_unique_id) B-tree (ana modeldeki dim_customer_unique_id_idx ile aynı tanım)",
                    apply_sql=["CREATE INDEX perf_dim_customer_unique_idx ON dw.dim_customer (customer_unique_id)"],
                    revert_sql=["DROP INDEX IF EXISTS dw.perf_dim_customer_unique_idx"],
                    index_names=["dw.perf_dim_customer_unique_idx"],
                ),
                Change(
                    name="single_pass_aggregate",
                    description="DISTINCT ON + EXISTS yerine müşteri başına tek geçişli toplama (count(DISTINCT order_id) >= 2)",
                    sql=(
                        "WITH customers AS ("
                        " SELECT customer_unique_id, min(purchase_month) AS cohort_month, count(DISTINCT order_id) AS orders"
                        " FROM reporting.v_orders WHERE in_sales_scope GROUP BY customer_unique_id) "
                        "SELECT CASE WHEN GROUPING(cohort_month) = 1 THEN 'total' ELSE 'cohort' END AS grouping_level,"
                        " cohort_month, count(*) AS customer_count,"
                        " count(*) FILTER (WHERE orders >= 2) AS repeat_customer_count,"
                        " round(count(*) FILTER (WHERE orders >= 2)::numeric / NULLIF(count(*), 0), 4) AS repeat_purchase_rate "
                        "FROM customers GROUP BY GROUPING SETS ((cohort_month), ()) ORDER BY cohort_month NULLS LAST"
                    ),
                )
            ],
        ),
        Experiment(
            id="E5_category_sales_mv",
            title="Kategori satışları ve kümülatif pay",
            technique="materialized view",
            sql=f"SELECT * FROM ({mv_def}) q ORDER BY sales_rank",
            params={},
            ordered=True,
            changes=[
                Change(
                    name="read_materialized_view",
                    description="Aynı sonucu reporting.mv_category_sales üzerinden okuma",
                    sql="SELECT * FROM reporting.mv_category_sales ORDER BY sales_rank",
                )
            ],
        ),
        Experiment(
            id="E6_rfm_work_mem",
            title="RFM: reporting.fn_customer_rfm(as_of)",
            technique="oturum work_mem (planda diske taşma için)",
            sql="SELECT * FROM reporting.fn_customer_rfm(%(as_of)s)",
            params={"as_of": p["as_of"]},
            ordered=True,
            changes=[
                Change(
                    name="work_mem_64mb",
                    description="SET work_mem = '64MB' (yalnız bu oturum)",
                    apply_sql=["SET work_mem = '64MB'"],
                    revert_sql=["RESET work_mem"],
                )
            ],
        ),
    ]


BASELINE_CATALOG = {
    "kpis": "SELECT * FROM reporting.v_sales_kpis",
    "monthly_growth": "SELECT * FROM reporting.v_monthly_sales_growth ORDER BY month_start",
    "monthly_mv": "SELECT * FROM reporting.mv_monthly_sales ORDER BY purchase_month",
    "delivery_rollup": "SELECT * FROM reporting.v_delivery_performance ORDER BY purchase_year NULLS LAST, purchase_month NULLS LAST",
    "repeat_purchase": "SELECT * FROM reporting.v_repeat_purchase ORDER BY cohort_month NULLS LAST",
    "category_mv": "SELECT * FROM reporting.mv_category_sales ORDER BY sales_rank",
}


def run_catalog(conn, plans_dir: Path) -> dict:
    out = {}
    for name, sql in BASELINE_CATALOG.items():
        m = measure_or_timeout(conn, sql)
        plan, analyzed = explain_or_estimate(conn, sql)
        save_json(plans_dir / f"catalog_{name}.json", plan)
        out[name] = {"sql": sql, "measurement": m, "plan_file": f"catalog_{name}.json",
                     "plan_analyzed": analyzed, "plan": plan_summary(plan)}
    return out


def mv_costs(conn, dsn_conn_factory) -> dict:
    """Materialized view yenileme süresi, depolama ve güncellik gösterimi."""
    out = {
        "refresh_plain": time_statement(conn, ["REFRESH MATERIALIZED VIEW reporting.mv_category_sales"]).to_dict(),
        "refresh_concurrently": time_statement(
            conn, ["REFRESH MATERIALIZED VIEW CONCURRENTLY reporting.mv_category_sales"]
        ).to_dict(),
        "storage_bytes": {
            "heap": fetch(conn, "SELECT pg_relation_size('reporting.mv_category_sales')")[0][0],
            "total_with_indexes": fetch(conn, "SELECT pg_total_relation_size('reporting.mv_category_sales')")[0][0],
            "unique_index": fetch(conn, "SELECT pg_relation_size('reporting.mv_category_sales_label_uq')")[0][0],
        },
        "rows": fetch(conn, "SELECT count(*) FROM reporting.mv_category_sales")[0][0],
    }
    # Güncellik: kaynakta (geri alınacak) bir değişiklik view'e hemen yansır, MV'ye yenilenene kadar yansımaz.
    tx = dsn_conn_factory()
    try:
        tx.autocommit = False
        item = fetch(tx, "SELECT s.order_id, s.order_item_id FROM dw.fact_sales s JOIN dw.fact_orders o USING (order_id) "
                         "WHERE o.order_status = 'delivered' ORDER BY s.order_id, s.order_item_id LIMIT 1")[0]
        before_view = fetch(tx, "SELECT sum(price) FROM reporting.v_sales_items WHERE in_sales_scope")[0][0]
        execute(tx, "UPDATE dw.fact_sales SET price = price + 1.00 WHERE order_id = %(o)s AND order_item_id = %(i)s",
                {"o": item[0], "i": item[1]})
        after_view = fetch(tx, "SELECT sum(price) FROM reporting.v_sales_items WHERE in_sales_scope")[0][0]
        mv_total = fetch(tx, "SELECT sum(product_sales) FROM reporting.mv_category_sales")[0][0]
        tx.rollback()
    finally:
        tx.close()
    out["freshness_demo"] = {
        "change": "Bir teslim edilmiş kalemin fiyatı +1.00 (işlem içinde, sonra ROLLBACK)",
        "view_total_before": before_view,
        "view_total_after_change": after_view,
        "mv_total_without_refresh": mv_total,
        "mv_reflects_change": mv_total == after_view,
    }
    out["freshness_rule"] = (
        "MV, son REFRESH anındaki veriyi gösterir. Projede ETL işleminin sonunda ve sp_refresh_reports() ile yenilenir; "
        "son yenileme zamanı meta.etl_runs / meta.report_refresh_runs içinde."
    )
    return out
