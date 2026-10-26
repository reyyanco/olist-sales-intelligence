-- Raporlama toplamları, KABUL EDİLEN kaynak satırlarından doğrudan hesaplanan toplamlara eşit olmalı
-- (çoğalma yok). Kabul = bu çalışmada meta.etl_rejected_rows içinde olmayan staging satırı.
-- Sonuç satırı = uyumsuz metrik.
WITH removed AS (
    SELECT source_table, source_row FROM meta.etl_rejected_rows WHERE run_id = meta.current_run_id()
), orders AS (
    SELECT o.order_id, o.order_status FROM staging.orders o
    WHERE NOT EXISTS (SELECT 1 FROM removed r WHERE r.source_table = 'orders' AND r.source_row = o._row_id)
), items AS (
    SELECT i.order_id, i.price::numeric(12,2) AS price, i.freight_value::numeric(12,2) AS freight_value FROM staging.order_items i
    WHERE NOT EXISTS (SELECT 1 FROM removed r WHERE r.source_table = 'order_items' AND r.source_row = i._row_id)
), payments AS (
    SELECT p.order_id, p.payment_value::numeric(12,2) AS payment_value FROM staging.order_payments p
    WHERE NOT EXISTS (SELECT 1 FROM removed r WHERE r.source_table = 'order_payments' AND r.source_row = p._row_id)
), expected AS (
    SELECT
        (SELECT sum(i.price) FROM items i JOIN orders o USING (order_id) WHERE o.order_status = 'delivered')         AS product_sales,
        (SELECT sum(i.freight_value) FROM items i JOIN orders o USING (order_id) WHERE o.order_status = 'delivered') AS freight_amount,
        (SELECT sum(p.payment_value) FROM payments p JOIN orders o USING (order_id) WHERE o.order_status = 'delivered') AS payment_amount,
        (SELECT count(*) FROM orders WHERE order_status = 'delivered')                                                AS order_count
), monthly AS (
    SELECT sum(product_sales) AS product_sales, sum(freight_amount) AS freight_amount,
           sum(payment_amount) AS payment_amount, sum(order_count) AS order_count
    FROM reporting.mv_monthly_sales
), kpis AS (
    SELECT product_sales, freight_amount, payment_amount, order_count FROM reporting.v_sales_kpis
), items_view AS (
    SELECT sum(price) AS product_sales, sum(freight_value) AS freight_amount
    FROM reporting.v_sales_items WHERE in_sales_scope
)
SELECT metric, source, expected_value, actual_value
FROM (
    SELECT 'product_sales' AS metric, 'mv_monthly_sales' AS source, e.product_sales AS expected_value, m.product_sales AS actual_value FROM expected e, monthly m
    UNION ALL SELECT 'freight_amount', 'mv_monthly_sales', e.freight_amount, m.freight_amount FROM expected e, monthly m
    UNION ALL SELECT 'payment_amount', 'mv_monthly_sales', e.payment_amount, m.payment_amount FROM expected e, monthly m
    UNION ALL SELECT 'order_count', 'mv_monthly_sales', e.order_count, m.order_count FROM expected e, monthly m
    UNION ALL SELECT 'product_sales', 'v_sales_kpis', e.product_sales, k.product_sales FROM expected e, kpis k
    UNION ALL SELECT 'freight_amount', 'v_sales_kpis', e.freight_amount, k.freight_amount FROM expected e, kpis k
    UNION ALL SELECT 'payment_amount', 'v_sales_kpis', e.payment_amount, k.payment_amount FROM expected e, kpis k
    UNION ALL SELECT 'order_count', 'v_sales_kpis', e.order_count, k.order_count FROM expected e, kpis k
    UNION ALL SELECT 'product_sales', 'v_sales_items', e.product_sales, v.product_sales FROM expected e, items_view v
    UNION ALL SELECT 'freight_amount', 'v_sales_items', e.freight_amount, v.freight_amount FROM expected e, items_view v
) AS checks
WHERE expected_value IS DISTINCT FROM actual_value;
