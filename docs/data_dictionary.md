# Veri Sözlüğü

Şema kaynağı: `sql/` altındaki numaralı dosyalar. Kısıtların gerekçesi `docs/data_profile.md` ölçümleridir. Metrik anlamları: `docs/metric_definitions.md`.

## staging (ham katman)

- Her tablo bir kaynak CSV'nin birebir kopyasıdır: aynı kolon adları (kaynaktaki `lenght` yazımı dahil) ve **tüm değerler `text`**.
- Kısıt yoktur; kirli bir satır yükleme sırasında kaybolmaz, dönüşümde nedeniyle reddedilir.
- Tek teknik kolon `_row_id`'dir: dosyadaki veri kaydının sırası (başlık hariç, 1'den başlar).

| Tablo | Dosya | Satır (gerçek) | Doğal anahtar |
|---|---|---:|---|
| `staging.customers` | `olist_customers_dataset.csv` | 99.441 | `customer_id` |
| `staging.geolocation` | `olist_geolocation_dataset.csv` | 1.000.163 | yok (posta kodu başına çok satır) |
| `staging.orders` | `olist_orders_dataset.csv` | 99.441 | `order_id` |
| `staging.order_items` | `olist_order_items_dataset.csv` | 112.650 | `order_id` + `order_item_id` |
| `staging.order_payments` | `olist_order_payments_dataset.csv` | 103.886 | `order_id` + `payment_sequential` |
| `staging.order_reviews` | `olist_order_reviews_dataset.csv` | 99.224 | `review_id` + `order_id` |
| `staging.products` | `olist_products_dataset.csv` | 32.951 | `product_id` |
| `staging.sellers` | `olist_sellers_dataset.csv` | 3.095 | `seller_id` |
| `staging.category_translation` | `product_category_name_translation.csv` (BOM'lu) | 71 | `product_category_name` |

## dw.dim_date

Grain: takvim günü. Kapsam, **kabul edilen** siparişlerin satın alma, teslim ve tahmini teslim tarihlerinin en erken ve en geç gününden üretilir. Gerçek veride bu aralık 2016-09-04 … 2018-11-12 (800 gün).

| Kolon | Tip | Kısıt / açıklama |
|---|---|---|
| `date_key` | integer | PK; `YYYYMMDD`, `full_date` ile tutarlı (CHECK) |
| `full_date` | date | UNIQUE |
| `year`, `quarter`, `month`, `day_of_month` | smallint | aralık CHECK'leri |
| `month_start` | date | ayın ilk günü (CHECK) |
| `iso_year`, `iso_week`, `iso_day_of_week` | smallint | ISO 8601; gün 1 = Pazartesi |
| `is_weekend` | boolean | Cumartesi/Pazar |

## dw.dim_customer

Grain: `customer_id`, yani sipariş başına müşteri kaydı. Gerçek veride 1 sipariş = 1 `customer_id`.

| Kolon | Tip | Kaynak | Kısıt / açıklama |
|---|---|---|---|
| `customer_id` | text | `customer_id` | PK; `^[0-9a-f]{32}$` |
| `customer_unique_id` | text | `customer_unique_id` | NOT NULL; 32 hex; **kişi kimliği** (RFM, tekrar alım); indeksli |
| `zip_code_prefix` | text | `customer_zip_code_prefix` | `^[0-9]{5}$`; baştaki sıfır korunur |
| `city` | text | `customer_city` | NOT NULL, olduğu gibi |
| `state` | text | `customer_state` | `^[A-Z]{2}$` |

## dw.dim_product

Grain: `product_id`.

| Kolon | Tip | Kaynak | Kısıt / açıklama |
|---|---|---|---|
| `product_id` | text | `product_id` | PK; 32 hex |
| `category_name` | text | `product_category_name` | boş olabilir (610 ürün) |
| `category_name_english` | text | çeviri dosyası | yalnızca kaynak çeviri; çevirisi yoksa NULL |
| `category_label` | text | türetilmiş | raporlamada kullanılacak ad (politika: `docs/etl_pipeline.md`) |
| `category_translation_status` | text | türetilmiş | `translated` / `untranslated` / `missing_category`; `category_label` ile tutarlılığı CHECK ile zorunlu |
| `name_length` | integer | `product_name_lenght` | > 0 veya NULL |
| `description_length` | integer | `product_description_lenght` | > 0 veya NULL |
| `photos_qty` | integer | `product_photos_qty` | > 0 veya NULL |
| `weight_g` | integer | `product_weight_g` | ≥ 0 veya NULL (profilde 0 değeri var) |
| `length_cm`, `height_cm`, `width_cm` | integer | aynı adlı kolonlar | > 0 veya NULL |

## dw.dim_seller

Grain: `seller_id`.

| Kolon | Tip | Kaynak | Kısıt |
|---|---|---|---|
| `seller_id` | text | `seller_id` | PK; 32 hex |
| `zip_code_prefix` | text | `seller_zip_code_prefix` | 5 hane metin |
| `city` | text | `seller_city` | NOT NULL, olduğu gibi (kaynakta "04482255" gibi kirli değerler var; değiştirilmez) |
| `state` | text | `seller_state` | 2 büyük harf |

## dw.fact_orders

Grain: **bir satır = bir sipariş**. Kalem, ödeme ve yorum ölçüleri sipariş başına **ayrı ayrı önceden toplanır**.

| Kolon | Tip | Kaynak | Kısıt / açıklama |
|---|---|---|---|
| `order_id` | text | `order_id` | PK; 32 hex |
| `customer_id` | text | `customer_id` | FK `dim_customer`; UNIQUE |
| `order_status` | text | `order_status` | 8 bilinen değerden biri |
| `purchase_ts` | timestamp | `order_purchase_timestamp` | NOT NULL; saat dilimi yok, dönüştürülmez |
| `approved_ts` | timestamp | `order_approved_at` | boş olabilir; ≥ `purchase_ts` |
| `delivered_carrier_ts` | timestamp | `order_delivered_carrier_date` | boş olabilir; sıralama kısıtı **yok** (166 kayıtta satın almadan önce) |
| `delivered_customer_ts` | timestamp | `order_delivered_customer_date` | boş olabilir (teslim edilmemiş sipariş hata değil); ≥ `purchase_ts` |
| `estimated_delivery_date` | date | `order_estimated_delivery_date` | NOT NULL; kaynakta her zaman 00:00:00 |
| `purchase_date_key`, `estimated_delivery_date_key` | integer | türetilmiş | FK `dim_date`; zamanla tutarlı (CHECK) |
| `delivered_customer_date_key` | integer | türetilmiş | FK `dim_date`; teslim zamanı yoksa NULL |
| `item_count` | integer | kalemler | ≥ 0; kalemsiz siparişte 0 |
| `product_value`, `freight_value` | numeric(12,2) | `price`, `freight_value` toplamı | ≥ 0; kalem yoksa 0 |
| `payment_count` | integer | ödemeler | ≥ 0 |
| `payment_value` | numeric(12,2) | `payment_value` toplamı | ≥ 0; ödeme yoksa 0 ve `payment_count = 0` |
| `review_count` | integer | yorumlar | ≥ 0 |
| `review_score_avg` | numeric(3,2) | `review_score` ortalaması | 1–5; yorum yoksa NULL |
| `delivery_days` | numeric(8,2) | üretilmiş | (teslim − satın alma) gün; teslim yoksa NULL |
| `is_late` | boolean | üretilmiş | teslim günü > tahmini gün; teslim yoksa NULL |

## dw.fact_sales

Grain: **bir satır = bir sipariş kalemi** (`order_id`, `order_item_id`). Kaynakta `quantity` yoktur (bkz. `docs/metric_definitions.md`).

| Kolon | Tip | Kaynak | Kısıt |
|---|---|---|---|
| `order_id` + `order_item_id` | text + smallint | aynı adlı kolonlar | PK; `order_item_id` ≥ 1 |
| `product_id` | text | `product_id` | FK `dim_product` |
| `seller_id` | text | `seller_id` | FK `dim_seller` |
| `customer_id`, `purchase_date_key` | text, integer | siparişten | (`order_id`, `customer_id`, `purchase_date_key`) birlikte FK `fact_orders`; kopya anahtarlar siparişle tutarlı kalır |
| `shipping_limit_ts` | timestamp | `shipping_limit_date` | NOT NULL (kaynakta 2020'ye kadar değerler var; değiştirilmez) |
| `price` | numeric(12,2) | `price` | > 0 (profilde sıfır yok) |
| `freight_value` | numeric(12,2) | `freight_value` | ≥ 0 (383 kalemde 0) |

## dw.fact_payments

Grain: bir ödeme kaydı (`order_id`, `payment_sequential`).

| Kolon | Tip | Kısıt |
|---|---|---|
| `order_id` + `payment_sequential` | text + smallint | PK; FK `fact_orders`; sıra ≥ 1 (80 siparişte sıra kesintili; kısıt yok) |
| `payment_type` | text | `credit_card`, `boleto`, `voucher`, `debit_card`, `not_defined` |
| `payment_installments` | smallint | ≥ 0 (2 kayıtta 0) |
| `payment_value` | numeric(12,2) | ≥ 0 (9 kayıtta 0) |

## reporting

| Nesne | Tür | Grain / içerik |
|---|---|---|
| `v_orders` | view | sipariş; `customer_unique_id`, `in_sales_scope`, `purchase_month` ekli |
| `v_sales_items` | view | kalem; kategori etiketi, kapsam bayrağı. Sipariş düzeyi ölçü **içermez** |
| `v_customer_purchases` | view | `customer_unique_id`; kapsamdaki sipariş sayısı, ilk/son satın alma, tutarlar |
| `v_rfm_observation` | view | tek satır: gözlem aralığı ve gözlem tarihi |
| `v_customer_rfm_base` | view | `customer_unique_id`; recency, frequency, monetary |
| `mv_monthly_sales` | materialized view | satın alma ayı; kapsam metrikleri. ETL sonunda yenilenir |
| `v_sales_kpis` | view | tek satır; tüm dönem kapsam metrikleri |
| `v_order_payment_differences` | view | ödeme ≠ kalem + kargo olan siparişler ve fark türü |
| `v_monthly_sales_growth` | view | `dim_date` ayı (satışsız aylar 0); önceki aya göre büyüme ve `growth_status` |
| `mv_category_sales` | materialized view | `category_label`; tutar, pay, kümülatif pay, sıra (UNIQUE `category_label`) |
| `v_delivery_performance` | view | ROLLUP: ay / yıl / toplam; teslimat süresi, geç teslim oranı, süre dilimleri |
| `v_repeat_purchase` | view | ilk satın alma ayı kohortu + toplam; tekrar satın alma oranı |
| `monthly_summary` | tablo | ay (PK `month_start`); `v_monthly_sales_growth` ile aynı kolonlar + `loaded_at`; `sp_load_monthly_summary(year)` ile yüklenir |
| `fn_customer_rfm(as_of date)` | fonksiyon | `customer_unique_id`; recency, frequency, monetary, R/F/M puanı, `rfm_code`, segment |

Rutinler (`sp_load_monthly_summary`, `refresh_report_objects`, `sp_refresh_reports`) ve işlem kuralları: `docs/reporting.md`.

## meta

| Tablo | Grain | Açıklama |
|---|---|---|
| `schema_migrations` | SQL dosyası | uygulanan numaralı dosya, SHA-256, zaman |
| `etl_runs` | çalışma | `run_id`, başlangıç/bitiş, süre, durum (`running`/`succeeded`/`failed`), hata |
| `etl_run_files` | çalışma × dosya | SHA-256, bayt, kaynak/staging/kabul/ret/tekrar sayıları, COPY süresi |
| `etl_run_checks` | çalışma × kontrol | `error`/`info` düzeyi, geçti mi, bulunan satırlar (jsonb) |
| `etl_rejected_rows` | çalışma × kaynak satır | `rejected` veya `duplicate_removed`, nedenler, ham kayıt (jsonb) |
| `report_refresh_runs` | `sp_refresh_reports` çağrısı | başlangıç/bitiş, durum, yenilenen nesneler ve yöntem (jsonb), hata (SQLSTATE: mesaj) |

Fonksiyonlar:

- `meta.current_run_id()`: işlem içindeyse o çalışmanın kimliği, dışındaysa son başarılı çalışma.
- `meta.is_valid_timestamp(text)`: biçim ve takvim geçerliliği kontrolü.
