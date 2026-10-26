-- Dashboard fonksiyonları, filtresiz ve tam veri kapsamında mevcut tek tanım kaynaklarıyla aynı olmalı.
-- Sonuç satırı = uyumsuzluk.
WITH cov AS (
    SELECT first_purchase_date AS f, last_purchase_date AS t FROM reporting.v_data_coverage WHERE order_count > 0
), k AS (
    SELECT * FROM reporting.v_sales_kpis
), ov AS (
    SELECT o.* FROM cov, LATERAL reporting.fn_overview_kpis(cov.f, cov.t) o
), mon AS (
    SELECT sum(m.product_sales) AS product_sales, sum(m.order_count) AS order_count, count(*) AS months
    FROM cov, LATERAL reporting.fn_monthly_sales(cov.f, cov.t) m
), mon_vs_growth AS (
    -- Kapsam içindeki her ay v_monthly_sales_growth ile aynı (tutar, sipariş, müşteri)
    SELECT count(*) AS n FROM (
        SELECT m.month_start, m.product_sales, m.order_count, m.customer_count
        FROM cov, LATERAL reporting.fn_monthly_sales(cov.f, cov.t) m
        EXCEPT
        SELECT g.month_start, g.product_sales, g.order_count, g.customer_count
        FROM reporting.v_monthly_sales_growth g, reporting.v_data_coverage c
        WHERE g.month_start BETWEEN c.first_month AND c.last_month
    ) d
), expected_months AS (
    SELECT (EXTRACT(YEAR FROM age(last_month, first_month)) * 12 + EXTRACT(MONTH FROM age(last_month, first_month)) + 1)::bigint AS n
    FROM reporting.v_data_coverage WHERE order_count > 0
), cat_diff AS (
    SELECT count(*) AS n FROM (
        (SELECT c.sales_rank, c.category_label, c.item_count, c.order_count, c.product_sales, c.sales_share,
                c.cumulative_sales, c.cumulative_share FROM cov, LATERAL reporting.fn_category_sales(cov.f, cov.t) c
         EXCEPT
         SELECT sales_rank, category_label, item_count, order_count, product_sales, sales_share, cumulative_sales, cumulative_share
         FROM reporting.mv_category_sales)
        UNION ALL
        (SELECT sales_rank, category_label, item_count, order_count, product_sales, sales_share, cumulative_sales, cumulative_share
         FROM reporting.mv_category_sales
         EXCEPT
         SELECT c.sales_rank, c.category_label, c.item_count, c.order_count, c.product_sales, c.sales_share,
                c.cumulative_sales, c.cumulative_share FROM cov, LATERAL reporting.fn_category_sales(cov.f, cov.t) c)
    ) d
), dlv AS (
    SELECT d.* FROM cov, LATERAL reporting.fn_delivery_by_region(cov.f, cov.t) d WHERE d.grouping_level = 'total'
), rep AS (
    SELECT r.* FROM cov, LATERAL reporting.fn_repeat_purchase(cov.f, cov.t) r
), rep_view AS (
    SELECT * FROM reporting.v_repeat_purchase WHERE grouping_level = 'total'
), mid AS (
    -- Ay ortasında başlayıp biten aralık: KPI ile aylık seri AYNI kapsamı kullanmalı (Aşama 8'de bulunan hata)
    SELECT (f + 20) AS f, (t - 10) AS t FROM cov
), mid_kpi AS (
    SELECT o.product_sales, o.order_count FROM mid, LATERAL reporting.fn_overview_kpis(mid.f, mid.t) o
), mid_mon AS (
    SELECT sum(m.product_sales) AS product_sales, sum(m.order_count) AS order_count
    FROM mid, LATERAL reporting.fn_monthly_sales(mid.f, mid.t) m
), seg AS (
    SELECT sum(s.customer_count) AS customers, sum(s.total_monetary) AS monetary
    FROM reporting.v_rfm_observation obs, LATERAL reporting.fn_rfm_segments(obs.observation_date) s
    WHERE obs.observation_date IS NOT NULL
)
SELECT check_name, expected_value, actual_value
FROM (
    SELECT 'overview_product_sales' AS check_name, k.product_sales::numeric AS expected_value, ov.product_sales::numeric AS actual_value FROM k, ov
    UNION ALL SELECT 'overview_order_count', k.order_count, ov.order_count FROM k, ov
    UNION ALL SELECT 'overview_customer_count', k.customer_count, ov.customer_count FROM k, ov
    UNION ALL SELECT 'overview_item_count', k.item_count, ov.item_count FROM k, ov
    UNION ALL SELECT 'overview_avg_basket', k.avg_basket_value, ov.avg_basket_value FROM k, ov
    UNION ALL SELECT 'monthly_product_sales', k.product_sales, mon.product_sales FROM k, mon
    UNION ALL SELECT 'monthly_order_count', k.order_count, mon.order_count FROM k, mon
    UNION ALL SELECT 'monthly_month_count', em.n, mon.months FROM expected_months em, mon
    UNION ALL SELECT 'mid_range_monthly_sum_vs_kpi_sales', mid_kpi.product_sales, mid_mon.product_sales FROM mid_kpi, mid_mon
    UNION ALL SELECT 'mid_range_monthly_sum_vs_kpi_orders', mid_kpi.order_count, mid_mon.order_count FROM mid_kpi, mid_mon
    UNION ALL SELECT 'monthly_vs_growth_view_mismatches', 0, mon_vs_growth.n FROM mon_vs_growth
    UNION ALL SELECT 'category_vs_mv_mismatches', 0, cat_diff.n FROM cat_diff
    UNION ALL SELECT 'delivery_order_count', k.order_count, dlv.order_count FROM k, dlv
    UNION ALL SELECT 'delivery_measured_orders', k.delivery_measured_orders, dlv.delivery_measured_orders FROM k, dlv
    UNION ALL SELECT 'delivery_avg_days', k.avg_delivery_days, dlv.avg_delivery_days FROM k, dlv
    UNION ALL SELECT 'delivery_late_rate', k.late_delivery_rate, dlv.late_delivery_rate FROM k, dlv
    UNION ALL SELECT 'repeat_customer_count', rep_view.customer_count, rep.customer_count FROM rep_view, rep
    UNION ALL SELECT 'repeat_repeat_customers', rep_view.repeat_customer_count, rep.repeat_customer_count FROM rep_view, rep
    UNION ALL SELECT 'repeat_rate', rep_view.repeat_purchase_rate, rep.repeat_purchase_rate FROM rep_view, rep
    UNION ALL SELECT 'rfm_segment_customers', k.customer_count, seg.customers FROM k, seg
    UNION ALL SELECT 'rfm_segment_monetary', k.product_sales, seg.monetary FROM k, seg
) AS checks
WHERE expected_value IS DISTINCT FROM actual_value;
