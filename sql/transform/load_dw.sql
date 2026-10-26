-- staging -> dw tam yenileme. etl/pipeline.py tarafından staging yüklemesiyle AYNI işlemde çalıştırılır;
-- herhangi bir adım hata verirse staging, dw, reporting ve ret kayıtları birlikte geri alınır.
-- Kurallar: docs/etl_pipeline.md

DO $$
BEGIN
    IF NULLIF(current_setting('etl.run_id', true), '') IS NULL THEN
        RAISE EXCEPTION 'etl.run_id ayarlı değil; dönüşüm etl/pipeline.py üzerinden çalıştırılmalı';
    END IF;
END
$$;

-- 1) Satır doğrulaması. q_* tabloları: kaynak kolonlar + natural_key + raw_record + reasons + disposition.
--    Boş metin ('') ve NULL aynı kabul edilir (eksik değer). Kimlikler ve posta kodları metin kalır.

CREATE TEMP TABLE q_customers ON COMMIT DROP AS
SELECT s.*, s.customer_id AS natural_key, to_jsonb(s) - '_row_id' AS raw_record, 'accepted'::text AS disposition,
    array_remove(ARRAY[
        CASE WHEN s.customer_id IS NULL OR s.customer_id !~ '^[0-9a-f]{32}$' THEN 'invalid_customer_id' END,
        CASE WHEN s.customer_unique_id IS NULL OR s.customer_unique_id !~ '^[0-9a-f]{32}$' THEN 'invalid_customer_unique_id' END,
        CASE WHEN s.customer_zip_code_prefix IS NULL OR s.customer_zip_code_prefix !~ '^[0-9]{5}$' THEN 'invalid_zip_code_prefix' END,
        CASE WHEN NULLIF(s.customer_city, '') IS NULL THEN 'missing_city' END,
        CASE WHEN s.customer_state IS NULL OR s.customer_state !~ '^[A-Z]{2}$' THEN 'invalid_state' END
    ]::text[], NULL) AS reasons
FROM staging.customers s;

CREATE TEMP TABLE q_sellers ON COMMIT DROP AS
SELECT s.*, s.seller_id AS natural_key, to_jsonb(s) - '_row_id' AS raw_record, 'accepted'::text AS disposition,
    array_remove(ARRAY[
        CASE WHEN s.seller_id IS NULL OR s.seller_id !~ '^[0-9a-f]{32}$' THEN 'invalid_seller_id' END,
        CASE WHEN s.seller_zip_code_prefix IS NULL OR s.seller_zip_code_prefix !~ '^[0-9]{5}$' THEN 'invalid_zip_code_prefix' END,
        CASE WHEN NULLIF(s.seller_city, '') IS NULL THEN 'missing_city' END,
        CASE WHEN s.seller_state IS NULL OR s.seller_state !~ '^[A-Z]{2}$' THEN 'invalid_state' END
    ]::text[], NULL) AS reasons
FROM staging.sellers s;

CREATE TEMP TABLE q_translation ON COMMIT DROP AS
SELECT s.*, s.product_category_name AS natural_key, to_jsonb(s) - '_row_id' AS raw_record, 'accepted'::text AS disposition,
    array_remove(ARRAY[
        CASE WHEN NULLIF(s.product_category_name, '') IS NULL THEN 'missing_category_name' END,
        CASE WHEN NULLIF(s.product_category_name_english, '') IS NULL THEN 'missing_category_name_english' END
    ]::text[], NULL) AS reasons
FROM staging.category_translation s;

-- Ürün sayısal alanları boş olabilir (profil: kategorisi boş 610 üründe boş); doluysa tam sayı olmalı.
CREATE TEMP TABLE q_products ON COMMIT DROP AS
SELECT s.*, s.product_id AS natural_key, to_jsonb(s) - '_row_id' AS raw_record, 'accepted'::text AS disposition,
    array_remove(ARRAY[
        CASE WHEN s.product_id IS NULL OR s.product_id !~ '^[0-9a-f]{32}$' THEN 'invalid_product_id' END,
        CASE WHEN NULLIF(s.product_name_lenght, '') IS NULL THEN NULL WHEN s.product_name_lenght !~ '^[0-9]{1,9}$' THEN 'invalid_name_length' WHEN s.product_name_lenght::int = 0 THEN 'invalid_name_length' END,
        CASE WHEN NULLIF(s.product_description_lenght, '') IS NULL THEN NULL WHEN s.product_description_lenght !~ '^[0-9]{1,9}$' THEN 'invalid_description_length' WHEN s.product_description_lenght::int = 0 THEN 'invalid_description_length' END,
        CASE WHEN NULLIF(s.product_photos_qty, '') IS NULL THEN NULL WHEN s.product_photos_qty !~ '^[0-9]{1,9}$' THEN 'invalid_photos_qty' WHEN s.product_photos_qty::int = 0 THEN 'invalid_photos_qty' END,
        CASE WHEN NULLIF(s.product_weight_g, '') IS NOT NULL AND s.product_weight_g !~ '^[0-9]{1,9}$' THEN 'invalid_weight_g' END,
        CASE WHEN NULLIF(s.product_length_cm, '') IS NULL THEN NULL WHEN s.product_length_cm !~ '^[0-9]{1,9}$' THEN 'invalid_length_cm' WHEN s.product_length_cm::int = 0 THEN 'invalid_length_cm' END,
        CASE WHEN NULLIF(s.product_height_cm, '') IS NULL THEN NULL WHEN s.product_height_cm !~ '^[0-9]{1,9}$' THEN 'invalid_height_cm' WHEN s.product_height_cm::int = 0 THEN 'invalid_height_cm' END,
        CASE WHEN NULLIF(s.product_width_cm, '') IS NULL THEN NULL WHEN s.product_width_cm !~ '^[0-9]{1,9}$' THEN 'invalid_width_cm' WHEN s.product_width_cm::int = 0 THEN 'invalid_width_cm' END
    ]::text[], NULL) AS reasons
FROM staging.products s;

-- Sipariş zamanları: satın alma ve tahmini teslim zorunlu; diğerleri boş olabilir (teslim edilmemiş
-- siparişte teslim zamanının boş olması hata değildir). Doluysa takvimde geçerli olmalı.
CREATE TEMP TABLE q_orders ON COMMIT DROP AS
SELECT s.*, s.order_id AS natural_key, to_jsonb(s) - '_row_id' AS raw_record, 'accepted'::text AS disposition,
    array_remove(ARRAY[
        CASE WHEN s.order_id IS NULL OR s.order_id !~ '^[0-9a-f]{32}$' THEN 'invalid_order_id' END,
        CASE WHEN s.customer_id IS NULL OR s.customer_id !~ '^[0-9a-f]{32}$' THEN 'invalid_customer_id' END,
        CASE WHEN s.order_status IS NULL OR s.order_status NOT IN (
                 'created', 'approved', 'invoiced', 'processing', 'shipped', 'delivered', 'canceled', 'unavailable')
             THEN 'invalid_order_status' END,
        CASE WHEN NOT meta.is_valid_timestamp(s.order_purchase_timestamp) THEN 'invalid_purchase_timestamp' END,
        CASE WHEN NULLIF(s.order_approved_at, '') IS NOT NULL AND NOT meta.is_valid_timestamp(s.order_approved_at) THEN 'invalid_approved_at' END,
        CASE WHEN NULLIF(s.order_delivered_carrier_date, '') IS NOT NULL AND NOT meta.is_valid_timestamp(s.order_delivered_carrier_date) THEN 'invalid_delivered_carrier_date' END,
        CASE WHEN NULLIF(s.order_delivered_customer_date, '') IS NOT NULL AND NOT meta.is_valid_timestamp(s.order_delivered_customer_date) THEN 'invalid_delivered_customer_date' END,
        CASE WHEN NOT meta.is_valid_timestamp(s.order_estimated_delivery_date) THEN 'invalid_estimated_delivery_date'
             WHEN s.order_estimated_delivery_date !~ ' 00:00:00$' THEN 'estimated_delivery_has_time' END,
        CASE WHEN NOT (meta.is_valid_timestamp(s.order_purchase_timestamp) AND meta.is_valid_timestamp(s.order_approved_at)) THEN NULL
             WHEN s.order_approved_at::timestamp < s.order_purchase_timestamp::timestamp THEN 'approved_before_purchase' END,
        CASE WHEN NOT (meta.is_valid_timestamp(s.order_purchase_timestamp) AND meta.is_valid_timestamp(s.order_delivered_customer_date)) THEN NULL
             WHEN s.order_delivered_customer_date::timestamp < s.order_purchase_timestamp::timestamp THEN 'delivered_before_purchase' END
    ]::text[], NULL) AS reasons
FROM staging.orders s;

-- Para: en fazla 10 tam ve 2 ondalık hane (NUMERIC(12,2) sessiz yuvarlama yapmasın).
CREATE TEMP TABLE q_items ON COMMIT DROP AS
SELECT s.*, s.order_id || ':' || s.order_item_id AS natural_key, to_jsonb(s) - '_row_id' AS raw_record, 'accepted'::text AS disposition,
    array_remove(ARRAY[
        CASE WHEN s.order_id IS NULL OR s.order_id !~ '^[0-9a-f]{32}$' THEN 'invalid_order_id' END,
        CASE WHEN s.order_item_id IS NULL OR s.order_item_id !~ '^[1-9][0-9]{0,3}$' THEN 'invalid_order_item_id' END,
        CASE WHEN s.product_id IS NULL OR s.product_id !~ '^[0-9a-f]{32}$' THEN 'invalid_product_id' END,
        CASE WHEN s.seller_id IS NULL OR s.seller_id !~ '^[0-9a-f]{32}$' THEN 'invalid_seller_id' END,
        CASE WHEN NOT meta.is_valid_timestamp(s.shipping_limit_date) THEN 'invalid_shipping_limit_date' END,
        CASE WHEN s.price IS NULL OR s.price !~ '^[0-9]{1,10}(\.[0-9]{1,2})?$' THEN 'invalid_price'
             WHEN s.price::numeric = 0 THEN 'non_positive_price' END,
        CASE WHEN s.freight_value IS NULL OR s.freight_value !~ '^[0-9]{1,10}(\.[0-9]{1,2})?$' THEN 'invalid_freight_value' END
    ]::text[], NULL) AS reasons
FROM staging.order_items s;

CREATE TEMP TABLE q_payments ON COMMIT DROP AS
SELECT s.*, s.order_id || ':' || s.payment_sequential AS natural_key, to_jsonb(s) - '_row_id' AS raw_record, 'accepted'::text AS disposition,
    array_remove(ARRAY[
        CASE WHEN s.order_id IS NULL OR s.order_id !~ '^[0-9a-f]{32}$' THEN 'invalid_order_id' END,
        CASE WHEN s.payment_sequential IS NULL OR s.payment_sequential !~ '^[1-9][0-9]{0,3}$' THEN 'invalid_payment_sequential' END,
        CASE WHEN s.payment_type IS NULL OR s.payment_type NOT IN ('credit_card', 'boleto', 'voucher', 'debit_card', 'not_defined')
             THEN 'invalid_payment_type' END,
        CASE WHEN s.payment_installments IS NULL OR s.payment_installments !~ '^[0-9]{1,4}$' THEN 'invalid_payment_installments' END,
        CASE WHEN s.payment_value IS NULL OR s.payment_value !~ '^[0-9]{1,10}(\.[0-9]{1,2})?$' THEN 'invalid_payment_value' END
    ]::text[], NULL) AS reasons
FROM staging.order_payments s;

-- Yorum anahtarı review_id + order_id (profil: review_id tek başına benzersiz değil).
CREATE TEMP TABLE q_reviews ON COMMIT DROP AS
SELECT s.*, s.review_id || ':' || s.order_id AS natural_key, to_jsonb(s) - '_row_id' AS raw_record, 'accepted'::text AS disposition,
    array_remove(ARRAY[
        CASE WHEN s.review_id IS NULL OR s.review_id !~ '^[0-9a-f]{32}$' THEN 'invalid_review_id' END,
        CASE WHEN s.order_id IS NULL OR s.order_id !~ '^[0-9a-f]{32}$' THEN 'invalid_order_id' END,
        CASE WHEN s.review_score IS NULL OR s.review_score !~ '^[1-5]$' THEN 'invalid_review_score' END,
        CASE WHEN NOT meta.is_valid_timestamp(s.review_creation_date) THEN 'invalid_review_creation_date' END,
        CASE WHEN NOT meta.is_valid_timestamp(s.review_answer_timestamp) THEN 'invalid_review_answer_timestamp' END
    ]::text[], NULL) AS reasons
FROM staging.order_reviews s;

-- Geçici tabloları autovacuum hiç analiz etmez; ilişki ve tekrar adımlarındaki planlar için istatistik.
ANALYZE q_customers, q_sellers, q_translation, q_products, q_orders, q_items, q_payments, q_reviews;

-- 2) Tekrarlar ve çelişkiler (her tabloda aynı kural):
--    - Aynı doğal anahtarın birden fazla FARKLI sürümü varsa: hiçbiri seçilmez, hepsi 'conflicting_key' ile reddedilir.
--    - Birebir aynı tekrar satırlar: ilk kaynak satırı kalır, diğerleri 'duplicate_removed'.
DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['q_customers', 'q_sellers', 'q_translation', 'q_products',
                             'q_orders', 'q_items', 'q_payments', 'q_reviews'] LOOP
        EXECUTE format($f$
            UPDATE %1$I q SET reasons = q.reasons || 'conflicting_key'::text
            FROM (SELECT natural_key FROM %1$I WHERE natural_key IS NOT NULL
                  GROUP BY natural_key HAVING count(DISTINCT raw_record) > 1) c
            WHERE q.natural_key = c.natural_key
        $f$, t);
        EXECUTE format($f$UPDATE %1$I SET disposition = 'rejected' WHERE cardinality(reasons) > 0$f$, t);
        EXECUTE format($f$
            UPDATE %1$I q SET disposition = 'duplicate_removed', reasons = ARRAY['exact_duplicate']
            FROM (SELECT _row_id, row_number() OVER (PARTITION BY natural_key ORDER BY _row_id) AS rn
                  FROM %1$I WHERE disposition = 'accepted') d
            WHERE q._row_id = d._row_id AND d.rn > 1
        $f$, t);
    END LOOP;
END
$$;

-- 3) İlişkiler. "not_found": kaynakta hiç yok; "rejected": kaynakta var ama reddedildi.
UPDATE q_orders o
SET disposition = 'rejected',
    reasons = o.reasons || CASE WHEN EXISTS (SELECT 1 FROM q_customers c WHERE c.natural_key = o.customer_id)
                                THEN 'customer_rejected' ELSE 'customer_not_found' END
WHERE o.disposition = 'accepted'
  AND NOT EXISTS (SELECT 1 FROM q_customers c WHERE c.natural_key = o.customer_id AND c.disposition = 'accepted');

UPDATE q_items i
SET disposition = 'rejected',
    reasons = i.reasons || CASE WHEN EXISTS (SELECT 1 FROM q_products p WHERE p.natural_key = i.product_id)
                                THEN 'product_rejected' ELSE 'product_not_found' END
WHERE i.disposition = 'accepted'
  AND NOT EXISTS (SELECT 1 FROM q_products p WHERE p.natural_key = i.product_id AND p.disposition = 'accepted');

UPDATE q_items i
SET disposition = 'rejected',
    reasons = i.reasons || CASE WHEN EXISTS (SELECT 1 FROM q_sellers s WHERE s.natural_key = i.seller_id)
                                THEN 'seller_rejected' ELSE 'seller_not_found' END
WHERE i.disposition = 'accepted'
  AND NOT EXISTS (SELECT 1 FROM q_sellers s WHERE s.natural_key = i.seller_id AND s.disposition = 'accepted');

-- Sipariş bütünlüğü: kalemi veya ödemesi reddedilen sipariş eksik tutarla yüklenmez, bütünüyle reddedilir.
UPDATE q_orders o
SET disposition = 'rejected', reasons = o.reasons || 'item_rejected'::text
WHERE o.disposition = 'accepted'
  AND EXISTS (SELECT 1 FROM q_items i WHERE i.order_id = o.order_id AND i.disposition = 'rejected');

UPDATE q_orders o
SET disposition = 'rejected', reasons = o.reasons || 'payment_rejected'::text
WHERE o.disposition = 'accepted'
  AND EXISTS (SELECT 1 FROM q_payments p WHERE p.order_id = o.order_id AND p.disposition = 'rejected');

-- Kabul edilmeyen siparişin kalemleri, ödemeleri ve yorumları da kabul edilmez.
UPDATE q_items i
SET disposition = 'rejected',
    reasons = i.reasons || CASE WHEN EXISTS (SELECT 1 FROM q_orders o WHERE o.natural_key = i.order_id)
                                THEN 'order_rejected' ELSE 'order_not_found' END
WHERE i.disposition = 'accepted'
  AND NOT EXISTS (SELECT 1 FROM q_orders o WHERE o.natural_key = i.order_id AND o.disposition = 'accepted');

UPDATE q_payments p
SET disposition = 'rejected',
    reasons = p.reasons || CASE WHEN EXISTS (SELECT 1 FROM q_orders o WHERE o.natural_key = p.order_id)
                                THEN 'order_rejected' ELSE 'order_not_found' END
WHERE p.disposition = 'accepted'
  AND NOT EXISTS (SELECT 1 FROM q_orders o WHERE o.natural_key = p.order_id AND o.disposition = 'accepted');

-- Yorum reddi siparişi etkilemez (yorumlar satış tutarına girmez).
UPDATE q_reviews r
SET disposition = 'rejected',
    reasons = r.reasons || CASE WHEN EXISTS (SELECT 1 FROM q_orders o WHERE o.natural_key = r.order_id)
                                THEN 'order_rejected' ELSE 'order_not_found' END
WHERE r.disposition = 'accepted'
  AND NOT EXISTS (SELECT 1 FROM q_orders o WHERE o.natural_key = r.order_id AND o.disposition = 'accepted');

-- 4) Ret ve tekrar kayıtları (bu çalışmanın run_id'si ile)
INSERT INTO meta.etl_rejected_rows (run_id, source_table, source_row, natural_key, disposition, reasons, raw_record)
SELECT meta.current_run_id(), 'customers', _row_id, natural_key, disposition, reasons, raw_record FROM q_customers WHERE disposition <> 'accepted'
UNION ALL SELECT meta.current_run_id(), 'sellers', _row_id, natural_key, disposition, reasons, raw_record FROM q_sellers WHERE disposition <> 'accepted'
UNION ALL SELECT meta.current_run_id(), 'category_translation', _row_id, natural_key, disposition, reasons, raw_record FROM q_translation WHERE disposition <> 'accepted'
UNION ALL SELECT meta.current_run_id(), 'products', _row_id, natural_key, disposition, reasons, raw_record FROM q_products WHERE disposition <> 'accepted'
UNION ALL SELECT meta.current_run_id(), 'orders', _row_id, natural_key, disposition, reasons, raw_record FROM q_orders WHERE disposition <> 'accepted'
UNION ALL SELECT meta.current_run_id(), 'order_items', _row_id, natural_key, disposition, reasons, raw_record FROM q_items WHERE disposition <> 'accepted'
UNION ALL SELECT meta.current_run_id(), 'order_payments', _row_id, natural_key, disposition, reasons, raw_record FROM q_payments WHERE disposition <> 'accepted'
UNION ALL SELECT meta.current_run_id(), 'order_reviews', _row_id, natural_key, disposition, reasons, raw_record FROM q_reviews WHERE disposition <> 'accepted';

-- 5) dw tam yenileme. TRUNCATE yerine DELETE: işlem sürerken okuyan oturumlar (dashboard)
--    kilitlenmeden önceki taahhüt edilmiş veriyi görmeye devam eder (MVCC).
DELETE FROM dw.fact_payments;
DELETE FROM dw.fact_sales;
DELETE FROM dw.fact_orders;
DELETE FROM dw.dim_customer;
DELETE FROM dw.dim_product;
DELETE FROM dw.dim_seller;
DELETE FROM dw.dim_date;

INSERT INTO dw.dim_customer (customer_id, customer_unique_id, zip_code_prefix, city, state)
SELECT customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state
FROM q_customers WHERE disposition = 'accepted';

INSERT INTO dw.dim_seller (seller_id, zip_code_prefix, city, state)
SELECT seller_id, seller_zip_code_prefix, seller_city, seller_state
FROM q_sellers WHERE disposition = 'accepted';

INSERT INTO dw.dim_product (
    product_id, category_name, category_name_english, name_length, description_length,
    photos_qty, weight_g, length_cm, height_cm, width_cm, category_translation_status, category_label
)
SELECT
    p.product_id,
    NULLIF(p.product_category_name, ''),
    t.product_category_name_english,
    NULLIF(p.product_name_lenght, '')::integer,
    NULLIF(p.product_description_lenght, '')::integer,
    NULLIF(p.product_photos_qty, '')::integer,
    NULLIF(p.product_weight_g, '')::integer,
    NULLIF(p.product_length_cm, '')::integer,
    NULLIF(p.product_height_cm, '')::integer,
    NULLIF(p.product_width_cm, '')::integer,
    CASE WHEN NULLIF(p.product_category_name, '') IS NULL THEN 'missing_category'
         WHEN t.product_category_name_english IS NULL THEN 'untranslated'
         ELSE 'translated' END,
    COALESCE(t.product_category_name_english, NULLIF(p.product_category_name, ''), 'uncategorized')
FROM q_products p
LEFT JOIN q_translation t
       ON t.disposition = 'accepted' AND t.product_category_name = NULLIF(p.product_category_name, '')
WHERE p.disposition = 'accepted';

-- Tarih boyutu: KABUL EDİLEN siparişlerin satın alma, teslim ve tahmini teslim tarihlerinin aralığı.
INSERT INTO dw.dim_date (
    date_key, full_date, year, quarter, month, month_start, day_of_month,
    iso_year, iso_week, iso_day_of_week, is_weekend
)
SELECT
    EXTRACT(YEAR FROM d)::int * 10000 + EXTRACT(MONTH FROM d)::int * 100 + EXTRACT(DAY FROM d)::int,
    d,
    EXTRACT(YEAR FROM d),
    EXTRACT(QUARTER FROM d),
    EXTRACT(MONTH FROM d),
    date_trunc('month', d)::date,
    EXTRACT(DAY FROM d),
    EXTRACT(ISOYEAR FROM d),
    EXTRACT(WEEK FROM d),
    EXTRACT(ISODOW FROM d),
    EXTRACT(ISODOW FROM d) IN (6, 7)
FROM (
    SELECT generate_series(min(x), max(x), interval '1 day')::date AS d
    FROM (
        SELECT order_purchase_timestamp::timestamp::date FROM q_orders WHERE disposition = 'accepted'
        UNION ALL
        SELECT NULLIF(order_delivered_customer_date, '')::timestamp::date FROM q_orders WHERE disposition = 'accepted'
        UNION ALL
        SELECT order_estimated_delivery_date::timestamp::date FROM q_orders WHERE disposition = 'accepted'
    ) AS all_dates (x)
) AS days
WHERE d IS NOT NULL;

-- Sipariş olgusu: kalem, ödeme ve yorumlar AYRI AYRI sipariş başına toplanır, sonra siparişe bağlanır.
INSERT INTO dw.fact_orders (
    order_id, customer_id, order_status, purchase_ts, approved_ts, delivered_carrier_ts,
    delivered_customer_ts, estimated_delivery_date, purchase_date_key,
    delivered_customer_date_key, estimated_delivery_date_key,
    item_count, product_value, freight_value, payment_count, payment_value,
    review_count, review_score_avg
)
WITH orders AS (
    SELECT
        order_id,
        customer_id,
        order_status,
        order_purchase_timestamp::timestamp                  AS purchase_ts,
        NULLIF(order_approved_at, '')::timestamp             AS approved_ts,
        NULLIF(order_delivered_carrier_date, '')::timestamp  AS delivered_carrier_ts,
        NULLIF(order_delivered_customer_date, '')::timestamp AS delivered_customer_ts,
        order_estimated_delivery_date::timestamp::date       AS estimated_delivery_date
    FROM q_orders
    WHERE disposition = 'accepted'
), items AS (
    SELECT order_id,
           count(*)                            AS item_count,
           sum(price::numeric(12,2))           AS product_value,
           sum(freight_value::numeric(12,2))   AS freight_value
    FROM q_items WHERE disposition = 'accepted'
    GROUP BY order_id
), payments AS (
    SELECT order_id,
           count(*)                            AS payment_count,
           sum(payment_value::numeric(12,2))   AS payment_value
    FROM q_payments WHERE disposition = 'accepted'
    GROUP BY order_id
), reviews AS (
    SELECT order_id,
           count(*)                                  AS review_count,
           round(avg(review_score::integer), 2)      AS review_score_avg
    FROM q_reviews WHERE disposition = 'accepted'
    GROUP BY order_id
)
SELECT
    o.order_id,
    o.customer_id,
    o.order_status,
    o.purchase_ts,
    o.approved_ts,
    o.delivered_carrier_ts,
    o.delivered_customer_ts,
    o.estimated_delivery_date,
    to_char(o.purchase_ts, 'YYYYMMDD')::int,
    to_char(o.delivered_customer_ts, 'YYYYMMDD')::int,
    to_char(o.estimated_delivery_date, 'YYYYMMDD')::int,
    COALESCE(i.item_count, 0),
    COALESCE(i.product_value, 0),
    COALESCE(i.freight_value, 0),
    COALESCE(p.payment_count, 0),
    COALESCE(p.payment_value, 0),
    COALESCE(r.review_count, 0),
    r.review_score_avg
FROM orders o
LEFT JOIN items    i USING (order_id)
LEFT JOIN payments p USING (order_id)
LEFT JOIN reviews  r USING (order_id);

-- Kalem olgusu: bir satır = kabul edilen bir kaynak kalem satırı. LEFT JOIN: beklenmedik bir
-- tutarsızlıkta kalem sessizce düşmez, NOT NULL kısıtına takılarak tüm yüklemeyi geri aldırır.
INSERT INTO dw.fact_sales (
    order_id, order_item_id, product_id, seller_id, customer_id, purchase_date_key,
    shipping_limit_ts, price, freight_value
)
SELECT
    i.order_id,
    i.order_item_id::smallint,
    i.product_id,
    i.seller_id,
    o.customer_id,
    o.purchase_date_key,
    i.shipping_limit_date::timestamp,
    i.price::numeric(12,2),
    i.freight_value::numeric(12,2)
FROM q_items i
LEFT JOIN dw.fact_orders o USING (order_id)
WHERE i.disposition = 'accepted';

INSERT INTO dw.fact_payments (order_id, payment_sequential, payment_type, payment_installments, payment_value)
SELECT order_id, payment_sequential::smallint, payment_type, payment_installments::smallint,
       payment_value::numeric(12,2)
FROM q_payments
WHERE disposition = 'accepted';

-- İstatistikler işlem İÇİNDE güncellenir: ANALYZE aynı işlemin eklediği satırları görür, autovacuum görmez.
-- Bu olmadan boş bir veritabanına ilk yüklemede planlayıcı tabloları boş sanır; gerçek veride kalite
-- kontrolü 9 dakikayı aşıp iptal edildi (docs/performance.md, F1).
ANALYZE dw.dim_customer, dw.dim_product, dw.dim_seller, dw.dim_date, dw.fact_orders, dw.fact_sales, dw.fact_payments;

-- 6) Rapor nesneleri (tüm reporting materialized view'leri + reporting.monthly_summary), bu işlemin içinde.
-- Doldurulmuş ve uygun UNIQUE index'i olan MV'ler CONCURRENTLY yenilenir (okuyanlar engellenmez);
-- ilk doldurma normal REFRESH ile yapılır. Kurallar: sql/150_report_routines.sql
SELECT reporting.refresh_report_objects();
