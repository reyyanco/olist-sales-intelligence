-- Kategori çevirisi politikasının sonucu: ürün ve kategori sayıları.
SELECT category_translation_status,
       count(*)                      AS product_count,
       count(DISTINCT category_name) AS category_count,
       string_agg(DISTINCT category_name, ', ') FILTER (WHERE category_translation_status = 'untranslated') AS untranslated_categories
FROM dw.dim_product
GROUP BY category_translation_status
ORDER BY category_translation_status;
