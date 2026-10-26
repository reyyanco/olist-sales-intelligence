-- Dashboard için parametreli raporlama fonksiyonları. İş mantığı burada; dashboard yeniden hesaplamaz.
-- Tanımlar: docs/metric_definitions.md, docs/dashboard.md
--
-- Ortak filtre kuralları (tüm fonksiyonlar):
-- - Satış kapsamı: order_status = 'delivered'.
-- - Tarih: satın alma günü p_from..p_to (ikisi dahil). purchase_date_key üzerinden uygulanır
--   (fact tablolarındaki tarih anahtarı; purchase_ts ile tutarlılığı CHECK ile zorunlu).
-- - p_states: müşterinin (siparişteki customer_id'nin) eyaleti; NULL = filtre yok.
-- - p_categories: category_label; NULL = filtre yok. Kategori filtresi kalem düzeyinde uygulanır:
--   tutar = seçili kategorilerdeki kalemlerin fiyat toplamı; sipariş sayısı = seçili kategoride en az bir
--   kalemi olan FARKLI sipariş sayısı (count DISTINCT, çoğalma yok).
-- - Fonksiyonlar SECURITY INVOKER'dır ve yalnızca reporting view'lerini okur; dashboard rolü dw'ye erişmez.

-- Eyalet -> IBGE coğrafi bölgesi (sabit başvuru verisi)
CREATE TABLE reporting.state_region (
    state  text PRIMARY KEY CHECK (state ~ '^[A-Z]{2}$'),
    region text NOT NULL CHECK (region IN ('Norte', 'Nordeste', 'Centro-Oeste', 'Sudeste', 'Sul'))
);
INSERT INTO reporting.state_region (state, region) VALUES
    ('AC', 'Norte'), ('AP', 'Norte'), ('AM', 'Norte'), ('PA', 'Norte'), ('RO', 'Norte'), ('RR', 'Norte'), ('TO', 'Norte'),
    ('AL', 'Nordeste'), ('BA', 'Nordeste'), ('CE', 'Nordeste'), ('MA', 'Nordeste'), ('PB', 'Nordeste'),
    ('PE', 'Nordeste'), ('PI', 'Nordeste'), ('RN', 'Nordeste'), ('SE', 'Nordeste'),
    ('DF', 'Centro-Oeste'), ('GO', 'Centro-Oeste'), ('MT', 'Centro-Oeste'), ('MS', 'Centro-Oeste'),
    ('ES', 'Sudeste'), ('MG', 'Sudeste'), ('RJ', 'Sudeste'), ('SP', 'Sudeste'),
    ('PR', 'Sul'), ('RS', 'Sul'), ('SC', 'Sul');
COMMENT ON TABLE reporting.state_region IS 'Brezilya eyaletlerinin IBGE coğrafi bölgeleri';

-- Kalem düzeyi, yalnızca satış kapsamı; filtre için gereken kolonlar.
CREATE VIEW reporting.v_dashboard_items AS
SELECT s.order_id,
       s.order_item_id,
       s.purchase_date_key,
       o.purchase_ts::date              AS purchase_date,
       date_trunc('month', o.purchase_ts)::date AS purchase_month,
       c.customer_unique_id,
       c.state                          AS customer_state,
       p.category_label,
       s.price
FROM dw.fact_sales s
JOIN dw.fact_orders o  ON o.order_id = s.order_id
JOIN dw.dim_customer c ON c.customer_id = s.customer_id
JOIN dw.dim_product p  ON p.product_id = s.product_id
WHERE o.order_status = 'delivered';

-- Sipariş düzeyi, yalnızca satış kapsamı; teslimat metrikleri için.
CREATE VIEW reporting.v_dashboard_orders AS
SELECT o.order_id,
       o.purchase_date_key,
       o.purchase_ts::date                 AS purchase_date,
       date_trunc('month', o.purchase_ts)::date AS purchase_month,
       c.customer_unique_id,
       c.state                             AS customer_state,
       r.region                            AS customer_region,
       o.product_value,
       o.delivered_customer_ts,
       o.delivery_days,
       o.is_late
FROM dw.fact_orders o
JOIN dw.dim_customer c ON c.customer_id = o.customer_id
LEFT JOIN reporting.state_region r ON r.state = c.state
WHERE o.order_status = 'delivered';

-- Veri kapsamı: satış kapsamındaki ilk ve son satın alma. Dashboard'un varsayılan tarih aralığı buradan gelir.
CREATE VIEW reporting.v_data_coverage AS
SELECT min(purchase_date)                        AS first_purchase_date,
       max(purchase_date)                        AS last_purchase_date,
       date_trunc('month', min(purchase_date))::date AS first_month,
       date_trunc('month', max(purchase_date))::date AS last_month,
       count(*)                                  AS order_count
FROM reporting.v_dashboard_orders;

-- Son başarılı yükleme ve rapor yenileme (dashboard rolü meta şemasını görmez; yalnızca bu view'i okur).
CREATE VIEW reporting.v_data_freshness AS
SELECT (SELECT finished_at FROM meta.etl_runs WHERE status = 'succeeded' ORDER BY finished_at DESC LIMIT 1) AS last_successful_load_at,
       (SELECT run_id FROM meta.etl_runs WHERE status = 'succeeded' ORDER BY finished_at DESC LIMIT 1)      AS last_successful_run_id,
       (SELECT finished_at FROM meta.report_refresh_runs WHERE status = 'succeeded' ORDER BY refresh_id DESC LIMIT 1) AS last_report_refresh_at;

CREATE VIEW reporting.v_dashboard_categories AS
SELECT DISTINCT category_label FROM dw.dim_product;

CREATE VIEW reporting.v_dashboard_states AS
SELECT DISTINCT c.state, r.region
FROM dw.dim_customer c LEFT JOIN reporting.state_region r ON r.state = c.state;

-- Genel bakış KPI'ları (tek satır).
CREATE FUNCTION reporting.fn_overview_kpis(p_from date, p_to date, p_states text[] DEFAULT NULL, p_categories text[] DEFAULT NULL)
RETURNS TABLE (product_sales numeric(14,2), order_count bigint, customer_count bigint, item_count bigint, avg_basket_value numeric(14,2))
LANGUAGE sql STABLE AS $$
    SELECT COALESCE(sum(i.price), 0)::numeric(14,2),
           count(DISTINCT i.order_id),
           count(DISTINCT i.customer_unique_id),
           count(*),
           round(sum(i.price) / NULLIF(count(DISTINCT i.order_id), 0), 2)
    FROM reporting.v_dashboard_items i
    WHERE i.purchase_date_key BETWEEN to_char(p_from, 'YYYYMMDD')::int AND to_char(p_to, 'YYYYMMDD')::int
      AND (p_states IS NULL OR i.customer_state = ANY (p_states))
      AND (p_categories IS NULL OR i.category_label = ANY (p_categories))
$$;

-- Aylık seri. Aylar veri kapsamıyla sınırlıdır (tahmini teslim tarihlerinden gelen gelecek aylar YOK).
-- Kapsam içinde satışı olmayan aylar 0 olarak gelir. Büyüme, filtreler uygulanmış TÜM kapsam serisi üzerinden
-- hesaplanır, sonra seçili aralık döndürülür (aralığın ilk ayı da önceki aya göre büyüme alır).
-- is_partial_month: ay, seçili aralık veya veri kapsamı tarafından kesiliyor (tam ay değil).
CREATE FUNCTION reporting.fn_monthly_sales(p_from date, p_to date, p_states text[] DEFAULT NULL, p_categories text[] DEFAULT NULL)
RETURNS TABLE (month_start date, product_sales numeric(14,2), order_count bigint, customer_count bigint,
               avg_basket_value numeric(14,2), prev_product_sales numeric(14,2), growth_rate numeric(10,4),
               growth_status text, is_partial_month boolean)
LANGUAGE sql STABLE AS $$
    WITH cov AS (
        SELECT first_purchase_date, last_purchase_date, first_month, last_month FROM reporting.v_data_coverage
    ), months AS (
        SELECT generate_series(cov.first_month, cov.last_month, interval '1 month')::date AS month_start FROM cov
    ), agg AS (
        SELECT i.purchase_month, sum(i.price) AS product_sales, count(DISTINCT i.order_id) AS order_count,
               count(DISTINCT i.customer_unique_id) AS customer_count
        FROM reporting.v_dashboard_items i
        WHERE (p_states IS NULL OR i.customer_state = ANY (p_states))
          AND (p_categories IS NULL OR i.category_label = ANY (p_categories))
        GROUP BY i.purchase_month
    ), series AS (
        SELECT m.month_start,
               COALESCE(a.product_sales, 0) AS product_sales,
               COALESCE(a.order_count, 0)   AS order_count,
               COALESCE(a.customer_count, 0) AS customer_count,
               LAG(COALESCE(a.product_sales, 0)) OVER (ORDER BY m.month_start) AS prev_product_sales
        FROM months m LEFT JOIN agg a ON a.purchase_month = m.month_start
    )
    SELECT s.month_start,
           s.product_sales::numeric(14,2),
           s.order_count,
           s.customer_count,
           round(s.product_sales / NULLIF(s.order_count, 0), 2),
           s.prev_product_sales::numeric(14,2),
           CASE WHEN s.prev_product_sales IS NULL OR s.prev_product_sales = 0 THEN NULL
                ELSE round((s.product_sales - s.prev_product_sales) / s.prev_product_sales, 4) END,
           CASE WHEN s.prev_product_sales IS NULL THEN 'no_previous_month'
                WHEN s.prev_product_sales = 0 THEN 'previous_month_zero'
                ELSE 'computed' END,
           s.month_start < GREATEST(p_from, cov.first_purchase_date)
             OR (s.month_start + interval '1 month' - interval '1 day')::date > LEAST(p_to, cov.last_purchase_date)
    FROM series s, cov
    WHERE s.month_start BETWEEN date_trunc('month', p_from)::date AND date_trunc('month', p_to)::date
    ORDER BY s.month_start
$$;

-- Kategori satışları, sıra ve kümülatif pay (mv_category_sales ile aynı kurallar, filtreli).
CREATE FUNCTION reporting.fn_category_sales(p_from date, p_to date, p_states text[] DEFAULT NULL)
RETURNS TABLE (sales_rank integer, category_label text, item_count bigint, order_count bigint,
               product_sales numeric(14,2), sales_share numeric, cumulative_sales numeric(14,2), cumulative_share numeric)
LANGUAGE sql STABLE AS $$
    WITH categories AS (
        SELECT i.category_label, count(*) AS item_count, count(DISTINCT i.order_id) AS order_count, sum(i.price) AS product_sales
        FROM reporting.v_dashboard_items i
        WHERE i.purchase_date_key BETWEEN to_char(p_from, 'YYYYMMDD')::int AND to_char(p_to, 'YYYYMMDD')::int
          AND (p_states IS NULL OR i.customer_state = ANY (p_states))
        GROUP BY i.category_label
    ), ranked AS (
        SELECT c.*,
               row_number() OVER w AS sales_rank,
               sum(c.product_sales) OVER (ORDER BY c.product_sales DESC, c.category_label
                                          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_sales,
               sum(c.product_sales) OVER () AS total_sales
        FROM categories c
        WINDOW w AS (ORDER BY c.product_sales DESC, c.category_label)
    )
    SELECT sales_rank::integer, category_label, item_count, order_count, product_sales::numeric(14,2),
           round(product_sales / NULLIF(total_sales, 0), 4), cumulative_sales::numeric(14,2),
           round(cumulative_sales / NULLIF(total_sales, 0), 4)
    FROM ranked
    ORDER BY sales_rank
$$;

-- Teslimat performansı: bölge ve eyalet kırılımı (ROLLUP ile bölge ara toplamı + genel toplam).
-- Pay/payda kuralları docs/metric_definitions.md 5-6 (teslim zamanı boş siparişler süre ve orandan dışlanır).
CREATE FUNCTION reporting.fn_delivery_by_region(p_from date, p_to date, p_states text[] DEFAULT NULL)
RETURNS TABLE (grouping_level text, customer_region text, customer_state text, order_count bigint,
               delivery_measured_orders bigint, avg_delivery_days numeric, late_orders bigint, late_delivery_rate numeric)
LANGUAGE sql STABLE AS $$
    SELECT CASE WHEN GROUPING(o.customer_region) = 1 THEN 'total'
                WHEN GROUPING(o.customer_state) = 1 THEN 'region' ELSE 'state' END,
           o.customer_region, o.customer_state,
           count(*), count(o.delivered_customer_ts), round(avg(o.delivery_days), 2),
           count(*) FILTER (WHERE o.is_late),
           round(count(*) FILTER (WHERE o.is_late)::numeric / NULLIF(count(o.delivered_customer_ts), 0), 4)
    FROM reporting.v_dashboard_orders o
    WHERE o.purchase_date_key BETWEEN to_char(p_from, 'YYYYMMDD')::int AND to_char(p_to, 'YYYYMMDD')::int
      AND (p_states IS NULL OR o.customer_state = ANY (p_states))
    GROUP BY ROLLUP (o.customer_region, o.customer_state)
    ORDER BY GROUPING(o.customer_region) DESC, o.customer_region NULLS FIRST, GROUPING(o.customer_state) DESC, o.customer_state
$$;

-- Teslimat performansı: aylık seri (veri kapsamındaki aylar).
CREATE FUNCTION reporting.fn_delivery_monthly(p_from date, p_to date, p_states text[] DEFAULT NULL)
RETURNS TABLE (month_start date, order_count bigint, delivery_measured_orders bigint, avg_delivery_days numeric,
               late_orders bigint, late_delivery_rate numeric)
LANGUAGE sql STABLE AS $$
    SELECT o.purchase_month, count(*), count(o.delivered_customer_ts), round(avg(o.delivery_days), 2),
           count(*) FILTER (WHERE o.is_late),
           round(count(*) FILTER (WHERE o.is_late)::numeric / NULLIF(count(o.delivered_customer_ts), 0), 4)
    FROM reporting.v_dashboard_orders o
    WHERE o.purchase_date_key BETWEEN to_char(p_from, 'YYYYMMDD')::int AND to_char(p_to, 'YYYYMMDD')::int
      AND (p_states IS NULL OR o.customer_state = ANY (p_states))
    GROUP BY o.purchase_month
    ORDER BY o.purchase_month
$$;

-- Tekrar satın alma: seçili aralıkta en az bir siparişi olan kişiler (customer_unique_id); tekrar eden =
-- aralıkta en az 2 FARKLI siparişi olan. Tek geçişli toplama (docs/performance.md E4).
CREATE FUNCTION reporting.fn_repeat_purchase(p_from date, p_to date)
RETURNS TABLE (customer_count bigint, repeat_customer_count bigint, repeat_purchase_rate numeric)
LANGUAGE sql STABLE AS $$
    WITH customers AS (
        SELECT o.customer_unique_id, count(DISTINCT o.order_id) AS orders
        FROM reporting.v_dashboard_orders o
        WHERE o.purchase_date_key BETWEEN to_char(p_from, 'YYYYMMDD')::int AND to_char(p_to, 'YYYYMMDD')::int
        GROUP BY o.customer_unique_id
    )
    SELECT count(*), count(*) FILTER (WHERE orders >= 2),
           round(count(*) FILTER (WHERE orders >= 2)::numeric / NULLIF(count(*), 0), 4)
    FROM customers
$$;

-- RFM segment özeti (fn_customer_rfm kurallarıyla; as_of zorunlu).
CREATE FUNCTION reporting.fn_rfm_segments(as_of date)
RETURNS TABLE (segment text, customer_count bigint, avg_recency_days numeric, avg_frequency numeric,
               avg_monetary numeric, total_monetary numeric(14,2))
LANGUAGE sql STABLE AS $$
    SELECT r.segment, count(*), round(avg(r.recency_days), 1), round(avg(r.frequency), 2),
           round(avg(r.monetary), 2), sum(r.monetary)::numeric(14,2)
    FROM reporting.fn_customer_rfm(as_of) r
    GROUP BY r.segment
    ORDER BY count(*) DESC, r.segment
$$;
