-- Raporlama katmanı. Metrik tanımları: docs/metric_definitions.md
-- Varsayılan satış kapsamı: order_status = 'delivered' (in_sales_scope).
-- Diğer durumlar dw katmanında korunur ve bu view'lerde bayrakla ayrılır.

CREATE SCHEMA IF NOT EXISTS reporting;
COMMENT ON SCHEMA reporting IS 'Raporlama view ve materialized view nesneleri';

-- Sipariş düzeyi: bir satır = bir sipariş.
CREATE VIEW reporting.v_orders AS
SELECT
    o.order_id,
    o.customer_id,
    c.customer_unique_id,
    o.order_status,
    (o.order_status = 'delivered') AS in_sales_scope,
    o.purchase_ts,
    o.purchase_ts::date AS purchase_date,
    date_trunc('month', o.purchase_ts)::date AS purchase_month,
    o.delivered_customer_ts,
    o.estimated_delivery_date,
    o.item_count,
    o.product_value,
    o.freight_value,
    o.payment_count,
    o.payment_value,
    o.review_count,
    o.review_score_avg,
    o.delivery_days,
    o.is_late
FROM dw.fact_orders o
JOIN dw.dim_customer c USING (customer_id);

-- Kalem düzeyi: bir satır = bir sipariş kalemi. Sipariş düzeyi ölçüler (ödeme, kargo toplamı vb.)
-- burada bilinçli olarak yoktur; kalem başına tekrarlanıp toplanmasınlar.
CREATE VIEW reporting.v_sales_items AS
SELECT
    s.order_id,
    s.order_item_id,
    s.product_id,
    p.category_name,
    p.category_name_english,
    s.seller_id,
    s.customer_id,
    c.customer_unique_id,
    o.order_status,
    (o.order_status = 'delivered') AS in_sales_scope,
    o.purchase_ts,
    date_trunc('month', o.purchase_ts)::date AS purchase_month,
    s.price,
    s.freight_value
FROM dw.fact_sales s
JOIN dw.fact_orders o USING (order_id)
JOIN dw.dim_customer c ON c.customer_id = s.customer_id
JOIN dw.dim_product p USING (product_id);

-- Kişi düzeyi (customer_unique_id), yalnızca satış kapsamındaki siparişler.
-- RFM ve tekrar satın alma bu view üzerinden hesaplanır.
CREATE VIEW reporting.v_customer_purchases AS
SELECT
    customer_unique_id,
    count(*)                 AS order_count,
    min(purchase_ts)         AS first_purchase_ts,
    max(purchase_ts)         AS last_purchase_ts,
    sum(product_value)       AS product_sales,
    sum(freight_value)       AS freight_amount,
    sum(payment_value)       AS payment_amount
FROM reporting.v_orders
WHERE in_sales_scope
GROUP BY customer_unique_id;

-- RFM gözlem tarihi: kapsamdaki en son satın alma gününden bir sonraki gün.
CREATE VIEW reporting.v_rfm_observation AS
SELECT
    min(purchase_ts)::date                         AS window_start_date,
    max(purchase_ts)::date                         AS last_purchase_date,
    (max(purchase_ts)::date + 1)                   AS observation_date
FROM reporting.v_orders
WHERE in_sales_scope;

-- RFM girdileri (skorlama analiz aşamasında yapılır).
CREATE VIEW reporting.v_customer_rfm_base AS
SELECT
    cp.customer_unique_id,
    (obs.observation_date - cp.last_purchase_ts::date) AS recency_days,
    cp.order_count                                      AS frequency,
    cp.product_sales                                    AS monetary,
    obs.observation_date
FROM reporting.v_customer_purchases cp
CROSS JOIN reporting.v_rfm_observation obs;

-- Aylık satış özeti (satın alma ayına göre, yalnızca satış kapsamı).
-- Tüm toplamlar sipariş düzeyinden (v_orders) alınır; çoğalma yoktur.
CREATE MATERIALIZED VIEW reporting.mv_monthly_sales AS
SELECT
    purchase_month,
    count(*)                                                    AS order_count,
    count(DISTINCT customer_unique_id)                          AS customer_count,
    sum(item_count)                                             AS item_count,
    sum(product_value)                                          AS product_sales,
    sum(freight_value)                                          AS freight_amount,
    sum(payment_value)                                          AS payment_amount,
    round(sum(product_value) / count(*), 2)                     AS avg_basket_value,
    count(delivered_customer_ts)                                AS delivery_measured_orders,
    round(avg(delivery_days), 2)                                AS avg_delivery_days,
    count(*) FILTER (WHERE is_late)                             AS late_orders,
    round(count(*) FILTER (WHERE is_late)::numeric
          / NULLIF(count(delivered_customer_ts), 0), 4)         AS late_delivery_rate
FROM reporting.v_orders
WHERE in_sales_scope
GROUP BY purchase_month
WITH NO DATA;
CREATE UNIQUE INDEX mv_monthly_sales_month_uq ON reporting.mv_monthly_sales (purchase_month);

-- Tüm dönem özet metrikleri (tek satır, satış kapsamı).
CREATE VIEW reporting.v_sales_kpis AS
WITH scope AS (
    SELECT * FROM reporting.v_orders WHERE in_sales_scope
), customers AS (
    SELECT count(*) AS customer_count,
           count(*) FILTER (WHERE order_count >= 2) AS repeat_customer_count
    FROM reporting.v_customer_purchases
)
SELECT
    count(*)                                                            AS order_count,
    (SELECT customer_count FROM customers)                              AS customer_count,
    sum(item_count)                                                     AS item_count,
    sum(product_value)                                                  AS product_sales,
    sum(freight_value)                                                  AS freight_amount,
    sum(payment_value)                                                  AS payment_amount,
    round(sum(product_value) / NULLIF(count(*), 0), 2)                  AS avg_basket_value,
    count(delivered_customer_ts)                                        AS delivery_measured_orders,
    count(*) - count(delivered_customer_ts)                             AS delivery_unmeasured_orders,
    round(avg(delivery_days), 2)                                        AS avg_delivery_days,
    count(*) FILTER (WHERE is_late)                                     AS late_orders,
    round(count(*) FILTER (WHERE is_late)::numeric
          / NULLIF(count(delivered_customer_ts), 0), 4)                 AS late_delivery_rate,
    (SELECT repeat_customer_count FROM customers)                       AS repeat_customer_count,
    round((SELECT repeat_customer_count::numeric / NULLIF(customer_count, 0) FROM customers), 4)
                                                                        AS repeat_purchase_rate
FROM scope;
