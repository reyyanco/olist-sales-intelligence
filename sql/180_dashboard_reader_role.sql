-- Dashboard için en az yetkili okuma rolü.
-- olist_reporting_reader (NOLOGIN): yalnızca reporting şemasındaki okuma nesneleri ve dashboard fonksiyonları.
-- Giriş yapan kullanıcı (DASHBOARD_DB_USER) bu dosyada OLUŞTURULMAZ: parola koda yazılmaz;
-- "python -m etl setup-dashboard-role" .env'deki değerlerle oluşturur ve bu role üye yapar.
-- Rol küme (cluster) düzeyindedir; yetkiler her veritabanında bu migration ile verilir.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'olist_reporting_reader') THEN
        CREATE ROLE olist_reporting_reader NOLOGIN;
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO olist_reporting_reader', current_database());
END
$$;

GRANT USAGE ON SCHEMA reporting TO olist_reporting_reader;

-- Varsayılan olarak PUBLIC'e verilen EXECUTE yetkisi reporting rutinlerinden kaldırılır;
-- dashboard rolü örneğin sp_refresh_reports veya sp_load_monthly_summary çağıramaz.
REVOKE EXECUTE ON ALL ROUTINES IN SCHEMA reporting FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA reporting REVOKE EXECUTE ON ROUTINES FROM PUBLIC;

GRANT SELECT ON
    reporting.v_dashboard_items,
    reporting.v_dashboard_orders,
    reporting.v_data_coverage,
    reporting.v_data_freshness,
    reporting.v_dashboard_categories,
    reporting.v_dashboard_states,
    reporting.v_orders,
    reporting.v_sales_kpis,
    reporting.v_rfm_observation,
    reporting.v_repeat_purchase,
    reporting.mv_monthly_sales,
    reporting.mv_category_sales
TO olist_reporting_reader;

GRANT EXECUTE ON FUNCTION
    reporting.fn_overview_kpis(date, date, text[], text[]),
    reporting.fn_monthly_sales(date, date, text[], text[]),
    reporting.fn_category_sales(date, date, text[]),
    reporting.fn_delivery_by_region(date, date, text[]),
    reporting.fn_delivery_monthly(date, date, text[]),
    reporting.fn_repeat_purchase(date, date),
    reporting.fn_rfm_segments(date),
    reporting.fn_customer_rfm(date)
TO olist_reporting_reader;
