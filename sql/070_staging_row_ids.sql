-- Her staging satırına kaynak kayıt sırası. Yükleme TRUNCATE ... RESTART IDENTITY ile
-- yapıldığından _row_id = dosyadaki veri kaydının sırası (başlık hariç, 1'den başlar).
-- Reddedilen kayıtlar bu numarayla raporlanır. Kaynak kolonlar değişmez.
ALTER TABLE staging.customers            ADD COLUMN _row_id bigint GENERATED ALWAYS AS IDENTITY;
ALTER TABLE staging.geolocation          ADD COLUMN _row_id bigint GENERATED ALWAYS AS IDENTITY;
ALTER TABLE staging.orders               ADD COLUMN _row_id bigint GENERATED ALWAYS AS IDENTITY;
ALTER TABLE staging.order_items          ADD COLUMN _row_id bigint GENERATED ALWAYS AS IDENTITY;
ALTER TABLE staging.order_payments       ADD COLUMN _row_id bigint GENERATED ALWAYS AS IDENTITY;
ALTER TABLE staging.order_reviews        ADD COLUMN _row_id bigint GENERATED ALWAYS AS IDENTITY;
ALTER TABLE staging.products             ADD COLUMN _row_id bigint GENERATED ALWAYS AS IDENTITY;
ALTER TABLE staging.sellers              ADD COLUMN _row_id bigint GENERATED ALWAYS AS IDENTITY;
ALTER TABLE staging.category_translation ADD COLUMN _row_id bigint GENERATED ALWAYS AS IDENTITY;
