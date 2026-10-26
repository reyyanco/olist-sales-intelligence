-- Raporlama rutinleri.
--
--   reporting.sp_load_monthly_summary(year int)  -- prosedür, işlem kontrolü YOK
--   reporting.refresh_report_objects()          -- fonksiyon, işlem kontrolü YOK; ETL işlemi içinde de çağrılır
--   reporting.sp_refresh_reports()              -- prosedür, işlem kontrolü VAR (COMMIT); durum kaydı tutar
--
-- PostgreSQL 16 kuralları (https://www.postgresql.org/docs/16/plpgsql-transactions.html):
-- - COMMIT/ROLLBACK yalnızca üst düzeyden (veya araya başka komut girmeden iç içe) CALL/DO ile
--   çağrılan prosedürlerde yapılabilir. Bu yüzden sp_refresh_reports istemciden autocommit modunda
--   "CALL reporting.sp_refresh_reports();" olarak çağrılmalıdır; açık bir BEGIN bloğu içinde
--   çağrılırsa ilk COMMIT "invalid transaction termination" hatası verir (testle doğrulandı).
-- - "A transaction cannot be ended inside a block with exception handlers": COMMIT'ler EXCEPTION
--   bloğunun DIŞINDADIR.
-- REFRESH MATERIALIZED VIEW CONCURRENTLY (https://www.postgresql.org/docs/16/sql-refreshmaterializedview.html):
-- - MV zaten doldurulmuş olmalı ve yalnızca kolon adlarından oluşan, WHERE içermeyen bir UNIQUE index
--   bulunmalı. Bu iki koşul katalogdan kontrol edilir; sağlanmıyorsa normal (kilitleyen) REFRESH yapılır
--   ve kullanılan yöntem sonuç ayrıntısına yazılır.

-- Aylık özet tablosu (yıl bazında yüklenir). İçerik reporting.v_monthly_sales_growth ile aynı tanımdır.
CREATE TABLE reporting.monthly_summary (
    month_start          date PRIMARY KEY,
    year                 integer NOT NULL,
    month                integer NOT NULL CHECK (month BETWEEN 1 AND 12),
    order_count          bigint NOT NULL CHECK (order_count >= 0),
    customer_count       bigint NOT NULL CHECK (customer_count >= 0),
    item_count           bigint NOT NULL CHECK (item_count >= 0),
    product_sales        numeric(14,2) NOT NULL,
    freight_amount       numeric(14,2) NOT NULL,
    payment_amount       numeric(14,2) NOT NULL,
    avg_basket_value     numeric(14,2),
    prev_product_sales   numeric(14,2),
    product_sales_change numeric(14,2),
    growth_rate          numeric(10,4),
    growth_status        text NOT NULL CHECK (growth_status IN ('no_previous_month', 'previous_month_zero', 'computed')),
    loaded_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT monthly_summary_year_matches CHECK (year = EXTRACT(YEAR FROM month_start)),
    CONSTRAINT monthly_summary_month_start CHECK (month_start = date_trunc('month', month_start)::date)
);
COMMENT ON TABLE reporting.monthly_summary IS 'Aylık satış özeti; reporting.sp_load_monthly_summary(year) ile yıl bazında yeniden yüklenir';

-- Rapor yenileme çalışma kaydı.
CREATE TABLE meta.report_refresh_runs (
    refresh_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at    timestamptz,
    status         text NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    details        jsonb,
    error_message  text,
    CONSTRAINT report_refresh_finished_when_done CHECK ((status = 'running') = (finished_at IS NULL)),
    CONSTRAINT report_refresh_failure_has_error CHECK (status <> 'failed' OR error_message IS NOT NULL)
);
COMMENT ON TABLE meta.report_refresh_runs IS 'reporting.sp_refresh_reports() çalışmaları: durum, yenilenen nesneler, hata';

-- Bir yılın aylık özetini yeniden yükler. Tekrar çağrılması çoğaltma yapmaz: önce o yılın satırları
-- silinir, sonra aynı işlemde yeniden eklenir (PK: month_start). Aynı anda iki çağrı advisory lock ile sıralanır.
-- Büyüme hesabı tüm ay serisi üzerinden yapıldığı için Ocak ayı önceki yılın Aralık ayına göre hesaplanır.
CREATE PROCEDURE reporting.sp_load_monthly_summary(year integer)
LANGUAGE plpgsql AS $$
#variable_conflict use_column
DECLARE
    v_year integer := sp_load_monthly_summary.year;
BEGIN
    IF v_year IS NULL THEN
        RAISE EXCEPTION 'sp_load_monthly_summary: year zorunludur';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM dw.dim_date d WHERE d.year = v_year) THEN
        RAISE EXCEPTION 'sp_load_monthly_summary: % yılı tarih boyutunda (dw.dim_date) yok', v_year;
    END IF;

    PERFORM pg_advisory_xact_lock(4820018, v_year);

    DELETE FROM reporting.monthly_summary m WHERE m.year = v_year;

    INSERT INTO reporting.monthly_summary (
        month_start, year, month, order_count, customer_count, item_count, product_sales,
        freight_amount, payment_amount, avg_basket_value, prev_product_sales,
        product_sales_change, growth_rate, growth_status
    )
    SELECT g.month_start, g.year, g.month, g.order_count, g.customer_count, g.item_count, g.product_sales,
           g.freight_amount, g.payment_amount, g.avg_basket_value, g.prev_product_sales,
           g.product_sales_change, g.growth_rate, g.growth_status
    FROM reporting.v_monthly_sales_growth g
    WHERE g.year = v_year;
END
$$;

-- Tüm rapor nesnelerini yeniler ve ne yaptığını jsonb olarak döndürür. İşlem kontrolü içermez;
-- çağıranın işleminde çalışır (ETL bunu tek yükleme işleminin sonunda çağırır).
CREATE FUNCTION reporting.refresh_report_objects()
RETURNS jsonb
LANGUAGE plpgsql AS $$
DECLARE
    mv          record;
    v_mode      text;
    v_details   jsonb := '[]'::jsonb;
    v_year      integer;
    v_years     integer[] := '{}';
BEGIN
    FOR mv IN
        SELECT c.oid, n.nspname, c.relname, m.ispopulated,
               EXISTS (
                   SELECT 1 FROM pg_index i
                   WHERE i.indrelid = c.oid AND i.indisunique AND i.indisvalid
                     AND i.indpred IS NULL AND i.indexprs IS NULL
               ) AS has_unique_index
        FROM pg_matviews m
        JOIN pg_namespace n ON n.nspname = m.schemaname
        JOIN pg_class c ON c.relnamespace = n.oid AND c.relname = m.matviewname
        WHERE m.schemaname = 'reporting'
        ORDER BY c.relname
    LOOP
        IF mv.ispopulated AND mv.has_unique_index THEN
            EXECUTE format('REFRESH MATERIALIZED VIEW CONCURRENTLY %I.%I', mv.nspname, mv.relname);
            v_mode := 'concurrently';
        ELSE
            EXECUTE format('REFRESH MATERIALIZED VIEW %I.%I', mv.nspname, mv.relname);
            v_mode := CASE WHEN NOT mv.ispopulated THEN 'initial_population' ELSE 'blocking_no_unique_index' END;
        END IF;
        v_details := v_details || jsonb_build_object('object', mv.nspname || '.' || mv.relname, 'mode', v_mode);
    END LOOP;

    -- Tarih boyutunda artık olmayan yılların özetleri kaldırılır, kalan her yıl yeniden yüklenir.
    DELETE FROM reporting.monthly_summary m
    WHERE NOT EXISTS (SELECT 1 FROM dw.dim_date d WHERE d.year = m.year);
    FOR v_year IN SELECT DISTINCT d.year FROM dw.dim_date d ORDER BY d.year LOOP
        CALL reporting.sp_load_monthly_summary(v_year);
        v_years := v_years || v_year;
    END LOOP;
    v_details := v_details || jsonb_build_object('object', 'reporting.monthly_summary', 'years', to_jsonb(v_years));

    RETURN v_details;
END
$$;

-- Rapor nesnelerini yeniler ve çalışma durumunu kalıcı olarak kaydeder.
-- 1) 'running' kaydı yazılır ve COMMIT edilir.
-- 2) Yenileme EXCEPTION bloğu içinde yapılır; hata olursa bloğun yaptığı her şey (MV ve özet
--    değişiklikleri) geri alınır, handler 'failed' ve hata nedenini yazar. Blok içinde COMMIT YOK.
-- 3) Bloğun dışında COMMIT: sonuç kaydı kalıcı olur.
-- 4) Hata olduysa aynı SQLSTATE ile yeniden yükseltilir; çağıran başarısızlığı görür, kayıt kalır.
CREATE PROCEDURE reporting.sp_refresh_reports()
LANGUAGE plpgsql AS $$
DECLARE
    v_id      bigint;
    v_details jsonb;
    v_error   text;
    v_state   text;
BEGIN
    INSERT INTO meta.report_refresh_runs (status) VALUES ('running') RETURNING refresh_id INTO v_id;
    COMMIT;

    BEGIN
        v_details := reporting.refresh_report_objects();
        UPDATE meta.report_refresh_runs
        SET status = 'succeeded', finished_at = clock_timestamp(), details = v_details
        WHERE refresh_id = v_id;
    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS v_error = MESSAGE_TEXT, v_state = RETURNED_SQLSTATE;
        UPDATE meta.report_refresh_runs
        SET status = 'failed', finished_at = clock_timestamp(), error_message = v_state || ': ' || v_error
        WHERE refresh_id = v_id;
    END;

    COMMIT;

    IF v_error IS NOT NULL THEN
        RAISE EXCEPTION 'Rapor yenileme başarısız (refresh_id=%): %', v_id, v_error USING ERRCODE = v_state;
    END IF;
END
$$;
