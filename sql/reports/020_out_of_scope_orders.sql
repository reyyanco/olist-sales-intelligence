-- Yüklenen ama varsayılan satış kapsamının (order_status = 'delivered') dışında kalan siparişler.
-- Bu siparişler dw'de korunur; satış metriklerine girmez.
SELECT order_status,
       count(*)                        AS order_count,
       sum(item_count)                 AS item_count,
       sum(product_value)              AS product_value,
       sum(payment_value)              AS payment_value,
       count(delivered_customer_ts)    AS with_delivery_date
FROM dw.fact_orders
WHERE order_status <> 'delivered'
GROUP BY order_status
ORDER BY order_count DESC;
