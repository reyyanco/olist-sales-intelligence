# Performans Ölçümleri — Özet

Bu dosya `python -m perf` tarafından `docs/perf/results/*.json` dosyalarından üretilir; elle düzenlenmez.
Süreler milisaniye (ms). medyan | min | max. Önbellek temizlenmedi (sıcak önbellek).

## Ortam

- Veri: GERÇEK Olist verisi (data/raw), olist_perf veritabanına yükleme hattıyla yüklendi
- Ölçüm zamanı (UTC): 2026-10-24T16:53:16+00:00
- PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2) on x86_64-pc-linux-gnu, compiled by gcc (Debian 12.2.0-14+deb12u1) 12.2.0, 64-bit
- Konteyner CPU: 16, bellek: 7786148 kB
- Veritabanı boyutu: 321608727 bayt
- Ayarlar: default_statistics_target=100, effective_cache_size=5242888kB, jit=on, maintenance_work_mem=65536kB, max_parallel_workers_per_gather=2, random_page_cost=4, shared_buffers=163848kB, work_mem=4096kB
- Satır sayıları: dw.dim_customer=99441, dw.dim_product=32951, dw.dim_seller=3095, dw.dim_date=800, dw.fact_orders=99441, dw.fact_sales=112650, dw.fact_payments=103886
- Yöntem: 2 ısınma çalışması (ölçüme katılmaz) + 7 ölçüm; istemcide execute+fetchall süresi (time.perf_counter). Önbellek temizlenmedi: tüm sorgu ölçümleri sıcak önbellek koşulundadır. EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ayrı çalıştırıldı. Yazma/yenileme/yükleme ölçümleri: 1 ısınma + 5 ölçüm. Sorgu başına statement_timeout=60000 ms; aşan ölçüm 'timed_out' kaydedilir ve planı yalnızca EXPLAIN (çalıştırmadan) ile alınır.

## Başlangıç durumu

Kaldırılan indeksler (yalnızca olist_perf):

- yok

Korunan indeks sayısı (PK/UNIQUE): 13

## Parametreler

- `customer_unique_id` = `8d50f5eadf50201ccdcedfb9e2ac8455`
- `seller_id` = `6560211a19b47992c3666cc44a7e94c0`
- `as_of` = `2018-08-30`

## Başlangıç kataloğu (değişiklik yok)

| Sorgu | medyan | min | max | satır | Plan düğümleri |
|---|---:|---:|---:|---:|---|
| kpis | 269.299 | 241.699 | 286.697 | 1 | Aggregate, CTE Scan, Gather, Hash, Hash Join, Seq Scan |
| monthly_growth | 350.385 | 338.404 | 383.539 | 27 | Aggregate, Hash, Hash Join, Merge Join, Seq Scan, Sort, Subquery Scan, WindowAgg |
| monthly_mv | 0.384 | 0.341 | 0.578 | 23 | Seq Scan, Sort |
| delivery_rollup | 240.919 | 231.199 | 288.953 | 27 | Aggregate, Hash, Hash Join, Seq Scan, Sort |
| repeat_purchase | zaman aşımı (>60000, warmup) | - | - | - | Aggregate, Gather Merge, Hash, Hash Join, Index Scan, Nested Loop, Seq Scan, Sort, Subquery Scan, Unique |
| category_mv | 0.512 | 0.421 | 0.890 | 74 | Seq Scan, Sort |

## E1_customer_history — Bir kişinin (customer_unique_id) sipariş geçmişi (B-tree indeks)

| Durum | medyan | min | max | hızlanma | sonuç aynı | kullanılan indeks | Seq Scan | plan ANALYZE | uygulama ms (1 kez) | indeks bayt | yazma medyan ms |
|---|---:|---:|---:|---:|---|---|---|---|---:|---:|---:|
| baseline | 11.965 | 10.798 | 13.713 |  | - | fact_orders_customer_id_key | dim_customer | True |  |  | 55.727 |
| btree_customer_unique_id | 0.755 | 0.644 | 1.028 | 15.85 | True (ref: baseline) | fact_orders_customer_id_key, perf_dim_customer_unique_idx | - | True | 298.247 | 5742592 | 407.996 |

EXPLAIN dosyaları: `plans/E1_customer_history_baseline.json`, `plans/E1_customer_history_btree_customer_unique_id.json`

## E2_seller_date_range — En çok kalemi olan satıcının 2018-01..03 günlük satışları (tek kolon / birleşik / INCLUDE indeks)

| Durum | medyan | min | max | hızlanma | sonuç aynı | kullanılan indeks | Seq Scan | plan ANALYZE | uygulama ms (1 kez) | indeks bayt | yazma medyan ms |
|---|---:|---:|---:|---:|---|---|---|---|---:|---:|---:|
| baseline | 16.836 | 15.303 | 19.671 |  | - | - | fact_sales | True |  |  | 79.894 |
| btree_seller | 3.151 | 2.649 | 3.588 | 5.34 | True (ref: baseline) | perf_sales_seller_idx | - | True | 192.272 | 1007616 | 324.814 |
| composite_seller_date | 1.327 | 0.969 | 1.665 | 12.69 | True (ref: baseline) | perf_sales_seller_date_idx | - | True | 234.715 | 4644864 | 465.584 |
| composite_include_price | 0.739 | 0.593 | 1.505 | 22.78 | True (ref: baseline) | perf_sales_seller_date_incl_idx | - | True | 249.475 | 7659520 | 489.41 |

EXPLAIN dosyaları: `plans/E2_seller_date_range_baseline.json`, `plans/E2_seller_date_range_btree_seller.json`, `plans/E2_seller_date_range_composite_seller_date.json`, `plans/E2_seller_date_range_composite_include_price.json`

## E3_open_orders — Teslim edilmemiş son 50 sipariş (durum indeksi / tam indeks / partial index)

| Durum | medyan | min | max | hızlanma | sonuç aynı | kullanılan indeks | Seq Scan | plan ANALYZE | uygulama ms (1 kez) | indeks bayt | yazma medyan ms |
|---|---:|---:|---:|---:|---|---|---|---|---:|---:|---:|
| baseline | 15.632 | 15.043 | 18.261 |  | - | - | fact_orders | True |  |  | 88.41 |
| btree_status | 15.883 | 14.628 | 17.273 | 0.98 | True (ref: baseline) | - | fact_orders | True | 94.02 | 712704 | 214.255 |
| full_purchase_desc | 1.906 | 1.409 | 2.309 | 8.2 | True (ref: baseline) | perf_orders_purchase_full_idx | - | True | 128.333 | 6725632 | 305.018 |
| partial_open_orders | 0.768 | 0.649 | 0.819 | 20.35 | True (ref: baseline) | perf_orders_open_partial_idx | - | True | 38.394 | 221184 | 97.489 |

EXPLAIN dosyaları: `plans/E3_open_orders_baseline.json`, `plans/E3_open_orders_btree_status.json`, `plans/E3_open_orders_full_purchase_desc.json`, `plans/E3_open_orders_partial_open_orders.json`

## E4_repeat_purchase_rewrite — Tekrar satın alma oranı (reporting.v_repeat_purchase) (sorgu düzenleme)

| Durum | medyan | min | max | hızlanma | sonuç aynı | kullanılan indeks | Seq Scan | plan ANALYZE | uygulama ms (1 kez) | indeks bayt | yazma medyan ms |
|---|---:|---:|---:|---:|---|---|---|---|---:|---:|---:|
| baseline | zaman aşımı (>60000, warmup) | - | - |  | - | fact_orders_customer_id_key | dim_customer, fact_orders | False |  |  |  |
| btree_customer_unique_id | 1507.649 | 1442.916 | 1594.754 | ≥ 39.8 | referans | fact_orders_customer_id_key, perf_dim_customer_unique_idx | dim_customer, fact_orders | True | 301.051 | 5742592 |  |
| single_pass_aggregate | 399.993 | 359.713 | 430.222 | ≥ 150.0 | True (ref: btree_customer_unique_id) | - | dim_customer, fact_orders | True |  |  |  |

EXPLAIN dosyaları: `plans/E4_repeat_purchase_rewrite_baseline.json`, `plans/E4_repeat_purchase_rewrite_btree_customer_unique_id.json`, `plans/E4_repeat_purchase_rewrite_single_pass_aggregate.json`

## E5_category_sales_mv — Kategori satışları ve kümülatif pay (materialized view)

| Durum | medyan | min | max | hızlanma | sonuç aynı | kullanılan indeks | Seq Scan | plan ANALYZE | uygulama ms (1 kez) | indeks bayt | yazma medyan ms |
|---|---:|---:|---:|---:|---|---|---|---|---:|---:|---:|
| baseline | 566.697 | 536.928 | 603.570 |  | - | - | dim_customer, dim_product, fact_orders, fact_sales | True |  |  |  |
| read_materialized_view | 0.856 | 0.771 | 1.339 | 662.03 | True (ref: baseline) | - | mv_category_sales | True |  |  |  |

EXPLAIN dosyaları: `plans/E5_category_sales_mv_baseline.json`, `plans/E5_category_sales_mv_read_materialized_view.json`

## E6_rfm_work_mem — RFM: reporting.fn_customer_rfm(as_of) (oturum work_mem (planda diske taşma için))

| Durum | medyan | min | max | hızlanma | sonuç aynı | kullanılan indeks | Seq Scan | plan ANALYZE | uygulama ms (1 kez) | indeks bayt | yazma medyan ms |
|---|---:|---:|---:|---:|---|---|---|---|---:|---:|---:|
| baseline | 1730.842 | 1587.083 | 1761.300 |  | - | - | - | True |  |  |  |
| work_mem_64mb | 1666.164 | 1623.924 | 1757.978 | 1.04 | True (ref: baseline) | - | - | True | 0.341 |  |  |

EXPLAIN dosyaları: `plans/E6_rfm_work_mem_baseline.json`, `plans/E6_rfm_work_mem_work_mem_64mb.json`

## E5 ek — materialized view maliyetleri

| Ölçüm | medyan | min | max |
|---|---:|---:|---:|
| REFRESH (normal) | 559.814 | 540.688 | 584.695 |
| REFRESH CONCURRENTLY | 549.224 | 531.020 | 649.395 |

- Satır: 74; depolama: heap 8192 bayt, UNIQUE indeks 16384 bayt, toplam 40960 bayt
- Güncellik: view toplamı 13221498.11 → 13221499.11; yenilenmemiş MV toplamı 13221498.11 (değişikliği yansıtıyor mu: False)

## L1 — COPY ve pandas to_sql

- Kaynak: `olist_order_items_dataset.csv` (15438671 bayt)
- Hedef: perf.load_target (order_id text, order_item_id text, product_id text, seller_id text, shipping_limit_date text, price text, freight_value text), indeks yok; işlem: her çalışma: BEGIN; TRUNCATE; yükleme; COMMIT
- Sürümler: {'pandas': '3.1.0', 'sqlalchemy': '2.1.6'}; to_sql ortak: schema='perf', if_exists='append', index=False
- pandas.read_csv (dtype=str, keep_default_na=False, na_filter=False): 297.000 | 287.625 | 317.649 ms
- Tüm yöntemlerin sonucu aynı: True

| Yöntem | method | chunksize | medyan | min | max | satır |
|---|---|---:|---:|---:|---:|---:|
| copy_from_stdin | - | - | 1230.757 | 1025.817 | 1392.231 | 112650 |
| to_sql_default_chunk10000 | None | 10000 | 3727.607 | 3678.310 | 3870.935 | 112650 |
| to_sql_multi_chunk1000 | multi | 1000 | 14764.324 | 14649.744 | 15286.157 | 112650 |

## P1 — Partitioning (yalıtılmış, gerçek hacim)

Satır sayıları: perf.orders_plain=99441, perf.orders_part=99441, perf.orders_part_2016=329, perf.orders_part_2017=45101, perf.orders_part_2018=54011, perf.orders_part_default=0

| Sorgu | Tablo | medyan | min | max | taranan tablolar | sonuç aynı | hızlanma |
|---|---|---:|---:|---:|---|---|---:|
| one_month | plain | 12.932 | 11.099 | 16.001 | orders_plain | True |  |
| one_month | partitioned | 7.821 | 7.212 | 9.461 | orders_part_2018 | True | 1.65 |
| all_rows | plain | 30.525 | 29.530 | 40.254 | orders_plain | True |  |
| all_rows | partitioned | 33.804 | 33.210 | 37.052 | orders_part_2016, orders_part_2017, orders_part_2018, orders_part_default | True | 0.9 |

