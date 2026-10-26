"""İsteğe bağlı, yalıtılmış partitioning deneyi (perf şeması; ana modele dokunmaz).

fact_orders'ın aynı kolonlarla iki kopyası: bölünmemiş (perf.orders_plain) ve purchase_ts'e göre yıllık
RANGE partition (perf.orders_part). İkisinde de indeks yok. Gerçek Olist hacmi (99.441 sipariş) kullanılır;
sentetik büyütme yapılmaz.
"""

from __future__ import annotations

from pathlib import Path

from perf.harness import execute, explain, fetch, measure, plan_summary, save_json

SETUP = [
    "CREATE SCHEMA IF NOT EXISTS perf",
    "DROP TABLE IF EXISTS perf.orders_plain, perf.orders_part CASCADE",
    "CREATE TABLE perf.orders_plain AS SELECT order_id, order_status, purchase_ts, product_value, payment_value FROM dw.fact_orders",
    "CREATE TABLE perf.orders_part (order_id text, order_status text, purchase_ts timestamp NOT NULL, "
    "product_value numeric(12,2), payment_value numeric(12,2)) PARTITION BY RANGE (purchase_ts)",
    "CREATE TABLE perf.orders_part_2016 PARTITION OF perf.orders_part FOR VALUES FROM ('2016-01-01') TO ('2017-01-01')",
    "CREATE TABLE perf.orders_part_2017 PARTITION OF perf.orders_part FOR VALUES FROM ('2017-01-01') TO ('2018-01-01')",
    "CREATE TABLE perf.orders_part_2018 PARTITION OF perf.orders_part FOR VALUES FROM ('2018-01-01') TO ('2019-01-01')",
    "CREATE TABLE perf.orders_part_default PARTITION OF perf.orders_part DEFAULT",
    "INSERT INTO perf.orders_part SELECT * FROM perf.orders_plain",
    "ANALYZE perf.orders_plain",
    "ANALYZE perf.orders_part",
]

QUERIES = {
    "one_month": (
        "SELECT order_status, count(*), sum(product_value) FROM {t} "
        "WHERE purchase_ts >= %(from)s AND purchase_ts < %(to)s GROUP BY order_status ORDER BY order_status",
        {"from": "2018-03-01", "to": "2018-04-01"},
    ),
    "all_rows": (
        "SELECT order_status, count(*), sum(product_value) FROM {t} GROUP BY order_status ORDER BY order_status",
        {},
    ),
}


def run(conn, plans_dir: Path) -> dict:
    for s in SETUP:
        execute(conn, s)
    out = {"setup_sql": SETUP, "row_counts": {}, "queries": {}}
    for t in ["perf.orders_plain", "perf.orders_part", "perf.orders_part_2016", "perf.orders_part_2017",
              "perf.orders_part_2018", "perf.orders_part_default"]:
        out["row_counts"][t] = fetch(conn, f"SELECT count(*) FROM {t}")[0][0]
    for qname, (template, params) in QUERIES.items():
        states = {}
        for label, table in [("plain", "perf.orders_plain"), ("partitioned", "perf.orders_part")]:
            sql = template.format(t=table)
            m = measure(conn, sql, params)
            plan = explain(conn, sql, params)
            save_json(plans_dir / f"P1_{qname}_{label}.json", plan)
            states[label] = {"sql": sql, "measurement": m.to_dict(), "plan_file": f"P1_{qname}_{label}.json",
                             "plan": plan_summary(plan)}
        states["result_equal"] = states["plain"]["measurement"]["result_md5"] == states["partitioned"]["measurement"]["result_md5"]
        states["median_speedup"] = round(states["plain"]["measurement"]["median_ms"] / states["partitioned"]["measurement"]["median_ms"], 2)
        out["queries"][qname] = {"params": params, **states}
    execute(conn, "DROP TABLE perf.orders_plain, perf.orders_part CASCADE")
    return out
