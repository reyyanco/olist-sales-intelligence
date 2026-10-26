-- Yedek / geri yükleme karşılaştırması için veritabanı özeti (scripts/verify-restore.ps1).
-- Kaynak ve geri yüklenen veritabanında aynı sorgu çalışır; tek satır JSON döndürür. Yalnızca okur.
-- Bölümler:
--   objects    : şema başına nesne sayıları (tablo, view, MV, indeks, rutin, kısıt)
--   business   : iş verisi (staging, dw, reporting): satır sayıları, içerik MD5, finansal toplamlar
--   logs       : çalışma kayıtları (meta): satır sayıları, içerik MD5, son çalışma, migration listesi
--   privileges : dashboard okuma rolünün (olist_reporting_reader) yetkileri
-- Bu dosya sql/ üst düzeyinde olmadığı için migration olarak uygulanmaz.
-- Not: ASCII dışı karakter içermez; psql'e dosya olarak verilir.

WITH rels AS (
    SELECT n.nspname AS schema_name, c.relname AS rel_name
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname IN ('staging', 'dw', 'reporting', 'meta')
      AND c.relkind IN ('r', 'p', 'm')
),
content AS (
    -- Satır sayısı ve tüm satırların sıralı metin özetinin MD5'i (tablo başına tek sorgu).
    SELECT r.schema_name,
           r.schema_name || '.' || r.rel_name AS rel,
           (xpath('/row/c/text()', x))[1]::text::bigint AS row_count,
           coalesce((xpath('/row/h/text()', x))[1]::text, 'empty') AS content_md5
    FROM rels r,
         LATERAL query_to_xml(format(
             'SELECT count(*) AS c, md5(string_agg(t::text, chr(10) ORDER BY t::text)) AS h FROM %I.%I t',
             r.schema_name, r.rel_name), false, true, '') AS x
),
objects AS (
    SELECT jsonb_object_agg(n.nspname, jsonb_build_object(
        'tables', (SELECT count(*) FROM pg_class c WHERE c.relnamespace = n.oid AND c.relkind IN ('r', 'p')),
        'views', (SELECT count(*) FROM pg_class c WHERE c.relnamespace = n.oid AND c.relkind = 'v'),
        'materialized_views', (SELECT count(*) FROM pg_class c WHERE c.relnamespace = n.oid AND c.relkind = 'm'),
        'indexes', (SELECT count(*) FROM pg_class c WHERE c.relnamespace = n.oid AND c.relkind = 'i'),
        'sequences', (SELECT count(*) FROM pg_class c WHERE c.relnamespace = n.oid AND c.relkind = 'S'),
        'functions', (SELECT count(*) FROM pg_proc p WHERE p.pronamespace = n.oid AND p.prokind = 'f'),
        'procedures', (SELECT count(*) FROM pg_proc p WHERE p.pronamespace = n.oid AND p.prokind = 'p'),
        'constraints', (SELECT count(*) FROM pg_constraint k WHERE k.connamespace = n.oid)
    )) AS j
    FROM pg_namespace n
    WHERE n.nspname IN ('staging', 'dw', 'reporting', 'meta')
),
reader AS (
    SELECT oid FROM pg_roles WHERE rolname = 'olist_reporting_reader'
)
SELECT jsonb_build_object(
    'database', current_database(),
    'server_version', current_setting('server_version'),
    'database_size_bytes', pg_database_size(current_database()),
    'objects', (SELECT j FROM objects),
    'business', jsonb_build_object(
        'row_counts', (SELECT jsonb_object_agg(rel, row_count) FROM content WHERE schema_name <> 'meta'),
        'content_md5', (SELECT jsonb_object_agg(rel, content_md5) FROM content WHERE schema_name <> 'meta'),
        'materialized_views_populated',
            (SELECT jsonb_object_agg(schemaname || '.' || matviewname, ispopulated) FROM pg_matviews
             WHERE schemaname = 'reporting'),
        'financials', jsonb_build_object(
            'v_sales_kpis', (SELECT to_jsonb(k) FROM reporting.v_sales_kpis k),
            'fact_sales_price_all_statuses', (SELECT sum(price) FROM dw.fact_sales),
            'fact_sales_freight_all_statuses', (SELECT sum(freight_value) FROM dw.fact_sales),
            'fact_payments_value_all_statuses', (SELECT sum(payment_value) FROM dw.fact_payments),
            'monthly_summary_product_sales', (SELECT sum(product_sales) FROM reporting.monthly_summary),
            'mv_category_sales_product_sales', (SELECT sum(product_sales) FROM reporting.mv_category_sales)
        )
    ),
    'logs', jsonb_build_object(
        'row_counts', (SELECT jsonb_object_agg(rel, row_count) FROM content WHERE schema_name = 'meta'),
        'content_md5', (SELECT jsonb_object_agg(rel, content_md5) FROM content WHERE schema_name = 'meta'),
        'current_run_id', meta.current_run_id(),
        'last_run', (SELECT to_jsonb(r) FROM (
            SELECT run_id, status, started_at FROM meta.etl_runs ORDER BY started_at DESC LIMIT 1) r),
        'etl_runs_by_status', (SELECT jsonb_object_agg(status, n) FROM (
            SELECT status, count(*) AS n FROM meta.etl_runs GROUP BY status) s),
        'schema_migrations', (SELECT jsonb_agg(filename ORDER BY filename) FROM meta.schema_migrations),
        'last_report_refresh_id', (SELECT max(refresh_id) FROM meta.report_refresh_runs)
    ),
    'privileges', jsonb_build_object(
        'reader_role_exists', EXISTS (SELECT 1 FROM reader),
        'reader_usage_reporting', has_schema_privilege('olist_reporting_reader', 'reporting', 'USAGE'),
        'reader_select_v_sales_kpis', has_table_privilege('olist_reporting_reader', 'reporting.v_sales_kpis', 'SELECT'),
        'reader_execute_fn_overview_kpis', has_function_privilege('olist_reporting_reader',
            'reporting.fn_overview_kpis(date, date, text[], text[])', 'EXECUTE'),
        'reader_usage_dw', has_schema_privilege('olist_reporting_reader', 'dw', 'USAGE'),
        'reader_execute_sp_refresh_reports', has_function_privilege('olist_reporting_reader',
            'reporting.sp_refresh_reports()', 'EXECUTE'),
        'reader_connect_grant_explicit', EXISTS (
            SELECT 1 FROM pg_database d, aclexplode(d.datacl) a
            WHERE d.datname = current_database() AND a.grantee = (SELECT oid FROM reader)
              AND a.privilege_type = 'CONNECT')
    )
)::text;
