# Kaynak Veri Profili

Kaynak klasör: `data/raw`. Bu rapor `python -m etl profile` ile dosyalardan üretilir; elle düzenlenmez.
Tüm değerler metin olarak okunmuştur. 'Boş' = boş hücre.

## Dosyalar

| Tablo | Dosya | Satır | Kolon | BOM |
|---|---|---:|---:|---|
| customers | `olist_customers_dataset.csv` | 99,441 | 5 | yok |
| geolocation | `olist_geolocation_dataset.csv` | 1,000,163 | 5 | yok |
| orders | `olist_orders_dataset.csv` | 99,441 | 8 | yok |
| order_items | `olist_order_items_dataset.csv` | 112,650 | 7 | yok |
| order_payments | `olist_order_payments_dataset.csv` | 103,886 | 5 | yok |
| order_reviews | `olist_order_reviews_dataset.csv` | 99,224 | 7 | yok |
| products | `olist_products_dataset.csv` | 32,951 | 9 | yok |
| sellers | `olist_sellers_dataset.csv` | 3,095 | 4 | yok |
| category_translation | `product_category_name_translation.csv` | 71 | 2 | var |

## Aday anahtarlar

| Tablo | Kolonlar | Satır | Tekrarlanan anahtar değeri | Benzersiz mi |
|---|---|---:|---:|---|
| customers | `customer_id` | 99,441 | 0 | evet |
| customers | `customer_unique_id` | 99,441 | 2,997 | hayır |
| orders | `order_id` | 99,441 | 0 | evet |
| orders | `customer_id` | 99,441 | 0 | evet |
| order_items | `order_id, order_item_id` | 112,650 | 0 | evet |
| order_payments | `order_id, payment_sequential` | 103,886 | 0 | evet |
| order_reviews | `review_id` | 99,224 | 789 | hayır |
| order_reviews | `order_id` | 99,224 | 547 | hayır |
| order_reviews | `review_id, order_id` | 99,224 | 0 | evet |
| products | `product_id` | 32,951 | 0 | evet |
| sellers | `seller_id` | 3,095 | 0 | evet |
| category_translation | `product_category_name` | 71 | 0 | evet |
| geolocation | `geolocation_zip_code_prefix` | 1,000,163 | 17,972 | hayır |

## İlişkiler ve çokluklar

Yetim: alt tablodaki boş olmayan değerlerden üst tabloda karşılığı olmayanlar. Altsız üst: alt tabloda hiç kaydı olmayan üst değerler. Dağılım: alt tabloda görünen her üst değer için alt satır sayısı.

| Alt → Üst | Alt boş | Yetim değer | Yetim satır | Altsız üst | Üst başına alt satır dağılımı |
|---|---:|---:|---:|---:|---|
| `orders.customer_id` → `customers.customer_id` | 0 | 0 | 0 | 0 | 1: 99,441 · 2: 0 · 3+: 0 · en çok: 1 |
| `order_items.order_id` → `orders.order_id` | 0 | 0 | 0 | 775 | 1: 88,863 · 2: 7,516 · 3+: 2,287 · en çok: 21 |
| `order_items.product_id` → `products.product_id` | 0 | 0 | 0 | 0 | 1: 18,117 · 2: 5,817 · 3+: 9,017 · en çok: 527 |
| `order_items.seller_id` → `sellers.seller_id` | 0 | 0 | 0 | 0 | 1: 509 · 2: 328 · 3+: 2,258 · en çok: 2033 |
| `order_payments.order_id` → `orders.order_id` | 0 | 0 | 0 | 1 | 1: 96,479 · 2: 2,382 · 3+: 579 · en çok: 29 |
| `order_reviews.order_id` → `orders.order_id` | 0 | 0 | 0 | 768 | 1: 98,126 · 2: 543 · 3+: 4 · en çok: 3 |
| `products.product_category_name` → `category_translation.product_category_name` | 610 | 2 | 13 | 0 | 1: 1 · 2: 1 · 3+: 69 · en çok: 3029 |
| `customers.customer_zip_code_prefix` → `geolocation.geolocation_zip_code_prefix` | 0 | 157 | 278 | 4,178 | 1: 2,902 · 2: 2,121 · 3+: 9,814 · en çok: 142 |
| `sellers.seller_zip_code_prefix` → `geolocation.geolocation_zip_code_prefix` | 0 | 7 | 7 | 16,776 | 1: 1,702 · 2: 381 · 3+: 156 · en çok: 49 |

## Alana özgü kontroller

### Sipariş durumları

| order_status | Sipariş |
|---|---:|
| delivered | 96,478 |
| shipped | 1,107 |
| canceled | 625 |
| unavailable | 609 |
| invoiced | 314 |
| processing | 301 |
| created | 5 |
| approved | 2 |

### Sipariş zamanlarının duruma göre boş sayısı

| order_status | order_purchase_timestamp | order_approved_at | order_delivered_carrier_date | order_delivered_customer_date | order_estimated_delivery_date |
|---|---:|---:|---:|---:|---:|
| delivered | 0 | 14 | 2 | 8 | 0 |
| shipped | 0 | 0 | 0 | 1,107 | 0 |
| canceled | 0 | 141 | 550 | 619 | 0 |
| unavailable | 0 | 0 | 609 | 609 | 0 |
| invoiced | 0 | 0 | 314 | 314 | 0 |
| processing | 0 | 0 | 301 | 301 | 0 |
| created | 0 | 5 | 5 | 5 | 0 |
| approved | 0 | 0 | 2 | 2 | 0 |

### Zaman tutarlılığı

| Kontrol | Sipariş |
|---|---:|
| approved_at < purchase_timestamp | 0 |
| delivered_carrier_date < purchase_timestamp | 166 |
| delivered_carrier_date < approved_at | 1,359 |
| delivered_customer_date < purchase_timestamp | 0 |
| delivered_customer_date < delivered_carrier_date | 23 |
| estimated_delivery_date saati 00:00:00 değil | 0 |
| teslim tarihi (gün) > tahmini teslim tarihi (gün) | 6,535 |

| Zaman kolonu | En erken | En geç |
|---|---|---|
| `order_purchase_timestamp` | 2016-09-04 21:15:19 | 2018-10-17 17:30:18 |
| `order_approved_at` | 2016-09-15 12:16:38 | 2018-09-03 17:40:06 |
| `order_delivered_carrier_date` | 2016-10-08 10:34:01 | 2018-09-11 19:48:28 |
| `order_delivered_customer_date` | 2016-10-11 13:46:32 | 2018-10-17 13:22:46 |
| `order_estimated_delivery_date` | 2016-09-30 00:00:00 | 2018-11-12 00:00:00 |
| `order_items.shipping_limit_date` | 2016-09-19 00:15:34 | 2020-04-09 22:35:08 |
| `order_reviews.review_creation_date` | 2016-10-02 00:00:00 | 2018-08-31 00:00:00 |
| `order_reviews.review_answer_timestamp` | 2016-10-07 18:32:28 | 2018-10-29 12:27:35 |

### Sipariş kalemleri

| Kontrol | Değer |
|---|---:|
| order_item_id en küçük / en büyük | 1 / 21 |
| order_item_id 1..n kesintisiz olan sipariş | 98,666 / 98,666 |
| aynı ürün aynı siparişte birden fazla satır (sipariş-ürün çifti) | 7,088 |
| aynı sipariş-ürün çiftinde birden fazla farklı fiyat | 0 |
| price = 0 olan kalem | 0 |
| freight_value = 0 olan kalem | 383 |
| kalemi olmayan sipariş | 775 |

Kalemi olmayan siparişlerin durumları: unavailable=603, canceled=164, created=5, invoiced=2, shipped=1

### Ödemeler

| Kontrol | Değer |
|---|---:|
| payment_type değerleri | credit_card=76,795, boleto=19,784, voucher=5,775, debit_card=1,529, not_defined=3 |
| payment_installments en küçük / en büyük | 0 / 24 |
| payment_installments = 0 | 2 |
| payment_value = 0 | 9 |
| payment_sequential 1..n kesintisiz olan sipariş | 99,360 / 99,440 |
| ödemesi olmayan sipariş | 1 |
| ödeme toplamı = kalem fiyatı + kargo (±0,01) olan sipariş | 98,362 / 98,665 |
| ödeme toplamı > kalem + kargo (0,01'den fazla) | 264 |
| ödeme toplamı < kalem + kargo (0,01'den fazla) | 39 |

### Yorumlar

| Kontrol | Değer |
|---|---:|
| review_score değerleri | 1=11,424, 2=3,151, 3=8,179, 4=19,142, 5=57,328 |
| birden fazla siparişte görünen review_id | 789 |
| birden fazla yorumu olan sipariş | 547 |
| yorumu olmayan sipariş | 768 |

### Ürün, müşteri ve posta kodu

| Kontrol | Değer |
|---|---:|
| kategorisi boş ürün | 610 |
| çevirisi olmayan kategori | 2: pc_gamer, portateis_cozinha_e_preparadores_de_alimentos |
| birden fazla customer_id'si olan customer_unique_id | 2,997 |
| customer_unique_id başına customer_id en çok | 17 |
| `customers.customer_zip_code_prefix` uzunluk dağılımı | 5 hane: 99,441 |
| `sellers.seller_zip_code_prefix` uzunluk dağılımı | 5 hane: 3,095 |
| `geolocation.geolocation_zip_code_prefix` uzunluk dağılımı | 5 hane: 1,000,163 |
| `customers.customer_state` 2 büyük harf olmayan | 0 |
| `sellers.seller_state` 2 büyük harf olmayan | 0 |

## Kolonlar

### customers

| Kolon | Boş | Farklı | Çıkarılan tip | En küçük | En büyük | En uzun | Baş/son boşluk |
|---|---:|---:|---|---|---|---:|---:|
| `customer_id` | 0 | 99,441 | text (32 hane küçük harf hex) | 00012a2ce6f8dcda20d059ce98491703 | ffffe8b65bbe3087b653a978c870db99 | 32 | 0 |
| `customer_unique_id` | 0 | 96,096 | text (32 hane küçük harf hex) | 0000366f3b9a7992bf8c76cfdf3221e2 | ffffd2657e2aad2907e67c3e9daecbeb | 32 | 0 |
| `customer_zip_code_prefix` | 0 | 14,994 | text (yalnız rakam; baştaki sıfırlar anlamlı) | 01003 | 99990 | 5 | 0 |
| `customer_city` | 0 | 4,119 | text | abadia dos dourados | zortea | 32 | 0 |
| `customer_state` | 0 | 27 | text | AC | TO | 2 | 0 |

### geolocation

| Kolon | Boş | Farklı | Çıkarılan tip | En küçük | En büyük | En uzun | Baş/son boşluk |
|---|---:|---:|---|---|---|---:|---:|
| `geolocation_zip_code_prefix` | 0 | 19,015 | text (yalnız rakam; baştaki sıfırlar anlamlı) | 01001 | 99990 | 5 | 0 |
| `geolocation_lat` | 0 | 717,372 | decimal (tam kısım ≤2 hane, ondalık ≤20) | -36.6053744107061 | 45.06593318269697 | 23 | 0 |
| `geolocation_lng` | 0 | 717,615 | decimal (tam kısım ≤3 hane, ondalık ≤16) | -101.46676644931476 | 121.10539381057764 | 19 | 0 |
| `geolocation_city` | 0 | 8,011 | text | * cidade | óleo | 38 | 1 |
| `geolocation_state` | 0 | 27 | text | AC | TO | 2 | 0 |

### orders

| Kolon | Boş | Farklı | Çıkarılan tip | En küçük | En büyük | En uzun | Baş/son boşluk |
|---|---:|---:|---|---|---|---:|---:|
| `order_id` | 0 | 99,441 | text (32 hane küçük harf hex) | 00010242fe8c5a6d1ba2dd792cb16214 | fffe41c64501cc87c801fd61db3f6244 | 32 | 0 |
| `customer_id` | 0 | 99,441 | text (32 hane küçük harf hex) | 00012a2ce6f8dcda20d059ce98491703 | ffffe8b65bbe3087b653a978c870db99 | 32 | 0 |
| `order_status` | 0 | 8 | text | approved | unavailable | 11 | 0 |
| `order_purchase_timestamp` | 0 | 98,875 | timestamp (YYYY-MM-DD HH:MM:SS, saat dilimi yok) | 2016-09-04 21:15:19 | 2018-10-17 17:30:18 | 19 | 0 |
| `order_approved_at` | 160 | 90,733 | timestamp (YYYY-MM-DD HH:MM:SS, saat dilimi yok) | 2016-09-15 12:16:38 | 2018-09-03 17:40:06 | 19 | 0 |
| `order_delivered_carrier_date` | 1,783 | 81,018 | timestamp (YYYY-MM-DD HH:MM:SS, saat dilimi yok) | 2016-10-08 10:34:01 | 2018-09-11 19:48:28 | 19 | 0 |
| `order_delivered_customer_date` | 2,965 | 95,664 | timestamp (YYYY-MM-DD HH:MM:SS, saat dilimi yok) | 2016-10-11 13:46:32 | 2018-10-17 13:22:46 | 19 | 0 |
| `order_estimated_delivery_date` | 0 | 459 | timestamp (YYYY-MM-DD HH:MM:SS, saat dilimi yok) | 2016-09-30 00:00:00 | 2018-11-12 00:00:00 | 19 | 0 |

### order_items

| Kolon | Boş | Farklı | Çıkarılan tip | En küçük | En büyük | En uzun | Baş/son boşluk |
|---|---:|---:|---|---|---|---:|---:|
| `order_id` | 0 | 98,666 | text (32 hane küçük harf hex) | 00010242fe8c5a6d1ba2dd792cb16214 | fffe41c64501cc87c801fd61db3f6244 | 32 | 0 |
| `order_item_id` | 0 | 21 | integer | 1 | 21 | 2 | 0 |
| `product_id` | 0 | 32,951 | text (32 hane küçük harf hex) | 00066f42aeeb9f3007548bb9d3f33c38 | fffe9eeff12fcbd74a2f2b007dde0c58 | 32 | 0 |
| `seller_id` | 0 | 3,095 | text (32 hane küçük harf hex) | 0015a82c2db000af6aaaf3ae2ecb0532 | ffff564a4f9085cd26170f4732393726 | 32 | 0 |
| `shipping_limit_date` | 0 | 93,318 | timestamp (YYYY-MM-DD HH:MM:SS, saat dilimi yok) | 2016-09-19 00:15:34 | 2020-04-09 22:35:08 | 19 | 0 |
| `price` | 0 | 5,968 | decimal (tam kısım ≤4 hane, ondalık ≤2) | 0.85 | 6735.00 | 7 | 0 |
| `freight_value` | 0 | 6,999 | decimal (tam kısım ≤3 hane, ondalık ≤2) | 0.00 | 409.68 | 6 | 0 |

### order_payments

| Kolon | Boş | Farklı | Çıkarılan tip | En küçük | En büyük | En uzun | Baş/son boşluk |
|---|---:|---:|---|---|---|---:|---:|
| `order_id` | 0 | 99,440 | text (32 hane küçük harf hex) | 00010242fe8c5a6d1ba2dd792cb16214 | fffe41c64501cc87c801fd61db3f6244 | 32 | 0 |
| `payment_sequential` | 0 | 29 | integer | 1 | 29 | 2 | 0 |
| `payment_type` | 0 | 5 | text | boleto | voucher | 11 | 0 |
| `payment_installments` | 0 | 24 | integer | 0 | 24 | 2 | 0 |
| `payment_value` | 0 | 29,077 | decimal (tam kısım ≤5 hane, ondalık ≤2) | 0.00 | 13664.08 | 8 | 0 |

### order_reviews

| Kolon | Boş | Farklı | Çıkarılan tip | En küçük | En büyük | En uzun | Baş/son boşluk |
|---|---:|---:|---|---|---|---:|---:|
| `review_id` | 0 | 98,410 | text (32 hane küçük harf hex) | 0001239bc1de2e33cb583967c2ca4c67 | fffefe7a48d22f7b32046421062219d1 | 32 | 0 |
| `order_id` | 0 | 98,673 | text (32 hane küçük harf hex) | 00010242fe8c5a6d1ba2dd792cb16214 | fffe41c64501cc87c801fd61db3f6244 | 32 | 0 |
| `review_score` | 0 | 5 | integer | 1 | 5 | 1 | 0 |
| `review_comment_title` | 87,656 | 4,527 | text |   | 🔟  | 26 | 1,998 |
| `review_comment_message` | 58,247 | 36,159 | text |   | 😡😡😡😡😡👎👎👎👎👎 Empresa sem compromisso com… | 208 | 9,451 |
| `review_creation_date` | 0 | 636 | timestamp (YYYY-MM-DD HH:MM:SS, saat dilimi yok) | 2016-10-02 00:00:00 | 2018-08-31 00:00:00 | 19 | 0 |
| `review_answer_timestamp` | 0 | 98,248 | timestamp (YYYY-MM-DD HH:MM:SS, saat dilimi yok) | 2016-10-07 18:32:28 | 2018-10-29 12:27:35 | 19 | 0 |

### products

| Kolon | Boş | Farklı | Çıkarılan tip | En küçük | En büyük | En uzun | Baş/son boşluk |
|---|---:|---:|---|---|---|---:|---:|
| `product_id` | 0 | 32,951 | text (32 hane küçük harf hex) | 00066f42aeeb9f3007548bb9d3f33c38 | fffe9eeff12fcbd74a2f2b007dde0c58 | 32 | 0 |
| `product_category_name` | 610 | 73 | text | agro_industria_e_comercio | utilidades_domesticas | 46 | 0 |
| `product_name_lenght` | 610 | 66 | integer | 5 | 76 | 2 | 0 |
| `product_description_lenght` | 610 | 2,960 | integer | 4 | 3992 | 4 | 0 |
| `product_photos_qty` | 610 | 19 | integer | 1 | 20 | 2 | 0 |
| `product_weight_g` | 2 | 2,204 | integer | 0 | 40425 | 5 | 0 |
| `product_length_cm` | 2 | 99 | integer | 7 | 105 | 3 | 0 |
| `product_height_cm` | 2 | 102 | integer | 2 | 105 | 3 | 0 |
| `product_width_cm` | 2 | 95 | integer | 6 | 118 | 3 | 0 |

### sellers

| Kolon | Boş | Farklı | Çıkarılan tip | En küçük | En büyük | En uzun | Baş/son boşluk |
|---|---:|---:|---|---|---|---:|---:|
| `seller_id` | 0 | 3,095 | text (32 hane küçük harf hex) | 0015a82c2db000af6aaaf3ae2ecb0532 | ffff564a4f9085cd26170f4732393726 | 32 | 0 |
| `seller_zip_code_prefix` | 0 | 2,246 | text (yalnız rakam; baştaki sıfırlar anlamlı) | 01001 | 99730 | 5 | 0 |
| `seller_city` | 0 | 611 | text | 04482255 | xaxim | 40 | 0 |
| `seller_state` | 0 | 23 | text | AC | SP | 2 | 0 |

### category_translation

| Kolon | Boş | Farklı | Çıkarılan tip | En küçük | En büyük | En uzun | Baş/son boşluk |
|---|---:|---:|---|---|---|---:|---:|
| `product_category_name` | 0 | 71 | text | agro_industria_e_comercio | utilidades_domesticas | 46 | 0 |
| `product_category_name_english` | 0 | 71 | text | agro_industry_and_commerce | watches_gifts | 39 | 0 |

