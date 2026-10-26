-- ETL çalışma kaydı. etl_runs satırı veri işleminden AYRI bir işlemde yazılır;
-- yükleme geri alınsa (rollback) bile çalışmanın başarısız olduğu kaydı kalır.

CREATE TABLE meta.etl_runs (
    run_id           uuid PRIMARY KEY,
    started_at       timestamptz NOT NULL DEFAULT now(),
    finished_at      timestamptz,
    duration_seconds numeric(10,3),
    status           text NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    source_dir       text NOT NULL,
    error_message    text,
    CONSTRAINT etl_runs_finished_when_done CHECK ((status = 'running') = (finished_at IS NULL)),
    CONSTRAINT etl_runs_failure_has_error CHECK (status <> 'failed' OR error_message IS NOT NULL)
);
CREATE INDEX etl_runs_finished_idx ON meta.etl_runs (status, finished_at DESC);

-- Dosya başına sayımlar. staged = accepted + rejected + duplicate (dönüşüm tamamlandıysa).
CREATE TABLE meta.etl_run_files (
    run_id         uuid NOT NULL REFERENCES meta.etl_runs (run_id) ON DELETE CASCADE,
    source_table   text NOT NULL,
    file_name      text NOT NULL,
    file_sha256    char(64) NOT NULL,
    file_bytes     bigint NOT NULL CHECK (file_bytes >= 0),
    source_rows    bigint NOT NULL CHECK (source_rows >= 0),
    staged_rows    bigint CHECK (staged_rows >= 0),
    accepted_rows  bigint CHECK (accepted_rows >= 0),
    rejected_rows  bigint CHECK (rejected_rows >= 0),
    duplicate_rows bigint CHECK (duplicate_rows >= 0),
    load_seconds   numeric(10,3),
    PRIMARY KEY (run_id, source_table),
    CONSTRAINT etl_run_files_reconciled CHECK (
        accepted_rows IS NULL OR staged_rows = accepted_rows + rejected_rows + duplicate_rows
    )
);

-- Kalite kontrolleri. severity='error' başarısızsa yükleme geri alınır;
-- 'info' kontroller açıklama/rapor amaçlıdır (ör. ödeme farkları).
CREATE TABLE meta.etl_run_checks (
    run_id     uuid NOT NULL REFERENCES meta.etl_runs (run_id) ON DELETE CASCADE,
    check_name text NOT NULL,
    severity   text NOT NULL CHECK (severity IN ('error', 'info')),
    passed     boolean NOT NULL,
    row_count  integer NOT NULL CHECK (row_count >= 0),
    details    jsonb NOT NULL,
    PRIMARY KEY (run_id, check_name)
);

-- Reddedilen ve tekrar olarak ayıklanan kaynak satırları, nedenleriyle.
CREATE TABLE meta.etl_rejected_rows (
    run_id       uuid NOT NULL REFERENCES meta.etl_runs (run_id) ON DELETE CASCADE,
    source_table text NOT NULL,
    source_row   bigint NOT NULL,
    natural_key  text,
    disposition  text NOT NULL CHECK (disposition IN ('rejected', 'duplicate_removed')),
    reasons      text[] NOT NULL CHECK (cardinality(reasons) > 0),
    raw_record   jsonb NOT NULL,
    PRIMARY KEY (run_id, source_table, source_row)
);

-- İçinde bulunulan ETL işleminin run_id'si; işlem dışında son başarılı çalışma.
CREATE FUNCTION meta.current_run_id() RETURNS uuid
LANGUAGE sql STABLE AS $$
    SELECT COALESCE(
        NULLIF(current_setting('etl.run_id', true), '')::uuid,
        (SELECT run_id FROM meta.etl_runs WHERE status = 'succeeded' ORDER BY finished_at DESC LIMIT 1)
    )
$$;

-- Kaynak zaman biçimi YYYY-MM-DD HH:MM:SS ve takvimde geçerli mi (ör. 2017-02-30 geçersiz).
CREATE FUNCTION meta.is_valid_timestamp(value text) RETURNS boolean
LANGUAGE plpgsql STABLE AS $$
BEGIN
    IF value IS NULL OR value !~ '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$' THEN
        RETURN false;
    END IF;
    PERFORM value::timestamp;
    RETURN true;
EXCEPTION WHEN others THEN
    RETURN false;
END
$$;

COMMENT ON TABLE meta.etl_runs IS 'Her ETL çalışması: run_id, süre, durum, hata';
COMMENT ON TABLE meta.etl_run_files IS 'Çalışma başına kaynak dosya sayımları ve SHA-256';
COMMENT ON TABLE meta.etl_run_checks IS 'Çalışma başına kalite kontrol sonuçları';
COMMENT ON TABLE meta.etl_rejected_rows IS 'Reddedilen/tekrar ayıklanan kaynak satırları ve nedenleri';
