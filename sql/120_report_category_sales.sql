-- Analiz: kategori satışları ve kümülatif pay (Pareto). reporting.mv_category_sales
--
-- Kurallar:
-- - Satış kapsamı = delivered; tutar = ürün satış tutarı (kalem fiyatı toplamı, kargo hariç).
-- - Kategori adı category_label (çeviri politikası: docs/etl_pipeline.md).
-- - Sıralama: product_sales azalan, eşit tutarlarda category_label artan -> deterministik.
-- - Kümülatif toplam SUM() OVER (... ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW).
--   ROWS açıkça yazılır: varsayılan RANGE çerçevesi eşit tutarlı kategorileri aynı kümülatif
--   değerde birleştirirdi.
-- - Pay ve kümülatif pay toplam satışa bölünür; toplam 0 ise NULL (sıfır payda).
-- - order_count = kategoride en az bir kalemi olan farklı sipariş sayısı. Bir sipariş birden fazla
--   kategoride olabileceğinden kategori sipariş sayılarının toplamı toplam sipariş sayısından büyük olabilir.
--
-- Materialized view: ilk doldurma WITH DATA ile oluşturulurken yapılır (boş veritabanında 0 satırla
-- doldurulmuş sayılır). category_label üzerindeki UNIQUE index (yalnızca kolon adı, WHERE yok)
-- REFRESH ... CONCURRENTLY önkoşuludur. Yenileme: reporting.refresh_report_objects().

CREATE MATERIALIZED VIEW reporting.mv_category_sales AS
WITH categories AS (
    SELECT category_label,
           count(*)                  AS item_count,
           count(DISTINCT order_id)  AS order_count,
           sum(price)                AS product_sales
    FROM reporting.v_sales_items
    WHERE in_sales_scope
    GROUP BY category_label
), ranked AS (
    SELECT c.*,
           row_number() OVER w AS sales_rank,
           sum(c.product_sales) OVER (ORDER BY c.product_sales DESC, c.category_label
                                      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_sales,
           sum(c.product_sales) OVER () AS total_sales
    FROM categories c
    WINDOW w AS (ORDER BY c.product_sales DESC, c.category_label)
)
SELECT
    sales_rank::integer                                         AS sales_rank,
    category_label,
    item_count,
    order_count,
    product_sales::numeric(14,2)                                AS product_sales,
    round(product_sales / NULLIF(total_sales, 0), 4)            AS sales_share,
    cumulative_sales::numeric(14,2)                             AS cumulative_sales,
    round(cumulative_sales / NULLIF(total_sales, 0), 4)         AS cumulative_share
FROM ranked
WITH DATA;

CREATE UNIQUE INDEX mv_category_sales_label_uq ON reporting.mv_category_sales (category_label);

COMMENT ON MATERIALIZED VIEW reporting.mv_category_sales IS
    'Kategori ürün satışları, pay ve kümülatif pay; eşitlikte category_label ile deterministik sıra';
