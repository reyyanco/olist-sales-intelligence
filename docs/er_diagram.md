# ER Diyagramı

Yıldız şema (dw) ve kaynak (staging) ilişkileri. Çokluklar `docs/data_profile.md` ölçümlerine dayanır.

## dw katmanı

```mermaid
erDiagram
    dim_customer ||--|| fact_orders : "customer_id (1 sipariş = 1 customer_id)"
    dim_date ||--o{ fact_orders : "purchase_date_key"
    dim_date |o--o{ fact_orders : "delivered_customer_date_key (boş olabilir)"
    dim_date ||--o{ fact_orders : "estimated_delivery_date_key"
    fact_orders ||--o{ fact_sales : "order_id (+customer_id, purchase_date_key)"
    fact_orders ||--o{ fact_payments : "order_id"
    dim_product ||--o{ fact_sales : "product_id"
    dim_seller ||--o{ fact_sales : "seller_id"
    dim_date ||--o{ fact_sales : "purchase_date_key"

    dim_customer {
        text customer_id PK
        text customer_unique_id "kişi; RFM ve tekrar alım"
        text zip_code_prefix "5 hane, metin"
        text city
        text state
    }
    dim_product {
        text product_id PK
        text category_name "boş olabilir"
        text category_name_english "yalnız kaynak çeviri"
        text category_label "çeviri / Portekizce / uncategorized"
        text category_translation_status
        int weight_g
    }
    dim_seller {
        text seller_id PK
        text zip_code_prefix
        text city
        text state
    }
    dim_date {
        int date_key PK "YYYYMMDD"
        date full_date UK
        smallint year
        smallint month
        boolean is_weekend
    }
    fact_orders {
        text order_id PK
        text customer_id FK "UNIQUE"
        text order_status
        timestamp purchase_ts
        timestamp delivered_customer_ts "boş olabilir"
        date estimated_delivery_date
        int item_count
        numeric product_value "12,2"
        numeric freight_value "12,2"
        int payment_count
        numeric payment_value "12,2"
        int review_count
        numeric delivery_days "üretilmiş"
        boolean is_late "üretilmiş"
    }
    fact_sales {
        text order_id PK, FK
        smallint order_item_id PK
        text product_id FK
        text seller_id FK
        text customer_id FK
        int purchase_date_key FK
        numeric price "12,2"
        numeric freight_value "12,2"
    }
    fact_payments {
        text order_id PK, FK
        smallint payment_sequential PK
        text payment_type
        smallint payment_installments
        numeric payment_value "12,2"
    }
```

## Kaynak (staging) ilişkileri ve ölçülen çokluklar

```mermaid
erDiagram
    customers ||--|| orders : "customer_id (1:1)"
    orders ||--o{ order_items : "order_id (0..21 kalem; 775 sipariş kalemsiz)"
    orders ||--o{ order_payments : "order_id (0..29 ödeme; 1 sipariş ödemesiz)"
    orders ||--o{ order_reviews : "order_id (0..3 yorum; 768 sipariş yorumsuz)"
    products ||--o{ order_items : "product_id"
    sellers ||--o{ order_items : "seller_id"
    category_translation |o--o{ products : "product_category_name (2 kategori çevirisiz, 610 ürün kategorisiz)"
    geolocation }o--o{ customers : "zip prefix (benzersiz değil; dw'ye alınmadı)"
```

Notlar:

- `customer_unique_id` bir kişiyi temsil eder. 2.997 kişinin birden fazla `customer_id` değeri vardır.
- `order_reviews` anahtarı `(review_id, order_id)` çiftidir; `review_id` tek başına benzersiz değildir.
- `geolocation` tablosu posta kodu öneki başına birden çok satır içerir, bu yüzden boyut olarak modellenmedi ve yalnızca staging'de tutuluyor.
- `meta` şeması (çalışma kaydı, ret kayıtları) bu diyagramda yoktur; ayrıntılar `docs/data_dictionary.md` dosyasında.
