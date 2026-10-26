-- Kategori çevirisi politikası (docs/etl_pipeline.md):
--   translated       : kategori var, çeviri var  -> category_label = İngilizce ad
--   untranslated     : kategori var, çeviri yok  -> category_label = Portekizce ad (değiştirilmeden)
--   missing_category : kategori boş              -> category_label = 'uncategorized'
-- category_name_english yalnızca kaynak çeviriyi taşır; uydurma çeviri yazılmaz.

ALTER TABLE dw.dim_product
    ADD COLUMN category_translation_status text,
    ADD COLUMN category_label text;

UPDATE dw.dim_product SET
    category_translation_status = CASE
        WHEN category_name IS NULL THEN 'missing_category'
        WHEN category_name_english IS NULL THEN 'untranslated'
        ELSE 'translated'
    END,
    category_label = COALESCE(category_name_english, category_name, 'uncategorized');

ALTER TABLE dw.dim_product
    ALTER COLUMN category_translation_status SET NOT NULL,
    ALTER COLUMN category_label SET NOT NULL,
    ADD CONSTRAINT dim_product_category_policy CHECK (
        (category_translation_status = 'translated'
            AND category_name IS NOT NULL AND category_name_english IS NOT NULL
            AND category_label = category_name_english)
        OR (category_translation_status = 'untranslated'
            AND category_name IS NOT NULL AND category_name_english IS NULL
            AND category_label = category_name)
        OR (category_translation_status = 'missing_category'
            AND category_name IS NULL AND category_name_english IS NULL
            AND category_label = 'uncategorized')
    );

-- Mevcut kolon sırası korunur; yeni kolonlar sona eklenir.
CREATE OR REPLACE VIEW reporting.v_sales_items AS
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
    s.freight_value,
    p.category_label,
    p.category_translation_status
FROM dw.fact_sales s
JOIN dw.fact_orders o USING (order_id)
JOIN dw.dim_customer c ON c.customer_id = s.customer_id
JOIN dw.dim_product p USING (product_id);
