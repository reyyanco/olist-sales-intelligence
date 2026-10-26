"""Şemanın boş bir veritabanında sıfırdan kurulduğunu doğrular."""

from __future__ import annotations

import uuid
from dataclasses import replace

from sqlalchemy import inspect, text

from etl.db import create_db_engine
from etl.sql_runner import apply_sql_files, discover_sql_files
from tests.conftest import SQL_DIR

EXPECTED_TABLES = {
    "staging": {
        "customers", "geolocation", "orders", "order_items", "order_payments",
        "order_reviews", "products", "sellers", "category_translation",
    },
    "dw": {"dim_customer", "dim_product", "dim_seller", "dim_date", "fact_sales", "fact_orders", "fact_payments"},
    "meta": {"schema_migrations", "etl_runs", "etl_run_files", "etl_run_checks", "etl_rejected_rows", "report_refresh_runs"},
    "reporting": {"monthly_summary", "state_region"},
}
EXPECTED_VIEWS = {
    "v_orders", "v_sales_items", "v_customer_purchases", "v_rfm_observation", "v_customer_rfm_base", "v_sales_kpis",
    "v_order_payment_differences", "v_monthly_sales_growth", "v_delivery_performance", "v_repeat_purchase",
    "v_dashboard_items", "v_dashboard_orders", "v_data_coverage", "v_data_freshness", "v_dashboard_categories",
    "v_dashboard_states", "v_sales_observation_months",
}


def test_schema_installs_on_empty_database(test_settings, admin_engine):
    name = f"olist_schema_{uuid.uuid4().hex[:8]}_test"
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_db_engine(replace(test_settings, database=name))
    try:
        with engine.connect() as conn:
            assert conn.execute(
                text("SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema')")
            ).scalar_one() == 0

        applied = apply_sql_files(engine, SQL_DIR)
        assert [f.name for f in applied] == [f.name for f in discover_sql_files(SQL_DIR)]

        insp = inspect(engine)
        for schema, tables in EXPECTED_TABLES.items():
            assert set(insp.get_table_names(schema=schema)) == tables
        assert set(insp.get_view_names(schema="reporting")) == EXPECTED_VIEWS
        assert sorted(insp.get_materialized_view_names(schema="reporting")) == ["mv_category_sales", "mv_monthly_sales"]

        assert insp.get_pk_constraint("fact_sales", schema="dw")["constrained_columns"] == ["order_id", "order_item_id"]
        assert insp.get_pk_constraint("fact_orders", schema="dw")["constrained_columns"] == ["order_id"]
        assert insp.get_pk_constraint("fact_payments", schema="dw")["constrained_columns"] == ["order_id", "payment_sequential"]
        fk_targets = {fk["referred_table"] for fk in insp.get_foreign_keys("fact_sales", schema="dw")}
        assert fk_targets == {"fact_orders", "dim_product", "dim_seller", "dim_date"}

        # Para kolonları NUMERIC(12,2)
        with engine.connect() as conn:
            money = conn.execute(
                text(
                    "SELECT table_name, column_name, data_type, numeric_precision, numeric_scale "
                    "FROM information_schema.columns WHERE table_schema = 'dw' "
                    "AND column_name IN ('price', 'freight_value', 'product_value', 'payment_value')"
                )
            ).all()
        assert money and all((r.data_type, r.numeric_precision, r.numeric_scale) == ("numeric", 12, 2) for r in money)

        # İkinci uygulama hiçbir şey yapmaz
        assert apply_sql_files(engine, SQL_DIR) == []
    finally:
        engine.dispose()
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
