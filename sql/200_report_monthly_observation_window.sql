-- DÜZELTME: aylık raporların tarih kapsamı (reporting.v_monthly_sales_growth, reporting.monthly_summary,
-- reporting.fn_monthly_sales büyüme kuralı).
--
-- Sorun (Aşama 8 raporu): ay listesi dw.dim_date'ten geliyordu. dim_date teslimat metrikleri için tahmini
-- teslim tarihlerini de kapsar (sql/tests/040) ve gerçek veride 2018-11'e uzanır. Bu yüzden satış gözlemi
-- olmayan 2018-09..11 aylar "0 satış" gibi görünüyordu.
--
-- Satış gözlem aralığı (docs/metric_definitions.md, bölüm 8 ile aynı tanım; tek kaynak reporting.v_rfm_observation):
--   satış kapsamındaki (delivered) ilk satın alma günü .. son satın alma günü.
-- Gerçek veride 2018-09 ve 2018-10'da 20 sipariş var ama hiçbiri delivered değil: bu ayların satışı kaynağın
-- anlık görüntüsünde henüz gözlenemez (sıfır değil). 2018-11'de hiç sipariş yoktur.
--
-- Yeni kurallar:
-- - reporting.v_sales_observation_months: dim_date'in HER ayı için gözlem durumu:
--     'observed'      ay tamamen gözlem aralığında
--     'partial'       ay gözlem aralığının başı/sonu tarafından kesiliyor
--     'not_observed'  ay gözlem aralığının dışında (ör. yalnızca tahmini teslim tarihleri nedeniyle var)
--   dim_date DEĞİŞMEZ; teslimat için gereken takvim kapsamı korunur.
-- - v_monthly_sales_growth ve monthly_summary yalnızca 'observed' ve 'partial' ayları içerir. Gözlem aralığı
--   içinde satışı olmayan aylar 0 olarak kalır (gerçek sıfır).
-- - Büyüme oranı yalnızca iki TAM gözlenmiş ay arasında hesaplanır:
--     bu ay kısmi              -> growth_rate NULL, 'partial_month'
--     önceki ay yok            -> NULL, 'no_previous_month'
--     önceki ay kısmi          -> NULL, 'previous_month_partial'
--     önceki ay 0              -> NULL, 'previous_month_zero'
--     diğer                    -> 'computed'
--   prev_product_sales ve product_sales_change ham değerlerdir ve tanımlı kalır; yorum growth_status'a göre yapılır.
-- - Yeni kolonlar (sona eklenir): is_partial_month, observed_from, observed_to.
-- - fn_monthly_sales: önceki ay veri kapsamı tarafından kesiliyorsa (yalnızca kapsamın ikinci ayı) büyüme
--   'previous_month_partial' olur. Tarih FİLTRESİYLE kesilen önceki ay için tam ay değeri kullanılmaya devam eder
--   (o ay tamamen gözlenmiştir).

CREATE VIEW reporting.v_sales_observation_months AS
WITH obs AS (
    SELECT window_start_date AS first_date, last_purchase_date AS last_date FROM reporting.v_rfm_observation
), months AS (
    SELECT month_start, max(full_date) AS month_end, count(*)::int AS calendar_days
    FROM dw.dim_date GROUP BY month_start
)
SELECT m.month_start,
       m.month_end,
       m.calendar_days,
       CASE WHEN obs.first_date IS NULL OR m.month_end < obs.first_date OR m.month_start > obs.last_date
                THEN 'not_observed'
            WHEN m.month_start < obs.first_date OR m.month_end > obs.last_date THEN 'partial'
            ELSE 'observed' END AS observation_status,
       CASE WHEN m.month_end >= obs.first_date AND m.month_start <= obs.last_date
            THEN GREATEST(m.month_start, obs.first_date) END AS observed_from,
       CASE WHEN m.month_end >= obs.first_date AND m.month_start <= obs.last_date
            THEN LEAST(m.month_end, obs.last_date) END AS observed_to
FROM months m CROSS JOIN obs;

COMMENT ON VIEW reporting.v_sales_observation_months IS
    'dim_date ayları için satış gözlem durumu (observed / partial / not_observed); gözlem aralığı = v_rfm_observation';

CREATE OR REPLACE VIEW reporting.v_monthly_sales_growth AS
WITH months AS (
    SELECT month_start, observation_status, observed_from, observed_to
    FROM reporting.v_sales_observation_months
    WHERE observation_status <> 'not_observed'
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
           m.observation_status = 'partial'  AS is_partial,
           m.observed_from,
           m.observed_to,
           COALESCE(s.order_count, 0)       AS order_count,
           COALESCE(s.customer_count, 0)    AS customer_count,
           COALESCE(s.item_count, 0)        AS item_count,
           COALESCE(s.product_sales, 0)     AS product_sales,
           COALESCE(s.freight_amount, 0)    AS freight_amount,
           COALESCE(s.payment_amount, 0)    AS payment_amount
    FROM months m
    LEFT JOIN sales s ON s.purchase_month = m.month_start
), lagged AS (
    SELECT f.*,
           LAG(f.product_sales) OVER (ORDER BY f.month_start) AS prev_product_sales,
           LAG(f.is_partial)    OVER (ORDER BY f.month_start) AS prev_is_partial
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
        WHEN is_partial OR prev_product_sales IS NULL OR prev_is_partial OR prev_product_sales = 0 THEN NULL
        ELSE round((product_sales - prev_product_sales) / prev_product_sales, 4)
    END AS growth_rate,
    CASE
        WHEN is_partial THEN 'partial_month'
        WHEN prev_product_sales IS NULL THEN 'no_previous_month'
        WHEN prev_is_partial THEN 'previous_month_partial'
        WHEN prev_product_sales = 0 THEN 'previous_month_zero'
        ELSE 'computed'
    END AS growth_status,
    is_partial AS is_partial_month,
    observed_from,
    observed_to
FROM lagged;

COMMENT ON VIEW reporting.v_monthly_sales_growth IS
    'Aylık ürün satış tutarı ve büyüme; yalnızca satış gözlem aralığındaki aylar (v_sales_observation_months); '
    'aralık içindeki satışsız aylar 0; büyüme yalnızca iki tam ay arasında';

-- monthly_summary: aynı kolonlar ve durum değerleri. Mevcut satırlar yeni kurala göre yeniden yüklenir.
DELETE FROM reporting.monthly_summary;
ALTER TABLE reporting.monthly_summary DROP CONSTRAINT monthly_summary_growth_status_check;
ALTER TABLE reporting.monthly_summary
    ADD CONSTRAINT monthly_summary_growth_status_check CHECK (growth_status IN
        ('partial_month', 'no_previous_month', 'previous_month_partial', 'previous_month_zero', 'computed')),
    ADD COLUMN is_partial_month boolean NOT NULL,
    ADD COLUMN observed_from date NOT NULL,
    ADD COLUMN observed_to date NOT NULL,
    ADD CONSTRAINT monthly_summary_observed_in_month CHECK (
        observed_from BETWEEN month_start AND observed_to
        AND observed_to < (month_start + interval '1 month')::date);

CREATE OR REPLACE PROCEDURE reporting.sp_load_monthly_summary(year integer)
LANGUAGE plpgsql AS $$
#variable_conflict use_column
DECLARE
    v_year integer := sp_load_monthly_summary.year;
BEGIN
    IF v_year IS NULL THEN
        RAISE EXCEPTION 'sp_load_monthly_summary: year zorunludur';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM dw.dim_date d WHERE d.year = v_year) THEN
        RAISE EXCEPTION 'sp_load_monthly_summary: % yılı tarih boyutunda (dw.dim_date) yok', v_year;
    END IF;

    PERFORM pg_advisory_xact_lock(4820018, v_year);

    -- Yılın tüm satırları silinir; yalnızca gözlem aralığındaki aylar yeniden eklenir (view zaten sınırlar).
    DELETE FROM reporting.monthly_summary m WHERE m.year = v_year;

    INSERT INTO reporting.monthly_summary (
        month_start, year, month, order_count, customer_count, item_count, product_sales,
        freight_amount, payment_amount, avg_basket_value, prev_product_sales,
        product_sales_change, growth_rate, growth_status, is_partial_month, observed_from, observed_to
    )
    SELECT g.month_start, g.year, g.month, g.order_count, g.customer_count, g.item_count, g.product_sales,
           g.freight_amount, g.payment_amount, g.avg_basket_value, g.prev_product_sales,
           g.product_sales_change, g.growth_rate, g.growth_status, g.is_partial_month, g.observed_from, g.observed_to
    FROM reporting.v_monthly_sales_growth g
    WHERE g.year = v_year;
END
$$;

DO $$
DECLARE
    v_year integer;
BEGIN
    FOR v_year IN SELECT DISTINCT d.year FROM dw.dim_date d ORDER BY d.year LOOP
        CALL reporting.sp_load_monthly_summary(v_year);
    END LOOP;
END
$$;

-- fn_monthly_sales: sql/190 ile aynı; yalnızca kapsam tarafından kesilen önceki ay için 'previous_month_partial'.
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
               -- önceki ay veri kapsamının başı tarafından kesiliyor (tam gözlenmemiş)
               m.month_start > cov.first_month AND (m.month_start - interval '1 month')::date < cov.first_purchase_date
                 AS prev_cut_by_coverage,
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
           CASE WHEN s.is_partial OR s.prev_full_sales IS NULL OR s.prev_cut_by_coverage OR s.prev_full_sales = 0 THEN NULL
                ELSE round((s.full_sales - s.prev_full_sales) / s.prev_full_sales, 4) END,
           CASE WHEN s.is_partial THEN 'partial_month'
                WHEN s.prev_full_sales IS NULL THEN 'no_previous_month'
                WHEN s.prev_cut_by_coverage THEN 'previous_month_partial'
                WHEN s.prev_full_sales = 0 THEN 'previous_month_zero'
                ELSE 'computed' END,
           s.is_partial
    FROM series s
    WHERE s.month_start BETWEEN date_trunc('month', p_from)::date AND date_trunc('month', p_to)::date
    ORDER BY s.month_start
$$;

REVOKE EXECUTE ON FUNCTION reporting.fn_monthly_sales(date, date, text[], text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reporting.fn_monthly_sales(date, date, text[], text[]) TO olist_reporting_reader;
