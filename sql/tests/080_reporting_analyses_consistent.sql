-- Analiz nesneleri metrik tanımlarıyla tutarlı olmalı: her analizin toplamı reporting.v_sales_kpis
-- (tek tanım kaynağı) ile aynı olmalı. Sonuç satırı = uyumsuzluk.
WITH k AS (
    SELECT * FROM reporting.v_sales_kpis
), obs AS (
    SELECT observation_date FROM reporting.v_rfm_observation
), rfm AS (
    SELECT count(*) AS customers, sum(r.frequency) AS orders, sum(r.monetary) AS monetary
    FROM obs, LATERAL reporting.fn_customer_rfm(obs.observation_date) r
    WHERE obs.observation_date IS NOT NULL
), growth AS (
    SELECT sum(order_count) AS orders, sum(product_sales) AS product_sales, sum(payment_amount) AS payment_amount
    FROM reporting.v_monthly_sales_growth
), summary AS (
    SELECT sum(order_count) AS orders, sum(product_sales) AS product_sales, count(*) AS months
    FROM reporting.monthly_summary
), growth_months AS (
    SELECT count(*) AS months FROM reporting.v_monthly_sales_growth
), obs_months AS (
    -- Aylık raporlar yalnızca satış gözlem aralığındaki ayları içerir (sql/200); aralık v_rfm_observation'dır
    SELECT count(*) AS n FROM reporting.v_rfm_observation o,
         LATERAL generate_series(date_trunc('month', o.window_start_date), date_trunc('month', o.last_purchase_date),
                                 interval '1 month') m
    WHERE o.window_start_date IS NOT NULL
), outside AS (
    SELECT (SELECT count(*) FROM reporting.v_monthly_sales_growth g, reporting.v_rfm_observation o
            WHERE g.month_start < date_trunc('month', o.window_start_date) OR g.month_start > o.last_purchase_date)
         + (SELECT count(*) FROM reporting.monthly_summary s, reporting.v_rfm_observation o
            WHERE s.month_start < date_trunc('month', o.window_start_date) OR s.month_start > o.last_purchase_date) AS n
), growth_on_partial AS (
    -- Kısmi ay veya kısmi önceki ay için büyüme oranı hesaplanmaz
    SELECT count(*) AS n FROM (
        SELECT growth_rate, is_partial_month, LAG(is_partial_month) OVER (ORDER BY month_start) AS prev_partial
        FROM reporting.v_monthly_sales_growth) x
    WHERE growth_rate IS NOT NULL AND (is_partial_month OR prev_partial)
), monthly_mismatch AS (
    -- Satışı olan her ay mv_monthly_sales ile aynı olmalı
    SELECT count(*) AS n
    FROM reporting.mv_monthly_sales m
    LEFT JOIN reporting.v_monthly_sales_growth g ON g.month_start = m.purchase_month
    WHERE g.month_start IS NULL
       OR (g.order_count, g.customer_count, g.product_sales, g.payment_amount)
          IS DISTINCT FROM (m.order_count, m.customer_count, m.product_sales, m.payment_amount)
), category AS (
    SELECT sum(product_sales) AS product_sales, sum(item_count) AS items, max(cumulative_share) AS max_share
    FROM reporting.mv_category_sales
), delivery AS (
    SELECT * FROM reporting.v_delivery_performance WHERE grouping_level = 'total'
), repeat AS (
    SELECT * FROM reporting.v_repeat_purchase WHERE grouping_level = 'total'
)
SELECT check_name, expected_value, actual_value
FROM (
    SELECT 'rfm_customer_count' AS check_name, k.customer_count::numeric AS expected_value, rfm.customers::numeric AS actual_value FROM k, rfm
    UNION ALL SELECT 'rfm_frequency_sum', k.order_count, rfm.orders FROM k, rfm
    UNION ALL SELECT 'rfm_monetary_sum', k.product_sales, rfm.monetary FROM k, rfm
    UNION ALL SELECT 'growth_order_count', k.order_count, COALESCE(growth.orders, 0) FROM k, growth
    UNION ALL SELECT 'growth_product_sales', COALESCE(k.product_sales, 0), COALESCE(growth.product_sales, 0) FROM k, growth
    UNION ALL SELECT 'growth_payment_amount', COALESCE(k.payment_amount, 0), COALESCE(growth.payment_amount, 0) FROM k, growth
    UNION ALL SELECT 'monthly_vs_mv_mismatched_months', 0, monthly_mismatch.n FROM monthly_mismatch
    UNION ALL SELECT 'summary_months', growth_months.months, summary.months FROM growth_months, summary
    UNION ALL SELECT 'growth_months_vs_observation_months', obs_months.n, growth_months.months FROM obs_months, growth_months
    UNION ALL SELECT 'monthly_rows_outside_observation', 0, outside.n FROM outside
    UNION ALL SELECT 'growth_rate_on_partial_months', 0, growth_on_partial.n FROM growth_on_partial
    UNION ALL SELECT 'summary_product_sales', COALESCE(k.product_sales, 0), COALESCE(summary.product_sales, 0) FROM k, summary
    UNION ALL SELECT 'category_product_sales', COALESCE(k.product_sales, 0), COALESCE(category.product_sales, 0) FROM k, category
    UNION ALL SELECT 'category_item_count', COALESCE(k.item_count, 0), COALESCE(category.items, 0) FROM k, category
    UNION ALL SELECT 'category_max_cumulative_share', CASE WHEN k.product_sales > 0 THEN 1 END, category.max_share FROM k, category
    UNION ALL SELECT 'delivery_order_count', k.order_count, delivery.order_count FROM k, delivery
    UNION ALL SELECT 'delivery_measured_orders', k.delivery_measured_orders, delivery.delivery_measured_orders FROM k, delivery
    UNION ALL SELECT 'delivery_avg_days', k.avg_delivery_days, delivery.avg_delivery_days FROM k, delivery
    UNION ALL SELECT 'delivery_late_orders', k.late_orders, delivery.late_orders FROM k, delivery
    UNION ALL SELECT 'delivery_late_rate', k.late_delivery_rate, delivery.late_delivery_rate FROM k, delivery
    UNION ALL SELECT 'repeat_customer_count', k.repeat_customer_count, repeat.repeat_customer_count FROM k, repeat
    UNION ALL SELECT 'repeat_purchase_rate', k.repeat_purchase_rate, repeat.repeat_purchase_rate FROM k, repeat
) AS checks
WHERE expected_value IS DISTINCT FROM actual_value;
