"""Performans deneyleri: python -m perf [--rebuild] [--only E1_customer_history,load,...]

Deneyler ayrı bir veritabanında (olist_perf) çalışır; bu veritabanı gerçek data/raw dosyalarından aynı
yükleme hattıyla kurulur. Ana veritabanına (olist) dokunulmaz.
Çıktılar: docs/perf/results/*.json (ham ölçümler), docs/perf/plans/*.json (EXPLAIN), docs/perf/summary.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
from dataclasses import replace
from pathlib import Path

import psycopg2

from etl.db import create_db_engine
from etl.pipeline import run_pipeline
from etl.settings import load_settings
from etl.sql_runner import apply_sql_files
from perf import dashboard_queries, experiments, load_compare, partition
from perf.harness import MEASURED_RUNS, QUERY_TIMEOUT_MS, WARMUP_RUNS, execute, fetch, save_json

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = PROJECT_ROOT / "sql"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PERF_DB = "olist_perf"
DW_TABLES = ["dw.dim_customer", "dw.dim_product", "dw.dim_seller", "dw.dim_date",
             "dw.fact_orders", "dw.fact_sales", "dw.fact_payments"]

log = logging.getLogger("perf")


def connect(settings, dbname: str):
    conn = psycopg2.connect(host=settings.host, port=settings.port, user=settings.user, password=settings.password,
                            dbname=dbname, application_name="olist-perf",
                            options=f"-c statement_timeout={QUERY_TIMEOUT_MS}")
    conn.autocommit = True
    return conn


def rebuild(settings) -> dict:
    admin = connect(settings, "postgres")
    try:
        execute(admin, f'DROP DATABASE IF EXISTS "{PERF_DB}" WITH (FORCE)')
        execute(admin, f'CREATE DATABASE "{PERF_DB}"')
    finally:
        admin.close()
    engine = create_db_engine(replace(settings, database=PERF_DB))
    try:
        apply_sql_files(engine, SQL_DIR)
        result = run_pipeline(engine, RAW_DIR)
    finally:
        engine.dispose()
    return {"run_id": str(result.run_id), "status": result.status, "duration_seconds": result.duration_seconds}


def baseline_state(conn) -> dict:
    """PK ve UNIQUE indeksler korunur; dw/reporting içindeki diğer tüm indeksler kaldırılır; istatistikler bir kez güncellenir."""
    extra = fetch(conn, """
        SELECT n.nspname || '.' || c.relname, pg_get_indexdef(i.indexrelid)
        FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('dw', 'reporting') AND NOT i.indisunique AND NOT i.indisprimary ORDER BY 1""")
    for name, _ in extra:
        execute(conn, f"DROP INDEX {name}")
    for t in DW_TABLES + ["reporting.mv_monthly_sales", "reporting.mv_category_sales"]:
        execute(conn, f"VACUUM (ANALYZE) {t}")
    kept = fetch(conn, """
        SELECT n.nspname || '.' || c.relname, pg_get_indexdef(i.indexrelid)
        FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('dw', 'reporting') ORDER BY 1""")
    return {"dropped_indexes": [{"name": n, "definition": d} for n, d in extra],
            "kept_indexes": [{"name": n, "definition": d} for n, d in kept],
            "statistics": "VACUUM (ANALYZE) dw tabloları ve reporting MV'leri, deneylerden önce bir kez"}


def environment(conn, settings) -> dict:
    mem_kb = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                mem_kb = int(line.split()[1])
    except OSError:
        pass
    run = fetch(conn, "SELECT run_id, duration_seconds, finished_at FROM meta.etl_runs WHERE status = 'succeeded' "
                      "ORDER BY finished_at DESC LIMIT 1")
    files = fetch(conn, "SELECT file_name, file_sha256, source_rows FROM meta.etl_run_files WHERE run_id = %(r)s ORDER BY 1",
                  {"r": run[0][0]}) if run else []
    return {
        "measured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "data": "GERÇEK Olist verisi (data/raw), olist_perf veritabanına yükleme hattıyla yüklendi",
        "database": PERF_DB,
        "postgres_version": fetch(conn, "SELECT version()")[0][0],
        "settings": {n: f"{s}{u or ''}" for n, s, u in fetch(conn,
            "SELECT name, setting, unit FROM pg_settings WHERE name IN ('shared_buffers','work_mem','effective_cache_size',"
            "'random_page_cost','max_parallel_workers_per_gather','jit','default_statistics_target','maintenance_work_mem') ORDER BY 1")},
        "container_cpu_count": os.cpu_count(),
        "container_mem_total_kb": mem_kb,
        "database_size_bytes": fetch(conn, "SELECT pg_database_size(current_database())")[0][0],
        "row_counts": {t: fetch(conn, f"SELECT count(*) FROM {t}")[0][0] for t in DW_TABLES},
        "etl_run": {"run_id": run[0][0], "duration_seconds": run[0][1], "finished_at": run[0][2]} if run else None,
        "source_files": [{"file": f, "sha256": s, "rows": r} for f, s, r in files],
        "measurement_method": (
            f"{WARMUP_RUNS} ısınma çalışması (ölçüme katılmaz) + {MEASURED_RUNS} ölçüm; istemcide execute+fetchall "
            "süresi (time.perf_counter). Önbellek temizlenmedi: tüm sorgu ölçümleri sıcak önbellek koşulundadır. "
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ayrı çalıştırıldı. Yazma/yenileme/yükleme ölçümleri: 1 ısınma + 5 ölçüm. "
            f"Sorgu başına statement_timeout={QUERY_TIMEOUT_MS} ms; aşan ölçüm 'timed_out' kaydedilir ve planı "
            "yalnızca EXPLAIN (çalıştırmadan) ile alınır."
        ),
        "client": "psycopg2, aynı Docker ağı üzerinden (db konteyneri), autocommit",
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="python -m perf")
    parser.add_argument("--rebuild", action="store_true", help=f"{PERF_DB} veritabanını data/raw'dan yeniden kur")
    parser.add_argument("--only", default="", help="virgülle ayrılmış deney kimlikleri (ör. E1_customer_history,load)")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "docs" / "perf")
    args = parser.parse_args()
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    selected = lambda key: not only or key in only  # noqa: E731

    settings = load_settings()
    if PERF_DB == settings.database:
        raise SystemExit("PERF_DB ana veritabanıyla aynı olamaz")
    results_dir, plans_dir = args.out / "results", args.out / "plans"

    admin = connect(settings, "postgres")
    exists = bool(fetch(admin, "SELECT 1 FROM pg_database WHERE datname = %(d)s", {"d": PERF_DB}))
    admin.close()
    if args.rebuild or not exists:
        log.info("%s gerçek veriden kuruluyor...", PERF_DB)
        save_json(results_dir / "rebuild.json", rebuild(settings))

    conn = connect(settings, PERF_DB)
    # Kısmi çalışma (--only) tam çalışmanın başlangıç/ortam kayıtlarının üzerine yazmaz.
    prefix = "partial_" if only else ""
    try:
        save_json(results_dir / f"{prefix}baseline_state.json", baseline_state(conn))
        save_json(results_dir / f"{prefix}environment.json", environment(conn, settings))
        params = experiments.choose_params(conn)
        save_json(results_dir / f"{prefix}parameters.json", {"values": params, "selection_sql": experiments.PARAM_QUERIES})

        if selected("catalog"):
            log.info("Başlangıç kataloğu ölçülüyor")
            save_json(results_dir / "catalog.json", experiments.run_catalog(conn, plans_dir))
        for exp in experiments.build_experiments(conn, params):
            if selected(exp.id):
                log.info("Deney: %s", exp.id)
                save_json(results_dir / f"{exp.id}.json", experiments.run_experiment(conn, exp, plans_dir))
        if selected("mv"):
            log.info("Materialized view maliyetleri")
            save_json(results_dir / "mv_costs.json", experiments.mv_costs(conn, lambda: connect(settings, PERF_DB)))
        if selected("dashboard"):
            log.info("D1: dashboard sorguları (ek indeks yok / model indeksleri)")
            engine = create_db_engine(replace(settings, database=PERF_DB))
            try:
                apply_sql_files(engine, SQL_DIR)  # yeni raporlama fonksiyonları olist_perf'e de uygulanır
            finally:
                engine.dispose()
            save_json(results_dir / "D1_dashboard_queries.json", dashboard_queries.run(conn, plans_dir))
        if selected("partition"):
            log.info("Partitioning deneyi (yalıtılmış)")
            save_json(results_dir / "P1_partitioning.json", partition.run(conn, plans_dir))
    finally:
        conn.close()

    if selected("load"):
        log.info("COPY / to_sql karşılaştırması")
        engine = create_db_engine(replace(settings, database=PERF_DB))
        try:
            save_json(results_dir / "L1_load_comparison.json", load_compare.run(engine, RAW_DIR))
        finally:
            engine.dispose()

    from perf.summary import write_summary
    write_summary(results_dir, args.out / "summary.md")
    log.info("Bitti: %s", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
