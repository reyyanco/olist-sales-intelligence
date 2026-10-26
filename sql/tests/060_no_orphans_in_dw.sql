-- Yetim FK kontrolü: dw içindeki her ilişki karşılığını bulmalı. Kısıtlar bunu zaten zorlar;
-- kontrol, kısıtların kaldırılması veya devre dışı kalması durumuna karşı açık doğrulamadır.
-- Sonuç satırı = yetim kayıt.
SELECT 'fact_orders.customer_id' AS relationship, o.order_id AS child_key
FROM dw.fact_orders o LEFT JOIN dw.dim_customer c USING (customer_id) WHERE c.customer_id IS NULL
UNION ALL
SELECT 'fact_sales.order_id', s.order_id || ':' || s.order_item_id
FROM dw.fact_sales s LEFT JOIN dw.fact_orders o USING (order_id) WHERE o.order_id IS NULL
UNION ALL
SELECT 'fact_sales.product_id', s.order_id || ':' || s.order_item_id
FROM dw.fact_sales s LEFT JOIN dw.dim_product p USING (product_id) WHERE p.product_id IS NULL
UNION ALL
SELECT 'fact_sales.seller_id', s.order_id || ':' || s.order_item_id
FROM dw.fact_sales s LEFT JOIN dw.dim_seller x USING (seller_id) WHERE x.seller_id IS NULL
UNION ALL
SELECT 'fact_payments.order_id', p.order_id || ':' || p.payment_sequential
FROM dw.fact_payments p LEFT JOIN dw.fact_orders o USING (order_id) WHERE o.order_id IS NULL
UNION ALL
SELECT 'fact_orders.purchase_date_key', o.order_id
FROM dw.fact_orders o LEFT JOIN dw.dim_date d ON d.date_key = o.purchase_date_key WHERE d.date_key IS NULL;
