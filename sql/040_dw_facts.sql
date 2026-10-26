-- Olgu tabloları. Para alanları NUMERIC(12,2): profilde en fazla 2 ondalık ve
-- en büyük değer 13664.08 (payment_value). Zamanlar saat dilimi olmadan saklanır
-- (kaynakta saat dilimi belirtilmemiş; dönüştürme yapılmaz).

-- Grain: bir satır = bir sipariş. Kalem, ödeme ve yorum ölçüleri yüklemede
-- sipariş başına önceden toplanır; kalem/ödeme/yorum satırları birleştirilerek çoğaltılmaz.
CREATE TABLE dw.fact_orders (
    order_id                    text PRIMARY KEY CHECK (order_id ~ '^[0-9a-f]{32}$'),
    customer_id                 text NOT NULL UNIQUE REFERENCES dw.dim_customer (customer_id),
    order_status                text NOT NULL CHECK (order_status IN (
                                    'created', 'approved', 'invoiced', 'processing',
                                    'shipped', 'delivered', 'canceled', 'unavailable')),
    purchase_ts                 timestamp NOT NULL,
    approved_ts                 timestamp,
    delivered_carrier_ts        timestamp,
    delivered_customer_ts       timestamp,
    -- Profil: tahmini teslim zamanı her satırda 00:00:00, bu yüzden tarih olarak saklanır.
    estimated_delivery_date     date NOT NULL,
    purchase_date_key           integer NOT NULL REFERENCES dw.dim_date (date_key),
    delivered_customer_date_key integer REFERENCES dw.dim_date (date_key),
    estimated_delivery_date_key integer NOT NULL REFERENCES dw.dim_date (date_key),
    item_count                  integer NOT NULL CHECK (item_count >= 0),
    product_value               numeric(12,2) NOT NULL CHECK (product_value >= 0),
    freight_value               numeric(12,2) NOT NULL CHECK (freight_value >= 0),
    payment_count               integer NOT NULL CHECK (payment_count >= 0),
    payment_value               numeric(12,2) NOT NULL CHECK (payment_value >= 0),
    review_count                integer NOT NULL CHECK (review_count >= 0),
    review_score_avg            numeric(3,2) CHECK (review_score_avg BETWEEN 1 AND 5),
    -- Teslim süresi (gün, ondalıklı) ve geç teslim bayrağı; teslim zamanı yoksa NULL.
    delivery_days               numeric(8,2) GENERATED ALWAYS AS (
                                    round(EXTRACT(EPOCH FROM (delivered_customer_ts - purchase_ts)) / 86400.0, 2)
                                ) STORED,
    is_late                     boolean GENERATED ALWAYS AS (
                                    delivered_customer_ts::date > estimated_delivery_date
                                ) STORED,
    -- Profil: approved < purchase ve delivered_customer < purchase durumları 0.
    -- delivered_carrier < purchase 166 siparişte var; bu yüzden onun için kısıt yok.
    CONSTRAINT fact_orders_approved_after_purchase CHECK (approved_ts IS NULL OR approved_ts >= purchase_ts),
    CONSTRAINT fact_orders_delivered_after_purchase CHECK (delivered_customer_ts IS NULL OR delivered_customer_ts >= purchase_ts),
    CONSTRAINT fact_orders_purchase_key_matches CHECK (
        purchase_date_key = EXTRACT(YEAR FROM purchase_ts)::int * 10000
                          + EXTRACT(MONTH FROM purchase_ts)::int * 100
                          + EXTRACT(DAY FROM purchase_ts)::int
    ),
    CONSTRAINT fact_orders_delivered_key_matches CHECK (
        (delivered_customer_ts IS NULL AND delivered_customer_date_key IS NULL)
        OR delivered_customer_date_key = EXTRACT(YEAR FROM delivered_customer_ts)::int * 10000
                                       + EXTRACT(MONTH FROM delivered_customer_ts)::int * 100
                                       + EXTRACT(DAY FROM delivered_customer_ts)::int
    ),
    CONSTRAINT fact_orders_estimated_key_matches CHECK (
        estimated_delivery_date_key = EXTRACT(YEAR FROM estimated_delivery_date)::int * 10000
                                    + EXTRACT(MONTH FROM estimated_delivery_date)::int * 100
                                    + EXTRACT(DAY FROM estimated_delivery_date)::int
    ),
    CONSTRAINT fact_orders_items_consistent CHECK (item_count > 0 OR (product_value = 0 AND freight_value = 0)),
    CONSTRAINT fact_orders_payments_consistent CHECK (payment_count > 0 OR payment_value = 0),
    CONSTRAINT fact_orders_reviews_consistent CHECK ((review_count = 0) = (review_score_avg IS NULL)),
    -- fact_sales'teki kopya anahtarların siparişle tutarlı kalması için.
    CONSTRAINT fact_orders_order_customer_date_uq UNIQUE (order_id, customer_id, purchase_date_key)
);
CREATE INDEX fact_orders_purchase_date_idx ON dw.fact_orders (purchase_date_key);
CREATE INDEX fact_orders_status_idx ON dw.fact_orders (order_status);

-- Grain: bir satır = bir sipariş kalemi (order_id + order_item_id).
-- Kaynakta quantity yok; her satır bir kalemdir (bkz. docs/metric_definitions.md).
CREATE TABLE dw.fact_sales (
    order_id          text     NOT NULL,
    order_item_id     smallint NOT NULL CHECK (order_item_id >= 1),
    product_id        text     NOT NULL REFERENCES dw.dim_product (product_id),
    seller_id         text     NOT NULL REFERENCES dw.dim_seller (seller_id),
    customer_id       text     NOT NULL,
    purchase_date_key integer  NOT NULL REFERENCES dw.dim_date (date_key),
    shipping_limit_ts timestamp NOT NULL,
    -- Profil: price en küçük 0.85 (sıfır yok); freight_value 383 kalemde 0.
    price             numeric(12,2) NOT NULL CHECK (price > 0),
    freight_value     numeric(12,2) NOT NULL CHECK (freight_value >= 0),
    PRIMARY KEY (order_id, order_item_id),
    CONSTRAINT fact_sales_order_fk FOREIGN KEY (order_id, customer_id, purchase_date_key)
        REFERENCES dw.fact_orders (order_id, customer_id, purchase_date_key)
);
CREATE INDEX fact_sales_product_idx ON dw.fact_sales (product_id);
CREATE INDEX fact_sales_seller_idx ON dw.fact_sales (seller_id);
CREATE INDEX fact_sales_purchase_date_idx ON dw.fact_sales (purchase_date_key);

-- Grain: bir satır = bir ödeme kaydı (order_id + payment_sequential).
-- Ödeme türü analizleri için; sipariş toplamı fact_orders.payment_value içinde.
CREATE TABLE dw.fact_payments (
    order_id             text     NOT NULL REFERENCES dw.fact_orders (order_id),
    payment_sequential   smallint NOT NULL CHECK (payment_sequential >= 1),
    payment_type         text     NOT NULL CHECK (payment_type IN (
                                      'credit_card', 'boleto', 'voucher', 'debit_card', 'not_defined')),
    -- Profil: 2 kayıtta taksit sayısı 0; 9 kayıtta ödeme tutarı 0.
    payment_installments smallint NOT NULL CHECK (payment_installments >= 0),
    payment_value        numeric(12,2) NOT NULL CHECK (payment_value >= 0),
    PRIMARY KEY (order_id, payment_sequential)
);

COMMENT ON TABLE dw.fact_orders IS 'Sipariş olgusu: bir satır = bir sipariş; kalem/ödeme/yorum ölçüleri önceden toplanmış';
COMMENT ON TABLE dw.fact_sales IS 'Satış olgusu: bir satır = bir sipariş kalemi (order_id, order_item_id)';
COMMENT ON TABLE dw.fact_payments IS 'Ödeme olgusu: bir satır = bir ödeme kaydı (order_id, payment_sequential)';
