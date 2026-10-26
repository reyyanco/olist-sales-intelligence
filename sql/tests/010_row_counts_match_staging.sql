-- Satır sayısı mutabakatı: staging = dw (kabul) + reddedilen + tekrar olarak ayıklanan.
-- Ret/tekrar sayıları içinde bulunulan çalışmanın (meta.current_run_id()) kayıtlarından alınır.
-- Sonuç satırı = uyumsuzluk.
WITH removed AS (
    SELECT source_table, count(*) AS n
    FROM meta.etl_rejected_rows
    WHERE run_id = meta.current_run_id()
    GROUP BY source_table
), counts AS (
    SELECT 'customers' AS source_table, (SELECT count(*) FROM staging.customers) AS staging_rows, (SELECT count(*) FROM dw.dim_customer) AS dw_rows
    UNION ALL SELECT 'products', (SELECT count(*) FROM staging.products), (SELECT count(*) FROM dw.dim_product)
    UNION ALL SELECT 'sellers', (SELECT count(*) FROM staging.sellers), (SELECT count(*) FROM dw.dim_seller)
    UNION ALL SELECT 'orders', (SELECT count(*) FROM staging.orders), (SELECT count(*) FROM dw.fact_orders)
    UNION ALL SELECT 'order_items', (SELECT count(*) FROM staging.order_items), (SELECT count(*) FROM dw.fact_sales)
    UNION ALL SELECT 'order_payments', (SELECT count(*) FROM staging.order_payments), (SELECT count(*) FROM dw.fact_payments)
)
SELECT c.source_table, c.staging_rows, COALESCE(r.n, 0) AS removed_rows, c.dw_rows
FROM counts c
LEFT JOIN removed r USING (source_table)
WHERE c.staging_rows - COALESCE(r.n, 0) <> c.dw_rows;
