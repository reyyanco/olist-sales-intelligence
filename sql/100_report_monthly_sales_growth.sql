-- Analiz: aylık ürün satış tutarı ve önceki aya göre büyüme.
-- Metrikler: docs/metric_definitions.md (satış kapsamı = delivered, ay = satın alma ayı).
--
-- Kurallar:
-- - Ay listesi dw.dim_date'ten gelir; satışı olmayan aylar 0 tutarla görünür (boşluk bırakılmaz).
-- - Önceki ay değeri LAG ile ayların takvim sırasına göre alınır.
-- - growth_rate = (bu ay - önceki ay) / önceki ay, 4 ondalık.
--     * İlk ay (önceki ay yok)       -> growth_rate NULL, growth_status 'no_previous_month'
--     * Önceki ay 0 (sıfır payda)    -> growth_rate NULL, growth_status 'previous_month_zero'
--     * Diğer                        -> growth_status 'computed'
--   product_sales_change (fark) her zaman tanımlıdır; sıfıra bölme yapılmaz, sonsuz büyüme uydurulmaz.
-- - Veri setinin ilk ve son ayları kısmi olabilir; dim_date kapsamı veriden üretildiği için bu aylar
--   da listelenir. Kısmi ay yorumu analiz aşamasının kararıdır.

CREATE VIEW reporting.v_monthly_sales_growth AS
WITH months AS (
    SELECT DISTINCT month_start FROM dw.dim_date
), sales AS (
    SELECT purchase_month,
           count(*)                           AS order_count,
           count(DISTINCT customer_unique_id) AS customer_count,
           sum(item_count)                    AS item_count,
           sum(product_value)                 AS product_sales,
           sum(freight_value)                 AS freight_amount,
           sum(payment_value)                 AS payment_amount
    FROM reporting.v_orders
    WHERE in_sales_scope
    GROUP BY purchase_month
), filled AS (
    SELECT m.month_start,
           COALESCE(s.order_count, 0)       AS order_count,
           COALESCE(s.customer_count, 0)    AS customer_count,
           COALESCE(s.item_count, 0)        AS item_count,
           COALESCE(s.product_sales, 0)     AS product_sales,
           COALESCE(s.freight_amount, 0)    AS freight_amount,
           COALESCE(s.payment_amount, 0)    AS payment_amount
    FROM months m
    LEFT JOIN sales s ON s.purchase_month = m.month_start
), lagged AS (
    SELECT f.*, LAG(f.product_sales) OVER (ORDER BY f.month_start) AS prev_product_sales
    FROM filled f
)
SELECT
    month_start,
    EXTRACT(YEAR FROM month_start)::int  AS year,
    EXTRACT(MONTH FROM month_start)::int AS month,
    order_count,
    customer_count,
    item_count,
    product_sales::numeric(14,2)   AS product_sales,
    freight_amount::numeric(14,2)  AS freight_amount,
    payment_amount::numeric(14,2)  AS payment_amount,
    round(product_sales / NULLIF(order_count, 0), 2) AS avg_basket_value,
    prev_product_sales::numeric(14,2) AS prev_product_sales,
    (product_sales - prev_product_sales)::numeric(14,2) AS product_sales_change,
    CASE
        WHEN prev_product_sales IS NULL OR prev_product_sales = 0 THEN NULL
        ELSE round((product_sales - prev_product_sales) / prev_product_sales, 4)
    END AS growth_rate,
    CASE
        WHEN prev_product_sales IS NULL THEN 'no_previous_month'
        WHEN prev_product_sales = 0 THEN 'previous_month_zero'
        ELSE 'computed'
    END AS growth_status
FROM lagged;

COMMENT ON VIEW reporting.v_monthly_sales_growth IS
    'Aylık ürün satış tutarı ve önceki aya göre büyüme; satışsız aylar dim_date ile 0; önceki ay 0 ise growth_rate NULL';
