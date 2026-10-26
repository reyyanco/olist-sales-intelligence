-- reporting.v_repeat_purchase: DISTINCT ON + EXISTS yerine tek geçişli toplama.
--
-- Gerekçe (docs/performance.md, E4; gerçek veri):
-- - EXISTS seçim listesinde bir SubPlan olarak müşteri başına çalışır. dim_customer(customer_unique_id)
--   indeksi olmadan 60 s zaman sınırını aşar; indeksle medyan 1.517,952 ms.
-- - Tek geçişli toplama indekssiz medyan 405,891 ms ve sonucu birebir aynıdır (MD5 eşit, A ve B çalışmaları).
-- Tanım değişmez: tekrar eden müşteri = kapsamda en az 2 FARKLI siparişi olan customer_unique_id;
-- kohort = ilk satın alma ayı (en erken satın almanın ayı = min(purchase_month)).
-- Kolon adları, sırası ve tipleri önceki tanımla aynıdır (CREATE OR REPLACE VIEW koşulu).
CREATE OR REPLACE VIEW reporting.v_repeat_purchase AS
WITH customers AS (
    SELECT customer_unique_id,
           min(purchase_month)       AS cohort_month,
           count(DISTINCT order_id)  AS orders
    FROM reporting.v_orders
    WHERE in_sales_scope
    GROUP BY customer_unique_id
)
SELECT
    CASE WHEN GROUPING(cohort_month) = 1 THEN 'total' ELSE 'cohort' END AS grouping_level,
    cohort_month,
    count(*)                                  AS customer_count,
    count(*) FILTER (WHERE orders >= 2)       AS repeat_customer_count,
    round(count(*) FILTER (WHERE orders >= 2)::numeric / NULLIF(count(*), 0), 4) AS repeat_purchase_rate
FROM customers
GROUP BY GROUPING SETS ((cohort_month), ());

COMMENT ON VIEW reporting.v_repeat_purchase IS
    'customer_unique_id bazında tekrar satın alma oranı (tek geçişli toplama); ilk satın alma ayı kohortları ve toplam';
