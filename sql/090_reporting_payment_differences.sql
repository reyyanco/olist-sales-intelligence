-- Ödeme toplamı ile kalem fiyatı + kargo toplamı farklı olan siparişler.
-- Fark raporlanır, zorla eşitlenmez (taksit faizi, kupon vb. nedenler kaynakta belirtilmiyor).
CREATE VIEW reporting.v_order_payment_differences AS
SELECT
    order_id,
    order_status,
    (order_status = 'delivered') AS in_sales_scope,
    item_count,
    product_value,
    freight_value,
    product_value + freight_value                    AS items_plus_freight,
    payment_count,
    payment_value,
    payment_value - (product_value + freight_value)  AS difference,
    CASE
        WHEN payment_count = 0 THEN 'no_payment'
        WHEN item_count = 0 THEN 'no_items'
        WHEN payment_value > product_value + freight_value THEN 'payment_higher'
        ELSE 'payment_lower'
    END AS difference_type
FROM dw.fact_orders
WHERE payment_value <> product_value + freight_value;
