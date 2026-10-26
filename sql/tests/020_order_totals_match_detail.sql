-- fact_orders içindeki önceden toplanmış ölçüler, ayrıntı olgularıyla birebir eşleşmeli.
-- Sonuç satırı = uyumsuz sipariş.
WITH items AS (
    SELECT order_id, count(*) AS item_count, sum(price) AS product_value, sum(freight_value) AS freight_value
    FROM dw.fact_sales GROUP BY order_id
), payments AS (
    SELECT order_id, count(*) AS payment_count, sum(payment_value) AS payment_value
    FROM dw.fact_payments GROUP BY order_id
)
SELECT o.order_id, o.item_count, i.item_count AS detail_item_count,
       o.product_value, i.product_value AS detail_product_value,
       o.freight_value, i.freight_value AS detail_freight_value,
       o.payment_count, p.payment_count AS detail_payment_count,
       o.payment_value, p.payment_value AS detail_payment_value
FROM dw.fact_orders o
LEFT JOIN items i USING (order_id)
LEFT JOIN payments p USING (order_id)
WHERE o.item_count    <> COALESCE(i.item_count, 0)
   OR o.product_value <> COALESCE(i.product_value, 0)
   OR o.freight_value <> COALESCE(i.freight_value, 0)
   OR o.payment_count <> COALESCE(p.payment_count, 0)
   OR o.payment_value <> COALESCE(p.payment_value, 0);
