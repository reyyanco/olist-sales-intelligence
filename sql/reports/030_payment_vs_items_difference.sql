-- Ödeme toplamı ile kalem fiyatı + kargo toplamı arasındaki farklar (zorla eşitlenmez).
SELECT in_sales_scope,
       difference_type,
       count(*)                AS order_count,
       sum(difference)         AS total_difference,
       min(difference)         AS min_difference,
       max(difference)         AS max_difference
FROM reporting.v_order_payment_differences
GROUP BY in_sales_scope, difference_type
ORDER BY in_sales_scope DESC, difference_type;
