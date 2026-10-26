-- Boyut tabloları. Kısıtlar docs/data_profile.md içindeki ölçümlere dayanır
-- (ör. tüm kimlikler 32 haneli küçük harf hex, posta kodu önekleri 5 hane).

CREATE TABLE dw.dim_date (
    date_key        integer  PRIMARY KEY,
    full_date       date     NOT NULL UNIQUE,
    year            smallint NOT NULL,
    quarter         smallint NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    month           smallint NOT NULL CHECK (month BETWEEN 1 AND 12),
    month_start     date     NOT NULL,
    day_of_month    smallint NOT NULL CHECK (day_of_month BETWEEN 1 AND 31),
    iso_year        smallint NOT NULL,
    iso_week        smallint NOT NULL CHECK (iso_week BETWEEN 1 AND 53),
    iso_day_of_week smallint NOT NULL CHECK (iso_day_of_week BETWEEN 1 AND 7),
    is_weekend      boolean  NOT NULL,
    CONSTRAINT dim_date_key_matches_date CHECK (
        date_key = EXTRACT(YEAR FROM full_date)::int * 10000
                 + EXTRACT(MONTH FROM full_date)::int * 100
                 + EXTRACT(DAY FROM full_date)::int
    ),
    CONSTRAINT dim_date_month_start CHECK (month_start = date_trunc('month', full_date)::date)
);

-- customer_id siparişe özgüdür (profil: orders.customer_id benzersiz, 1 sipariş = 1 customer_id).
-- Gerçek kişi customer_unique_id ile temsil edilir; RFM ve tekrar satın alma bu kolonla hesaplanır.
CREATE TABLE dw.dim_customer (
    customer_id        text PRIMARY KEY CHECK (customer_id ~ '^[0-9a-f]{32}$'),
    customer_unique_id text NOT NULL CHECK (customer_unique_id ~ '^[0-9a-f]{32}$'),
    zip_code_prefix    text NOT NULL CHECK (zip_code_prefix ~ '^[0-9]{5}$'),
    city               text NOT NULL,
    state              text NOT NULL CHECK (state ~ '^[A-Z]{2}$')
);
CREATE INDEX dim_customer_unique_id_idx ON dw.dim_customer (customer_unique_id);

-- Kategori adı 610 üründe boş; 2 kategorinin İngilizce çevirisi kaynakta yok (NULL bırakılır).
-- Boyut alanları profilde en az 2 cm; ağırlık 0 değerini alabiliyor.
CREATE TABLE dw.dim_product (
    product_id            text PRIMARY KEY CHECK (product_id ~ '^[0-9a-f]{32}$'),
    category_name         text,
    category_name_english text,
    name_length           integer CHECK (name_length > 0),
    description_length    integer CHECK (description_length > 0),
    photos_qty            integer CHECK (photos_qty > 0),
    weight_g              integer CHECK (weight_g >= 0),
    length_cm             integer CHECK (length_cm > 0),
    height_cm             integer CHECK (height_cm > 0),
    width_cm              integer CHECK (width_cm > 0),
    CONSTRAINT dim_product_english_requires_category CHECK (category_name_english IS NULL OR category_name IS NOT NULL)
);

CREATE TABLE dw.dim_seller (
    seller_id       text PRIMARY KEY CHECK (seller_id ~ '^[0-9a-f]{32}$'),
    zip_code_prefix text NOT NULL CHECK (zip_code_prefix ~ '^[0-9]{5}$'),
    city            text NOT NULL,
    state           text NOT NULL CHECK (state ~ '^[A-Z]{2}$')
);

COMMENT ON TABLE dw.dim_date IS 'Takvim boyutu; kapsam yüklemede siparişlerdeki en erken ve en geç tarihten üretilir';
COMMENT ON TABLE dw.dim_customer IS 'Sipariş müşterisi (customer_id); kişi düzeyi için customer_unique_id';
COMMENT ON TABLE dw.dim_product IS 'Ürün boyutu; kategori çevirisi product_category_name_translation.csv dosyasından';
COMMENT ON TABLE dw.dim_seller IS 'Satıcı boyutu';
