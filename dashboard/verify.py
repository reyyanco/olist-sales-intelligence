"""Gerçek veri doğrulaması: örnek filtrelerde dashboard'un gösterdiği KPI'lar, reporting fonksiyonlarını
KULLANMAYAN doğrudan SQL ile eşleşmeli. Kullanım: python -m dashboard.verify --output docs/dashboard_verification.json
(.\\scripts\\verify-dashboard.ps1). Yönetici bağlantısıyla çalışır (doğrudan SQL dw tablolarını okur)."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from streamlit.testing.v1 import AppTest

from dashboard import ui
from etl.db import create_db_engine
from etl.settings import load_settings

APP = str(Path(__file__).resolve().parent / "app.py")

# (ad, sayfa, widget değerleri)
SAMPLES = [
    ("default_coverage", "page_overview.py", {}),
    ("category_health_beauty", "page_overview.py", {"w_categories": ["health_beauty"]}),
    ("states_SP_RJ_2018H1", "page_overview.py",
     {"w_states": ["SP", "RJ"], "w_dates": (dt.date(2018, 1, 1), dt.date(2018, 6, 30))}),
    ("bed_bath_table_MG_2017", "page_overview.py",
     {"w_categories": ["bed_bath_table"], "w_states": ["MG"], "w_dates": (dt.date(2017, 1, 1), dt.date(2017, 12, 31))}),
    ("two_categories_2018_03", "page_overview.py",
     {"w_categories": ["health_beauty", "watches_gifts"], "w_dates": (dt.date(2018, 3, 1), dt.date(2018, 3, 31))}),
    ("delivery_state_BA_2017", "page_delivery.py",
     {"w_states": ["BA"], "w_dates": (dt.date(2017, 1, 1), dt.date(2017, 12, 31))}),
    ("customers_2017", "page_customers.py", {"w_dates": (dt.date(2017, 1, 1), dt.date(2017, 12, 31))}),
]

SALES_SQL = """
SELECT sum(s.price) AS product_sales, count(DISTINCT s.order_id) AS orders, count(DISTINCT c.customer_unique_id) AS customers
FROM dw.fact_sales s JOIN dw.fact_orders o ON o.order_id = s.order_id
JOIN dw.dim_customer c ON c.customer_id = o.customer_id JOIN dw.dim_product p ON p.product_id = s.product_id
WHERE o.order_status = 'delivered' AND o.purchase_ts >= :f AND o.purchase_ts < CAST(:t AS date) + 1
  AND (CAST(:states AS text[]) IS NULL OR c.state = ANY (CAST(:states AS text[])))
  AND (CAST(:cats AS text[]) IS NULL OR p.category_label = ANY (CAST(:cats AS text[])))"""

DELIVERY_SQL = """
SELECT round(avg(round(EXTRACT(EPOCH FROM (o.delivered_customer_ts - o.purchase_ts)) / 86400.0, 2)), 2) AS avg_days,
       count(o.delivered_customer_ts) AS measured,
       count(*) FILTER (WHERE o.delivered_customer_ts::date > o.estimated_delivery_date) AS late,
       count(*) AS orders
FROM dw.fact_orders o JOIN dw.dim_customer c ON c.customer_id = o.customer_id
WHERE o.order_status = 'delivered' AND o.purchase_ts >= :f AND o.purchase_ts < CAST(:t AS date) + 1
  AND (CAST(:states AS text[]) IS NULL OR c.state = ANY (CAST(:states AS text[])))"""

REPEAT_SQL = """
SELECT count(*) AS customers, count(*) FILTER (WHERE n >= 2) AS repeaters FROM (
  SELECT c.customer_unique_id, count(DISTINCT o.order_id) AS n
  FROM dw.fact_orders o JOIN dw.dim_customer c ON c.customer_id = o.customer_id
  WHERE o.order_status = 'delivered' AND o.purchase_ts >= :f AND o.purchase_ts < CAST(:t AS date) + 1
  GROUP BY c.customer_unique_id) x"""


def app_values(page: str, widgets: dict) -> dict:
    at = AppTest.from_file(APP, default_timeout=300)
    at.run()
    if page != "page_overview.py":
        at.switch_page(page).run()
    for key, value in widgets.items():
        w = at.multiselect(key=key) if key in ("w_states", "w_categories") else at.date_input(key=key)
        w.set_value(value)
        at.run()
    if at.exception or at.error:
        raise RuntimeError(f"Uygulama hatası: {[e.value for e in at.exception]} {[e.value for e in at.error]}")
    return {m.label: m.value for m in at.metric}


def direct_values(conn, page: str, widgets: dict, coverage: tuple[dt.date, dt.date]) -> dict:
    f, t = widgets.get("w_dates", coverage)
    p = {"f": f, "t": t, "states": widgets.get("w_states"), "cats": widgets.get("w_categories")}
    if page == "page_overview.py":
        r = conn.execute(text(SALES_SQL), p).mappings().one()
        basket = (r["product_sales"] / r["orders"]).quantize(Decimal("0.01")) if r["orders"] else None
        return {"Ürün satış tutarı": ui.fmt_brl(r["product_sales"]), "Sipariş sayısı": ui.fmt_int(r["orders"]),
                "Müşteri sayısı": ui.fmt_int(r["customers"]), "Ortalama sepet tutarı": ui.fmt_brl(basket)}
    if page == "page_delivery.py":
        r = conn.execute(text(DELIVERY_SQL), p).mappings().one()
        rate = (Decimal(r["late"]) / r["measured"]).quantize(Decimal("0.0001")) if r["measured"] else None
        return {"Ortalama teslimat süresi": f"{ui.fmt_decimal(r['avg_days'])} gün",
                "Geç teslimat oranı": ui.fmt_pct(rate, 2), "Ölçülen sipariş": ui.fmt_int(r["measured"]),
                "Teslim zamanı boş": ui.fmt_int(r["orders"] - r["measured"])}
    r = conn.execute(text(REPEAT_SQL), p).mappings().one()
    rate = (Decimal(r["repeaters"]) / r["customers"]).quantize(Decimal("0.0001")) if r["customers"] else None
    return {"Müşteri sayısı": ui.fmt_int(r["customers"]), "Tekrar eden müşteri": ui.fmt_int(r["repeaters"]),
            "Tekrar satın alma oranı": ui.fmt_pct(rate, 2)}


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m dashboard.verify")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = load_settings()
    engine = create_db_engine(settings)
    results = []
    with engine.connect() as conn:
        cov = conn.execute(text("SELECT min(purchase_ts)::date, max(purchase_ts)::date FROM dw.fact_orders "
                                "WHERE order_status = 'delivered'")).one()
        run = conn.execute(text("SELECT run_id::text, finished_at FROM meta.etl_runs WHERE status = 'succeeded' "
                                "ORDER BY finished_at DESC LIMIT 1")).one()
        for name, page, widgets in SAMPLES:
            app = app_values(page, widgets)
            direct = direct_values(conn, page, widgets, (cov[0], cov[1]))
            shown = {k: app.get(k) for k in direct}
            results.append({"sample": name, "page": page,
                            "filters": {k: [str(x) for x in v] if isinstance(v, (list, tuple)) else v for k, v in widgets.items()},
                            "app": shown, "direct_sql": direct, "match": shown == direct})
            print(f"{'OK ' if shown == direct else 'FARK'} {name}: {shown}")
    engine.dispose()
    doc = {"database": settings.database, "data": "GERÇEK Olist verisi", "etl_run_id": run[0],
           "etl_finished_at": str(run[1]), "coverage": [str(cov[0]), str(cov[1])],
           "verified_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "all_match": all(r["match"] for r in results), "samples": results}
    args.output.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if doc["all_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
