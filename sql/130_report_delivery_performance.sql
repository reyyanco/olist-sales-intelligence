-- Analiz: teslimat süresi ve geç teslimat oranı (sipariş seviyesinde). reporting.v_delivery_performance
-- Tanımlar: docs/metric_definitions.md 5. ve 6. bölüm.
--
-- Kurallar:
-- - Grain: sipariş (reporting.v_orders, satış kapsamı = delivered). Kalem satırlarına inilmez;
--   bu yüzden çok kalemli siparişler süre/gecikme ortalamasını çoğaltmaz.
-- - GROUP BY ROLLUP (purchase_year, purchase_month): ay satırları + yıl ara toplamı + genel toplam.
--   grouping_level kolonu GROUPING() ile 'month' / 'year' / 'total' değerini alır.
-- - Pay/payda:
--     avg_delivery_days  = teslim zamanı dolu siparişlerin delivery_days ortalaması
--     late_delivery_rate = late_orders / delivery_measured_orders; payda 0 ise NULL
--   Teslim zamanı boş siparişler (delivery_unmeasured_orders) her iki metrikten dışlanır ve ayrıca sayılır.
-- - Süre dilimleri CASE ile: 0-7, 7-14, 14-30, 30+ gün (üst sınır dahil: 7.00 gün ilk dilimde).

CREATE VIEW reporting.v_delivery_performance AS
WITH orders AS (
    SELECT EXTRACT(YEAR FROM purchase_month)::int AS purchase_year,
           purchase_month,
           delivered_customer_ts,
           delivery_days,
           is_late
    FROM reporting.v_orders
    WHERE in_sales_scope
)
SELECT
    CASE
        WHEN GROUPING(purchase_year) = 1  THEN 'total'
        WHEN GROUPING(purchase_month) = 1 THEN 'year'
        ELSE 'month'
    END                                                             AS grouping_level,
    purchase_year,
    purchase_month,
    count(*)                                                        AS order_count,
    count(delivered_customer_ts)                                    AS delivery_measured_orders,
    count(*) - count(delivered_customer_ts)                         AS delivery_unmeasured_orders,
    round(avg(delivery_days), 2)                                    AS avg_delivery_days,
    sum(CASE WHEN is_late THEN 1 ELSE 0 END)                        AS late_orders,
    round(sum(CASE WHEN is_late THEN 1 ELSE 0 END)::numeric
          / NULLIF(count(delivered_customer_ts), 0), 4)             AS late_delivery_rate,
    sum(CASE WHEN delivery_days <= 7 THEN 1 ELSE 0 END)                         AS days_0_7,
    sum(CASE WHEN delivery_days > 7 AND delivery_days <= 14 THEN 1 ELSE 0 END)  AS days_7_14,
    sum(CASE WHEN delivery_days > 14 AND delivery_days <= 30 THEN 1 ELSE 0 END) AS days_14_30,
    sum(CASE WHEN delivery_days > 30 THEN 1 ELSE 0 END)                         AS days_over_30
FROM orders
GROUP BY ROLLUP (purchase_year, purchase_month);

COMMENT ON VIEW reporting.v_delivery_performance IS
    'Sipariş seviyesinde teslimat süresi ve geç teslim oranı; ROLLUP ile ay, yıl ve genel toplam';
