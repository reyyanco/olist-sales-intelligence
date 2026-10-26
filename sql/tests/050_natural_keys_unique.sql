-- Doğal anahtar tekilliği: KABUL EDİLEN staging satırlarında her doğal anahtar tam bir kez geçmeli
-- ve çelişkili anahtarlardan hiçbiri dw'ye girmemiş olmalı. Sonuç satırı = ihlal.
WITH removed AS (
    SELECT source_table, source_row FROM meta.etl_rejected_rows WHERE run_id = meta.current_run_id()
), conflicts AS (
    SELECT source_table, natural_key FROM meta.etl_rejected_rows
    WHERE run_id = meta.current_run_id() AND 'conflicting_key' = ANY (reasons)
), accepted_keys AS (
    SELECT 'customers' AS source_table, customer_id AS natural_key FROM staging.customers s
    WHERE NOT EXISTS (SELECT 1 FROM removed r WHERE r.source_table = 'customers' AND r.source_row = s._row_id)
    UNION ALL SELECT 'products', product_id FROM staging.products s
    WHERE NOT EXISTS (SELECT 1 FROM removed r WHERE r.source_table = 'products' AND r.source_row = s._row_id)
    UNION ALL SELECT 'sellers', seller_id FROM staging.sellers s
    WHERE NOT EXISTS (SELECT 1 FROM removed r WHERE r.source_table = 'sellers' AND r.source_row = s._row_id)
    UNION ALL SELECT 'orders', order_id FROM staging.orders s
    WHERE NOT EXISTS (SELECT 1 FROM removed r WHERE r.source_table = 'orders' AND r.source_row = s._row_id)
    UNION ALL SELECT 'order_items', order_id || ':' || order_item_id FROM staging.order_items s
    WHERE NOT EXISTS (SELECT 1 FROM removed r WHERE r.source_table = 'order_items' AND r.source_row = s._row_id)
    UNION ALL SELECT 'order_payments', order_id || ':' || payment_sequential FROM staging.order_payments s
    WHERE NOT EXISTS (SELECT 1 FROM removed r WHERE r.source_table = 'order_payments' AND r.source_row = s._row_id)
    UNION ALL SELECT 'order_reviews', review_id || ':' || order_id FROM staging.order_reviews s
    WHERE NOT EXISTS (SELECT 1 FROM removed r WHERE r.source_table = 'order_reviews' AND r.source_row = s._row_id)
)
SELECT source_table, natural_key, count(*) AS accepted_rows, 'duplicate_accepted_key' AS problem
FROM accepted_keys GROUP BY source_table, natural_key HAVING count(*) > 1
UNION ALL
SELECT a.source_table, a.natural_key, 1, 'conflicting_key_accepted'
FROM accepted_keys a JOIN conflicts c USING (source_table, natural_key);
