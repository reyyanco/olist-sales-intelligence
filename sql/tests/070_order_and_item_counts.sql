-- Sipariş ve kalem sayıları AYRI doğrulanır; kalem tutarı aynı iş kapsamında (tüm durumlar ve
-- teslim edilmiş siparişler) kabul edilen kaynak kalemleriyle fact_sales arasında karşılaştırılır.
-- Sonuç satırı = uyumsuzluk.
WITH removed AS (
    SELECT source_table, source_row FROM meta.etl_rejected_rows WHERE run_id = meta.current_run_id()
), src_orders AS (
    SELECT o.order_id, o.order_status FROM staging.orders o
    WHERE NOT EXISTS (SELECT 1 FROM removed r WHERE r.source_table = 'orders' AND r.source_row = o._row_id)
), src_items AS (
    SELECT i.order_id, i.price::numeric(12,2) AS price, i.freight_value::numeric(12,2) AS freight_value
    FROM staging.order_items i
    WHERE NOT EXISTS (SELECT 1 FROM removed r WHERE r.source_table = 'order_items' AND r.source_row = i._row_id)
), comparisons AS (
    SELECT 'order_count_all' AS check_name,
           (SELECT count(*) FROM src_orders)::numeric AS source_value,
           (SELECT count(*) FROM dw.fact_orders)::numeric AS dw_value
    UNION ALL SELECT 'order_count_delivered',
           (SELECT count(*) FROM src_orders WHERE order_status = 'delivered'),
           (SELECT count(*) FROM dw.fact_orders WHERE order_status = 'delivered')
    UNION ALL SELECT 'item_count_all',
           (SELECT count(*) FROM src_items),
           (SELECT count(*) FROM dw.fact_sales)
    UNION ALL SELECT 'item_count_delivered',
           (SELECT count(*) FROM src_items i JOIN src_orders o USING (order_id) WHERE o.order_status = 'delivered'),
           (SELECT count(*) FROM dw.fact_sales s JOIN dw.fact_orders o USING (order_id) WHERE o.order_status = 'delivered')
    UNION ALL SELECT 'item_price_total_all',
           (SELECT sum(price) FROM src_items),
           (SELECT sum(price) FROM dw.fact_sales)
    UNION ALL SELECT 'item_freight_total_all',
           (SELECT sum(freight_value) FROM src_items),
           (SELECT sum(freight_value) FROM dw.fact_sales)
    UNION ALL SELECT 'item_price_total_delivered',
           (SELECT sum(i.price) FROM src_items i JOIN src_orders o USING (order_id) WHERE o.order_status = 'delivered'),
           (SELECT sum(s.price) FROM dw.fact_sales s JOIN dw.fact_orders o USING (order_id) WHERE o.order_status = 'delivered')
)
SELECT check_name, source_value, dw_value
FROM comparisons
WHERE source_value IS DISTINCT FROM dw_value;
