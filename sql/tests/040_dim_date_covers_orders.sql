-- Tarih boyutu boşluksuz olmalı ve siparişlerdeki en erken/en geç tarihle başlayıp bitmeli.
-- Sonuç satırı = uyumsuzluk.
WITH bounds AS (
    SELECT least(min(purchase_ts::date), min(delivered_customer_ts::date), min(estimated_delivery_date)) AS lo,
           greatest(max(purchase_ts::date), max(delivered_customer_ts::date), max(estimated_delivery_date)) AS hi
    FROM dw.fact_orders
), dim AS (
    SELECT min(full_date) AS lo, max(full_date) AS hi, count(*) AS days FROM dw.dim_date
)
SELECT b.lo AS expected_start, d.lo AS actual_start, b.hi AS expected_end, d.hi AS actual_end,
       (b.hi - b.lo + 1) AS expected_days, d.days AS actual_days
FROM bounds b, dim d
WHERE b.lo IS DISTINCT FROM d.lo OR b.hi IS DISTINCT FROM d.hi OR (b.hi - b.lo + 1) IS DISTINCT FROM d.days;
