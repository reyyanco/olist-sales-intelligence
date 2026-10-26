-- Analiz: tekrar satın alma oranı. reporting.v_repeat_purchase
-- Tanım: docs/metric_definitions.md 7. bölüm.
--
-- Kurallar:
-- - Birim customer_unique_id (customer_id siparişe özgü olduğu için kullanılmaz).
-- - Kapsam: satış kapsamındaki (delivered) siparişler.
-- - Tekrar eden müşteri: ilk siparişinden FARKLI bir order_id ile en az bir siparişi daha olan kişi.
--   EXISTS ile yazıldı: ikinci sipariş bulunduğu anda arama durur (semi-join); müşteri başına tüm
--   siparişlerin sayılmasına gerek yoktur. Sonuç count(DISTINCT order_id) >= 2 ile aynıdır.
-- - İlk sipariş: en erken purchase_ts, eşitlikte küçük order_id (deterministik).
-- - Kohort = ilk satın alma ayı. GROUPING SETS ile kohort satırları + genel toplam.
-- - Oran payda 0 ise NULL.

CREATE VIEW reporting.v_repeat_purchase AS
WITH first_orders AS (
    SELECT DISTINCT ON (customer_unique_id)
           customer_unique_id, order_id AS first_order_id, purchase_month AS cohort_month
    FROM reporting.v_orders
    WHERE in_sales_scope
    ORDER BY customer_unique_id, purchase_ts, order_id
), flagged AS (
    SELECT f.customer_unique_id,
           f.cohort_month,
           EXISTS (
               SELECT 1
               FROM reporting.v_orders o
               WHERE o.in_sales_scope
                 AND o.customer_unique_id = f.customer_unique_id
                 AND o.order_id <> f.first_order_id
           ) AS is_repeat
    FROM first_orders f
)
SELECT
    CASE WHEN GROUPING(cohort_month) = 1 THEN 'total' ELSE 'cohort' END AS grouping_level,
    cohort_month,
    count(*)                                AS customer_count,
    count(*) FILTER (WHERE is_repeat)       AS repeat_customer_count,
    round(count(*) FILTER (WHERE is_repeat)::numeric / NULLIF(count(*), 0), 4) AS repeat_purchase_rate
FROM flagged
GROUP BY GROUPING SETS ((cohort_month), ());

COMMENT ON VIEW reporting.v_repeat_purchase IS
    'customer_unique_id bazında tekrar satın alma oranı (EXISTS); ilk satın alma ayı kohortları ve toplam';
