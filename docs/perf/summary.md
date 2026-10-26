# Performans Ölçümleri — Özet

Bu dosya `python -m perf` tarafından `docs/perf/results/*.json` dosyalarından üretilir; elle düzenlenmez.
Süreler milisaniye (ms). medyan | min | max. Önbellek temizlenmedi (sıcak önbellek).

## Ortam

- Veri: GERÇEK Olist verisi (data/raw), olist_perf veritabanına yükleme hattıyla yüklendi
- Ölçüm zamanı (UTC): 2026-10-24T17:03:35+00:00
- PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2) on x86_64-pc-linux-gnu, compiled by gcc (Debian 12.2.0-14+deb12u1) 12.2.0, 64-bit
- Konteyner CPU: 16, bellek: 7786148 kB
- Veritabanı boyutu: 321674263 bayt
- Ayarlar: default_statistics_target=100, effective_cache_size=5242888kB, jit=on, maintenance_work_mem=65536kB, max_parallel_workers_per_gather=2, random_page_cost=4, shared_buffers=163848kB, work_mem=4096kB
- Satır sayıları: dw.dim_customer=99441, dw.dim_product=32951, dw.dim_seller=3095, dw.dim_date=800, dw.fact_orders=99441, dw.fact_sales=112650, dw.fact_payments=103886
- Yöntem: 2 ısınma çalışması (ölçüme katılmaz) + 7 ölçüm; istemcide execute+fetchall süresi (time.perf_counter). Önbellek temizlenmedi: tüm sorgu ölçümleri sıcak önbellek koşulundadır. EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ayrı çalıştırıldı. Yazma/yenileme/yükleme ölçümleri: 1 ısınma + 5 ölçüm. Sorgu başına statement_timeout=60000 ms; aşan ölçüm 'timed_out' kaydedilir ve planı yalnızca EXPLAIN (çalıştırmadan) ile alınır.

## Başlangıç durumu

Kaldırılan indeksler (yalnızca olist_perf):

- `CREATE INDEX dim_customer_unique_id_idx ON dw.dim_customer USING btree (customer_unique_id)`
- `CREATE INDEX fact_orders_purchase_date_idx ON dw.fact_orders USING btree (purchase_date_key)`
- `CREATE INDEX fact_orders_status_idx ON dw.fact_orders USING btree (order_status)`
- `CREATE INDEX fact_sales_product_idx ON dw.fact_sales USING btree (product_id)`
- `CREATE INDEX fact_sales_purchase_date_idx ON dw.fact_sales USING btree (purchase_date_key)`
- `CREATE INDEX fact_sales_seller_idx ON dw.fact_sales USING btree (seller_id)`

Korunan indeks sayısı (PK/UNIQUE): 13

## Parametreler

- `customer_unique_id` = `8d50f5eadf50201ccdcedfb9e2ac8455`
- `seller_id` = `6560211a19b47992c3666cc44a7e94c0`
- `as_of` = `2018-08-30`

## Başlangıç kataloğu (değişiklik yok)

| Sorgu | medyan | min | max | satır | Plan düğümleri |
|---|---:|---:|---:|---:|---|
| kpis | 303.373 | 297.584 | 325.384 | 1 | Aggregate, CTE Scan, Gather, Hash, Hash Join, Seq Scan |
| monthly_growth | 351.235 | 330.725 | 398.139 | 27 | Aggregate, Hash, Hash Join, Merge Join, Seq Scan, Sort, Subquery Scan, WindowAgg |
| monthly_mv | 0.371 | 0.362 | 0.572 | 23 | Seq Scan, Sort |
| delivery_rollup | 251.761 | 225.445 | 257.942 | 27 | Aggregate, Hash, Hash Join, Seq Scan, Sort |
| repeat_purchase | zaman aşımı (>60000, warmup) | - | - | - | Aggregate, Gather Merge, Hash, Hash Join, Index Scan, Nested Loop, Seq Scan, Sort, Subquery Scan, Unique |
| category_mv | 0.908 | 0.829 | 1.375 | 74 | Seq Scan, Sort |

## E1_customer_history — Bir kişinin (customer_unique_id) sipariş geçmişi (B-tree indeks)

| Durum | medyan | min | max | hızlanma | sonuç aynı | kullanılan indeks | Seq Scan | plan ANALYZE | uygulama ms (1 kez) | indeks bayt | yazma medyan ms |
|---|---:|---:|---:|---:|---|---|---|---|---:|---:|---:|
| baseline | 12.918 | 11.404 | 13.654 |  | - | fact_orders_customer_id_key | dim_customer | True |  |  | 51.383 |
| btree_customer_unique_id | 0.955 | 0.811 | 1.255 | 13.53 | True (ref: baseline) | fact_orders_customer_id_key, perf_dim_customer_unique_idx | - | True | 271.733 | 5742592 | 427.977 |

EXPLAIN dosyaları: `plans/E1_customer_history_baseline.json`, `plans/E1_customer_history_btree_customer_unique_id.json`

## E2_seller_date_range — En çok kalemi olan satıcının 2018-01..03 günlük satışları (tek kolon / birleşik / INCLUDE indeks)

| Durum | medyan | min | max | hızlanma | sonuç aynı | kullanılan indeks | Seq Scan | plan ANALYZE | uygulama ms (1 kez) | indeks bayt | yazma medyan ms |
|---|---:|---:|---:|---:|---|---|---|---|---:|---:|---:|
| baseline | 16.813 | 16.094 | 19.900 |  | - | - | fact_sales | True |  |  | 79.762 |
| btree_seller | 2.823 | 2.581 | 3.485 | 5.96 | True (ref: baseline) | perf_sales_seller_idx | - | True | 194.948 | 1007616 | 351.761 |
| composite_seller_date | 1.258 | 0.956 | 2.020 | 13.36 | True (ref: baseline) | perf_sales_seller_date_idx | - | True | 254.938 | 4644864 | 466.536 |
| composite_include_price | 0.824 | 0.579 | 1.089 | 20.4 | True (ref: baseline) | perf_sales_seller_date_incl_idx | - | True | 233.174 | 7659520 | 467.812 |

EXPLAIN dosyaları: `plans/E2_seller_date_range_baseline.json`, `plans/E2_seller_date_range_btree_seller.json`, `plans/E2_seller_date_range_composite_seller_date.json`, `plans/E2_seller_date_range_composite_include_price.json`

## E3_open_orders — Teslim edilmemiş son 50 sipariş (durum indeksi / tam indeks / partial index)

| Durum | medyan | min | max | hızlanma | sonuç aynı | kullanılan indeks | Seq Scan | plan ANALYZE | uygulama ms (1 kez) | indeks bayt | yazma medyan ms |
|---|---:|---:|---:|---:|---|---|---|---|---:|---:|---:|
| baseline | 15.281 | 14.790 | 19.162 |  | - | - | fact_orders | True |  |  | 84.611 |
| btree_status | 15.066 | 14.761 | 18.236 | 1.01 | True (ref: baseline) | - | fact_orders | True | 86.457 | 712704 | 200.761 |
| full_purchase_desc | 1.851 | 1.365 | 2.088 | 8.26 | True (ref: baseline) | perf_orders_purchase_full_idx | - | True | 104.97 | 6725632 | 274.017 |
| partial_open_orders | 0.524 | 0.430 | 0.592 | 29.16 | True (ref: baseline) | perf_orders_open_partial_idx | - | True | 36.318 | 221184 | 100.541 |

EXPLAIN dosyaları: `plans/E3_open_orders_baseline.json`, `plans/E3_open_orders_btree_status.json`, `plans/E3_open_orders_full_purchase_desc.json`, `plans/E3_open_orders_partial_open_orders.json`

## E4_repeat_purchase_rewrite — Tekrar satın alma oranı (reporting.v_repeat_purchase) (sorgu düzenleme)

| Durum | medyan | min | max | hızlanma | sonuç aynı | kullanılan indeks | Seq Scan | plan ANALYZE | uygulama ms (1 kez) | indeks bayt | yazma medyan ms |
|---|---:|---:|---:|---:|---|---|---|---|---:|---:|---:|
| baseline | zaman aşımı (>60000, warmup) | - | - |  | - | fact_orders_customer_id_key | dim_customer, fact_orders | False |  |  |  |
| btree_customer_unique_id | 1517.952 | 1455.413 | 1570.890 | ≥ 39.5 | referans | fact_orders_customer_id_key, perf_dim_customer_unique_idx | dim_customer, fact_orders | True | 269.794 | 5742592 |  |
| single_pass_aggregate | 405.891 | 389.916 | 447.033 | ≥ 147.8 | True (ref: btree_customer_unique_id) | - | dim_customer, fact_orders | True |  |  |  |

EXPLAIN dosyaları: `plans/E4_repeat_purchase_rewrite_baseline.json`, `plans/E4_repeat_purchase_rewrite_btree_customer_unique_id.json`, `plans/E4_repeat_purchase_rewrite_single_pass_aggregate.json`

## E5_category_sales_mv — Kategori satışları ve kümülatif pay (materialized view)

| Durum | medyan | min | max | hızlanma | sonuç aynı | kullanılan indeks | Seq Scan | plan ANALYZE | uygulama ms (1 kez) | indeks bayt | yazma medyan ms |
|---|---:|---:|---:|---:|---|---|---|---|---:|---:|---:|
| baseline | 568.796 | 538.207 | 644.802 |  | - | - | dim_customer, dim_product, fact_orders, fact_sales | True |  |  |  |
| read_materialized_view | 0.607 | 0.499 | 0.780 | 937.06 | True (ref: baseline) | - | mv_category_sales | True |  |  |  |

EXPLAIN dosyaları: `plans/E5_category_sales_mv_baseline.json`, `plans/E5_category_sales_mv_read_materialized_view.json`

## E6_rfm_work_mem — RFM: reporting.fn_customer_rfm(as_of) (oturum work_mem (planda diske taşma için))

| Durum | medyan | min | max | hızlanma | sonuç aynı | kullanılan indeks | Seq Scan | plan ANALYZE | uygulama ms (1 kez) | indeks bayt | yazma medyan ms |
|---|---:|---:|---:|---:|---|---|---|---|---:|---:|---:|
| baseline | 1571.508 | 1535.076 | 1780.144 |  | - | - | - | True |  |  |  |
| work_mem_64mb | 1627.023 | 1547.379 | 1674.393 | 0.97 | True (ref: baseline) | - | - | True | 0.376 |  |  |

EXPLAIN dosyaları: `plans/E6_rfm_work_mem_baseline.json`, `plans/E6_rfm_work_mem_work_mem_64mb.json`

## E5 ek — materialized view maliyetleri

| Ölçüm | medyan | min | max |
|---|---:|---:|---:|
| REFRESH (normal) | 563.615 | 548.377 | 606.509 |
| REFRESH CONCURRENTLY | 549.114 | 539.270 | 570.223 |

- Satır: 74; depolama: heap 8192 bayt, UNIQUE indeks 16384 bayt, toplam 40960 bayt
- Güncellik: view toplamı 13221498.11 → 13221499.11; yenilenmemiş MV toplamı 13221498.11 (değişikliği yansıtıyor mu: False)

## L1 — COPY ve pandas to_sql

- Kaynak: `olist_order_items_dataset.csv` (15438671 bayt)
- Hedef: perf.load_target (order_id text, order_item_id text, product_id text, seller_id text, shipping_limit_date text, price text, freight_value text), indeks yok; işlem: her çalışma: BEGIN; TRUNCATE; yükleme; COMMIT
- Sürümler: {'pandas': '3.1.0', 'sqlalchemy': '2.1.6'}; to_sql ortak: schema='perf', if_exists='append', index=False
- pandas.read_csv (dtype=str, keep_default_na=False, na_filter=False): 298.790 | 282.707 | 348.951 ms
- Tüm yöntemlerin sonucu aynı: True

| Yöntem | method | chunksize | medyan | min | max | satır |
|---|---|---:|---:|---:|---:|---:|
| copy_from_stdin | - | - | 1262.600 | 1035.928 | 1439.099 | 112650 |
| to_sql_default_chunk10000 | None | 10000 | 3715.595 | 3583.976 | 3764.930 | 112650 |
| to_sql_multi_chunk1000 | multi | 1000 | 15460.695 | 15171.799 | 16119.020 | 112650 |

## P1 — Partitioning (yalıtılmış, gerçek hacim)

Satır sayıları: perf.orders_plain=99441, perf.orders_part=99441, perf.orders_part_2016=329, perf.orders_part_2017=45101, perf.orders_part_2018=54011, perf.orders_part_default=0

| Sorgu | Tablo | medyan | min | max | taranan tablolar | sonuç aynı | hızlanma |
|---|---|---:|---:|---:|---|---|---:|
| one_month | plain | 12.361 | 11.343 | 16.368 | orders_plain | True |  |
| one_month | partitioned | 8.026 | 7.301 | 11.057 | orders_part_2018 | True | 1.54 |
| all_rows | plain | 29.803 | 28.163 | 32.324 | orders_plain | True |  |
| all_rows | partitioned | 36.808 | 32.564 | 39.442 | orders_part_2016, orders_part_2017, orders_part_2018, orders_part_default | True | 0.81 |

