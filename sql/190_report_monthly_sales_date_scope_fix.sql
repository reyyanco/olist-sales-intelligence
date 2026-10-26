-- DÜZELTME: reporting.fn_monthly_sales tarih kapsamı (Aşama 8 doğrulaması).
--
-- Hata (sql/160): aylık tutarlar tarih filtresi UYGULANMADAN tam aylar üzerinden toplanıyordu. Ay ortasında
-- başlayan/biten bir aralıkta grafik seçilmeyen günleri de içeriyor ve KPI ile tutmuyordu. Gerçek veride
-- 2018-01-15..2018-03-10: KPI 1.657.285,69 BRL / 12.891 sipariş; grafik toplamı 2.704.438,38 / 20.627.
--
-- Yeni kurallar:
-- - product_sales, order_count, customer_count, avg_basket_value: seçili tarih aralığı + eyalet + kategori
--   filtreleriyle (fn_overview_kpis ile AYNI kapsam; aylık tutarların toplamı KPI'ya eşittir).
-- - Büyüme yalnızca TAM aylar için, tam ay değerlerinden (eyalet/kategori filtreli) hesaplanır:
--     kısmi ay                     -> growth_rate NULL, growth_status 'partial_month'
--     önceki ay yok                -> NULL, 'no_previous_month'
--     önceki tam ay değeri 0       -> NULL, 'previous_month_zero'
--     diğer                        -> 'computed'
--   prev_product_sales = önceki ayın TAM ay değeri. Tam ayda gösterilen tutar tam ay değeriyle aynıdır.
-- - Kısmi ay: ay, seçili aralık veya veri kapsamı tarafından kesiliyor.
-- İmza ve dönüş kolonları değişmez.
CREATE OR REPLACE FUNCTION reporting.fn_monthly_sales(p_from date, p_to date, p_states text[] DEFAULT NULL, p_categories text[] DEFAULT NULL)
RETURNS TABLE (month_start date, product_sales numeric(14,2), order_count bigint, customer_count bigint,
               avg_basket_value numeric(14,2), prev_product_sales numeric(14,2), growth_rate numeric(10,4),
               growth_status text, is_partial_month boolean)
LANGUAGE sql STABLE AS $$
    WITH cov AS (
        SELECT first_purchase_date, last_purchase_date, first_month, last_month FROM reporting.v_data_coverage
    ), months AS (
        SELECT generate_series(cov.first_month, cov.last_month, interval '1 month')::date AS month_start FROM cov
    ), filtered AS (
        SELECT i.* FROM reporting.v_dashboard_items i
        WHERE (p_states IS NULL OR i.customer_state = ANY (p_states))
          AND (p_categories IS NULL OR i.category_label = ANY (p_categories))
    ), full_month AS (           -- büyüme için: tarih filtresi yok
        SELECT purchase_month, sum(price) AS product_sales FROM filtered GROUP BY purchase_month
    ), in_range AS (             -- gösterilen değerler: tarih filtresi var (KPI ile aynı kapsam)
        SELECT purchase_month, sum(price) AS product_sales, count(DISTINCT order_id) AS order_count,
               count(DISTINCT customer_unique_id) AS customer_count
        FROM filtered
        WHERE purchase_date_key BETWEEN to_char(p_from, 'YYYYMMDD')::int AND to_char(p_to, 'YYYYMMDD')::int
        GROUP BY purchase_month
    ), series AS (
        SELECT m.month_start,
               COALESCE(r.product_sales, 0)  AS product_sales,
               COALESCE(r.order_count, 0)    AS order_count,
               COALESCE(r.customer_count, 0) AS customer_count,
               COALESCE(f.product_sales, 0)  AS full_sales,
               LAG(COALESCE(f.product_sales, 0)) OVER (ORDER BY m.month_start) AS prev_full_sales,
               m.month_start < GREATEST(p_from, cov.first_purchase_date)
                 OR (m.month_start + interval '1 month' - interval '1 day')::date > LEAST(p_to, cov.last_purchase_date)
                 AS is_partial
        FROM months m
        CROSS JOIN cov
        LEFT JOIN in_range r ON r.purchase_month = m.month_start
        LEFT JOIN full_month f ON f.purchase_month = m.month_start
    )
    SELECT s.month_start,
           s.product_sales::numeric(14,2),
           s.order_count,
           s.customer_count,
           round(s.product_sales / NULLIF(s.order_count, 0), 2),
           s.prev_full_sales::numeric(14,2),
           CASE WHEN s.is_partial OR s.prev_full_sales IS NULL OR s.prev_full_sales = 0 THEN NULL
                ELSE round((s.full_sales - s.prev_full_sales) / s.prev_full_sales, 4) END,
           CASE WHEN s.is_partial THEN 'partial_month'
                WHEN s.prev_full_sales IS NULL THEN 'no_previous_month'
                WHEN s.prev_full_sales = 0 THEN 'previous_month_zero'
                ELSE 'computed' END,
           s.is_partial
    FROM series s
    WHERE s.month_start BETWEEN date_trunc('month', p_from)::date AND date_trunc('month', p_to)::date
    ORDER BY s.month_start
$$;

-- CREATE OR REPLACE mevcut yetkileri korur; açıklık için yeniden verilir.
REVOKE EXECUTE ON FUNCTION reporting.fn_monthly_sales(date, date, text[], text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reporting.fn_monthly_sales(date, date, text[], text[]) TO olist_reporting_reader;
