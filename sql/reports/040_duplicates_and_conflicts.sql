-- Birebir aynı tekrar satırlar ile çelişkili doğal anahtarlar ayrı ayrı.
SELECT source_table,
       CASE WHEN disposition = 'duplicate_removed' THEN 'exact_duplicate' ELSE 'conflicting_key' END AS kind,
       count(*)                     AS row_count,
       count(DISTINCT natural_key)  AS distinct_keys
FROM meta.etl_rejected_rows
WHERE run_id = meta.current_run_id()
  AND (disposition = 'duplicate_removed' OR 'conflicting_key' = ANY (reasons))
GROUP BY source_table, kind
ORDER BY source_table, kind;
