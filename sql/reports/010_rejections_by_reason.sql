-- Bu çalışmada reddedilen veya tekrar olarak ayıklanan kaynak satırları, tablo ve nedene göre.
SELECT source_table, disposition, reason, count(*) AS row_count
FROM meta.etl_rejected_rows, unnest(reasons) AS reason
WHERE run_id = meta.current_run_id()
GROUP BY source_table, disposition, reason
ORDER BY source_table, disposition, row_count DESC, reason;
