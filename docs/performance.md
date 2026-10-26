# Performans Deneyleri

## Özet

- **Veri:** GERÇEK Olist verisi. Sentetik veya büyütülmüş veri kullanılmadı.
- **Yeniden üretme:** `.\scripts\perf.ps1 --rebuild` (yalnızca `olist_perf` veritabanını kullanır; ana `olist` veritabanına dokunmaz).
- **Önbellek:** Hiçbir ölçümde önbellek temizlenmedi. Tüm sorgu süreleri **sıcak önbellek** koşulundadır; "cold cache" ölçümü yoktur.
- **Sayıların kaynağı:**
  - Bu belgedeki tekrarlı ölçüm sayıları **B çalışmasından** gelir (`docs/perf/results/*.json`, özet `docs/perf/summary.md`; ölçüm 2026-10-24T17:03:35Z).
  - Çalışmalar arası tekrarlanabilirlik için ikinci bağımsız çalışma **A** `docs/perf/run_A_results/` altındadır (ölçüm 2026-10-24T16:53:16Z). A'nın EXPLAIN dosyaları B tarafından üzerine yazıldı; A için yalnızca sonuç JSON'ları saklıdır.
- **Tek seferlik tanı (F1):** Tekrarlı benchmark değildir; ayrı bölümde ve ayrı dosyada (`results/F1_first_load_missing_statistics.json`) tutulur.

## Ölçümlerin ait olduğu şema sürümü

| Ölçüm | Zaman (UTC) | O sırada uygulanmış son migration | Sonradan değişen ve ölçümü etkileyebilecek |
|---|---|---|---|
| E1–E6, L1, P1, katalog, MV (B çalışması) | 2026-10-24 17:03 | `150` | `170` `v_repeat_purchase`'ı değiştirdi (E4 başlangıcı eski `140` view'idir); `190`/`200` aylık nesneleri değiştirdi (katalogdaki `v_monthly_sales_growth` ölçümü eski sürüme aittir) |
| D1 dashboard sorguları | 2026-10-24 17:54 | `180` | `190` ve `200` `fn_monthly_sales`'ı değiştirdi; `monthly_full` ve `monthly_state_RJ` satırları eski sürüme aittir |
| F1, F2 | Aşama 6–7, tek ölçüm | — | Tanı amaçlı; tekrarlı benchmark değildir |

Bu aşamada (9) ölçümler yeniden çalıştırılmadı. Kazançlar tek tek sorgulara aittir; uygulamanın bütününün aynı oranda hızlandığı anlamına gelmez.

## Yöntem

| Konu | Uygulama |
|---|---|
| Ortam | PostgreSQL 16.15; Docker Desktop VM'i: 16 CPU, 7.786.148 kB bellek; `shared_buffers=163848kB`, `work_mem=4096kB`, `jit=on`, `max_parallel_workers_per_gather=2`, `random_page_cost=4` (`results/environment.json`) |
| Veritabanı | `olist_perf`. Her `--rebuild` çalışmasında silinir ve `data/raw` gerçek CSV'lerinden yükleme hattıyla (`run_pipeline`) yeniden kurulur. B: run_id `44a78aeb-cd89-4d29-ba38-e27b596bdda1`, yükleme 94,952 s (`results/rebuild.json`) |
| Satırlar | dim_customer 99.441 · dim_product 32.951 · dim_seller 3.095 · dim_date 800 · fact_orders 99.441 · fact_sales 112.650 · fact_payments 103.886 |
| Başlangıç durumu | PK ve UNIQUE indeksler korunur (13 adet). dw/reporting'deki diğer tüm indeksler kaldırılır. B'de kaldırılanlar: `dim_customer_unique_id_idx`, `fact_orders_purchase_date_idx`, `fact_orders_status_idx`, `fact_sales_product_idx`, `fact_sales_purchase_date_idx`, `fact_sales_seller_idx` (`results/baseline_state.json`). Ana modele dokunulmadı. |
| İstatistik | Deneylerden önce bir kez `VACUUM (ANALYZE)`. Deneyler arasında tekrar ANALYZE yapılmaz; büyük tablolarda örnekleme rastgele olduğu için tekrar ANALYZE planları değiştirebilirdi. |
| Sorgu ölçümü | 2 ısınma (sayılmaz) + 7 ölçüm; istemcide `execute` + `fetchall` süresi; rapor medyan / min / max. |
| Plan | `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` ayrı çalıştırılır, süreye karışmaz (`docs/perf/plans/`). |
| Tek değişiklik | Her değişiklik başlangıç durumundan uygulanır, ölçülür ve geri alınır. |
| Sonuç eşitliği | Sonuç satırlarının MD5 özeti ve satır sayısı başlangıçla karşılaştırılır. Başlangıç zaman aşımına uğradıysa ölçülebilen ilk durumla karşılaştırılır. |
| Zaman sınırı | `statement_timeout = 60000 ms`. Aşan ölçüm süre uydurulmadan "zaman aşımı" olarak kaydedilir; planı yalnızca `EXPLAIN` ile (çalıştırmadan) alınır; hızlanma yalnızca alt sınır (≥) olarak verilir. |
| Yazma / yenileme / yükleme | 1 ısınma + 5 ölçüm. İndeks kurulum süresi tek ölçümdür (n=1). |
| Parametreler | Veriden belirlenimci seçilir (`results/parameters.json`): `customer_unique_id = 8d50f5eadf50201ccdcedfb9e2ac8455` (en çok customer_id'si olan kişi), `seller_id = 6560211a19b47992c3666cc44a7e94c0` (en çok kalemli satıcı), tarih aralığı 20180101–20180331, `as_of = 2018-08-30` |

**Türetilmiş sayılar:** Hızlanma oranları (`median_speedup_*`) ham dosyalarda hazır bulunur. Metindeki diğer oranlar ve yüzdeler (ör. "~3,7×", "%65") aynı dosyalardaki medyan ve bayt değerlerinden hesaplanmıştır.

**Gürültü:** A ve B çalışmalarında aynı durumların medyanları 1 ms altındaki ölçümlerde ~%32'ye kadar farklı. Örneğin E3 partial index 0,768 → 0,524 ms, E5 MV okuma 0,856 → 0,607 ms. 10 ms üzerindeki ölçümlerde fark çoğunlukla %10'un altında. Sonuçların **yönü** ve sıralaması iki çalışmada da aynı. Tüm sonuç MD5 özetleri iki çalışmada da aynı.

## Başlangıç kataloğu (değişiklik yok)

| Sorgu | medyan ms | min | max |
|---|---:|---:|---:|
| `v_sales_kpis` | 303,373 | — | — |
| `v_monthly_sales_growth` | 351,235 | — | — |
| `mv_monthly_sales` | 0,371 | — | — |
| `v_delivery_performance` | 251,761 | — | — |
| `v_repeat_purchase` | **zaman aşımı (> 60 s, ısınmada)** | — | — |
| `mv_category_sales` | 0,908 | — | — |

min ve max değerleri `docs/perf/summary.md` içindedir.

## Deneyler

### E1: Bir kişinin sipariş geçmişi (B-tree)

`dim_customer JOIN fact_orders WHERE customer_unique_id = …`

| Durum | medyan | min | max | hızlanma | sonuç aynı | plan |
|---|---:|---:|---:|---:|---|---|
| başlangıç | 12,918 | 11,404 | 13,654 | — | — | `dim_customer` Seq Scan + `fact_orders_customer_id_key` |
| B-tree `dim_customer(customer_unique_id)` | 0,955 | 0,811 | 1,255 | 13,53× | evet | indeks taraması, Seq Scan yok |

**Maliyet:**

- İndeks 5.742.592 bayt; kurulum 271,733 ms (tek ölçüm).
- Yazma: `dim_customer`'ın tüm satırlarını boş bir kopyaya ekleme medyanı **51,383 → 427,977 ms**, yaklaşık 8 kat. Yükleme hattı her çalışmada `dim_customer`'ı yeniden yazdığı için bu maliyet her ETL'de ödenir.

**Kazanç:** Bu indeks, E4'te `v_repeat_purchase`'ı çalışabilir kılan indeksle aynıdır.

### E2: Satıcının tarih aralığındaki satışları (tek kolon / birleşik / INCLUDE)

| Durum | medyan | min | max | hızlanma | sonuç aynı | indeks bayt | yazma medyan ms |
|---|---:|---:|---:|---:|---|---:|---:|
| başlangıç (Seq Scan `fact_sales`) | 16,813 | 16,094 | 19,900 | — | — | — | 79,762 |
| `(seller_id)` | 2,823 | 2,581 | 3,485 | 5,96× | evet | 1.007.616 | 351,761 |
| `(seller_id, purchase_date_key)` | 1,258 | 0,956 | 2,020 | 13,36× | evet | 4.644.864 | 466,536 |
| `(seller_id, purchase_date_key) INCLUDE (price)` | 0,824 | 0,579 | 1,089 | 20,40× | evet | 7.659.520 | 467,812 |

- Birleşik indeks, tarih koşulunu indeks içinde süzdüğü için tek kolonlu indeksten belirgin biçimde hızlıdır.
- INCLUDE, birleşik indekse göre ek kazanç sağlar ama indeksi %65 büyütür (4,6 → 7,7 MB).
- Yazma maliyeti üç indekste de 80 ms'den 350–470 ms'ye çıkar.

### E3: Teslim edilmemiş son 50 sipariş (durum indeksi / tam indeks / partial)

`WHERE order_status <> 'delivered' ORDER BY purchase_ts DESC, order_id LIMIT 50`

| Durum | medyan | min | max | hızlanma | sonuç aynı | kullanılan indeks | indeks bayt | yazma medyan ms |
|---|---:|---:|---:|---:|---|---|---:|---:|
| başlangıç | 15,281 | 14,790 | 19,162 | — | — | — (Seq Scan) | — | 84,611 |
| `(order_status)` | 15,066 | 14,761 | 18,236 | 1,01× | evet | **kullanılmadı** | 712.704 | 200,761 |
| `(purchase_ts DESC, order_id)` tam | 1,851 | 1,365 | 2,088 | 8,26× | evet | evet | 6.725.632 | 274,017 |
| aynı kolonlar, `WHERE order_status <> 'delivered'` partial | 0,524 | 0,430 | 0,592 | 29,16× | evet | evet | **221.184** | 100,541 |

- **Kullanılmayan indeks:** `order_status` B-tree indeksi `<>` koşulunda planlayıcı tarafından **kullanılmadı**; Seq Scan devam etti. Kazanç yok, ama yazma maliyetini 84,6'dan 200,8 ms'ye çıkardı. Bu tanım ana modeldeki `fact_orders_status_idx` ile aynıdır.
- **Partial index:** Sorgu koşuluyla birebir uyumlu partial index hem en hızlısı hem de tam indeksin %3'ü kadar küçük (221 KB'a karşı 6,7 MB). Yazma maliyeti de en düşük (100,5 ms).

### E4: Tekrar satın alma oranı (sorgu düzenleme)

`reporting.v_repeat_purchase`; `DISTINCT ON` + seçim listesinde `EXISTS`

| Durum | medyan | min | max | hızlanma | sonuç aynı |
|---|---:|---:|---:|---:|---|
| başlangıç (ek indeks yok) | **zaman aşımı (> 60 s, ısınmada)** | — | — | — | ölçülemedi |
| B-tree `dim_customer(customer_unique_id)` (ana modeldeki durum) | 1.517,952 | 1.455,413 | 1.570,890 | ≥ 39,5× | referans |
| tek geçişli toplama (indeks yok) | 405,891 | 389,916 | 447,033 | ≥ 147,8× | evet (ref: B-tree durumu) |

- **Neden zaman aşımı:**
  - `EXISTS` bir join'e dönüşmüyor; her müşteri için çalışan bir `SubPlan` oluyor.
  - İndeks yokken bu alt plan her seferinde `dim_customer`'ı baştan tarıyor.
  - Tahmini plan maliyeti 252.438.047,44 (`plans/E4_repeat_purchase_rewrite_baseline.json`, yalnızca EXPLAIN).
- **Bulgu:** Ana modeldeki `v_repeat_purchase`, kabul edilebilir sürede çalışmak için `dim_customer_unique_id_idx` indeksine **bağımlı**.
- **Sorgu düzenleme:** Müşteri başına `count(DISTINCT order_id)` ile tek geçişte toplama hiçbir ek indekse ihtiyaç duymadan, indeksli `EXISTS` sürümünden yaklaşık 3,7 kat hızlı (405,9'a karşı 1.518,0 ms). Sonucu birebir aynı.
- **Uygulanmadı:** View değiştirilmedi; öneri aşağıda.

### E5: Kategori satışları (materialized view)

| Durum | medyan | min | max | hızlanma | sonuç aynı |
|---|---:|---:|---:|---:|---|
| alttaki sorgu (her seferinde hesaplama) | 568,796 | 538,207 | 644,802 | — | — |
| `reporting.mv_category_sales` okuma | 0,607 | 0,499 | 0,780 | 937,06× | evet |

MV maliyetleri (`results/mv_costs.json`):

| Ölçüm | medyan ms | min | max |
|---|---:|---:|---:|
| `REFRESH MATERIALIZED VIEW` | 563,615 | — | — |
| `REFRESH MATERIALIZED VIEW CONCURRENTLY` | 549,114 | — | — |

min ve max değerleri `summary.md` içindedir.

- **Depolama:** 74 satır; heap 8.192 bayt, UNIQUE indeks 16.384 bayt, toplam 40.960 bayt.
- **Güncellik:** İşlem içinde bir kalemin fiyatı 1,00 artırıldı (sonra ROLLBACK). View toplamı 13.221.498,11'den 13.221.499,11'e çıktı; yenilenmemiş MV toplamı 13.221.498,11'de kaldı (`mv_reflects_change: false`). MV yalnızca son yenileme anındaki veriyi gösterir; projede ETL işleminin sonunda ve `sp_refresh_reports()` ile yenilenir.
- **Değerlendirme:** Bir yenileme, alttaki sorgunun bir kez çalışmasıyla aynı mertebede (~550–565 ms). Rapor günde bir kez yüklenip çok kez okunduğu için MV kazançlıdır. Sık değişen veride bu oran değişir.

### E6: RFM ve `work_mem`

`reporting.fn_customer_rfm('2018-08-30')`

| Durum | medyan | min | max | hızlanma | sonuç aynı | geçici blok yazımı |
|---|---:|---:|---:|---:|---|---:|
| başlangıç (`work_mem=4MB`) | 1.571,508 | 1.535,076 | 1.780,144 | — | — | 7.292 |
| `SET work_mem = '64MB'` (oturum) | 1.627,023 | 1.547,379 | 1.674,393 | **0,97×** | evet | 0 |

- 64 MB, diske taşmayı tamamen kaldırdı (7.292 → 0 geçici blok) ama hızlandırmadı. B'de medyan biraz kötüleşti (0,97×); A'da 1,04× idi. Bu fark gürültü aralığında, yani **etki yok**.
- Diske taşma bu sorgunun darboğazı değil. Ayar değişikliği önerilmez.
- Plan yalnızca `Function Scan` düğümünü gösterir; fonksiyonun içindeki plan görünmez. Geçici blok sayısı iç sorgular dahil tamponlardan gelir.

## L1: COPY ile pandas `to_sql`

| Koşul | Değer |
|---|---|
| Veri | `olist_order_items_dataset.csv` (15.438.671 bayt, 112.650 satır), gerçek veri |
| Hedef tablo | `perf.load_target`: 7 `text` kolon, **indeks yok**, her yöntemde aynı |
| İşlem | Her çalışma: `BEGIN; TRUNCATE; yükleme; COMMIT` |
| Süre | Uçtan uca, dosya okuma dahil. `to_sql` için `pandas.read_csv(dtype=str, keep_default_na=False, na_filter=False)` dahildir; okuma tek başına medyan 298,79 ms |
| Sürümler | pandas 3.1.0, SQLAlchemy 2.1.6; ortak ayarlar `schema='perf', if_exists='append', index=False` |
| Sonuç | Üç yöntemde satır sayısı ve içerik MD5'i aynı (`all_results_identical: true`) |

| Yöntem | method | chunksize | medyan ms | min | max |
|---|---|---:|---:|---:|---:|
| `COPY ... FROM STDIN` (psycopg2 `copy_expert`) | — | — | **1.262,6** | — | — |
| `to_sql` | `None` | 10000 | 3.715,595 | — | — |
| `to_sql` | `'multi'` | 1000 | 15.460,695 | — | — |

min ve max değerleri `summary.md` içindedir.

- COPY, varsayılan `to_sql`'den yaklaşık 2,9 kat hızlı.
- `method='multi'` bu kurulumda varsayılandan yaklaşık 4,2 kat **daha yavaş**.

## P1: Partitioning (isteğe bağlı, yalıtılmış)

`perf` şemasında `fact_orders`'ın 5 kolonlu iki kopyası. İkisinde de indeks yok:

- **Bölünmemiş:** 99.441 satır.
- **Yıllık RANGE partition:** 2016: 329, 2017: 45.101, 2018: 54.011, default: 0.

| Sorgu | Tablo | medyan | min | max | taranan | sonuç aynı | hızlanma |
|---|---|---:|---:|---:|---|---|---:|
| 2018-03 ayı | bölünmemiş | 12,361 | — | — | orders_plain | evet | — |
| 2018-03 ayı | partition | 8,026 | — | — | yalnız orders_part_2018 | evet | 1,54× |
| tüm satırlar | bölünmemiş | 29,803 | — | — | orders_plain | evet | — |
| tüm satırlar | partition | 36,808 | — | — | 4 partition | evet | **0,81× (yavaşladı)** |

min ve max değerleri `summary.md` içindedir.

- Partition budama ay sorgusunda ~4 ms kazandırdı.
- Tüm tabloyu tarayan sorgu ~7 ms yavaşladı.
- Gerçek hacimde (~100 bin sipariş) mutlak farklar birkaç milisaniye.
- Partition'ların bakım maliyeti var: yeni yıl partition'ı, default partition yönetimi, PK/UNIQUE'in partition anahtarını içermesi zorunluluğu.
- **Ana modele eklenmedi.** Sentetik büyütme yapılmadı; daha büyük hacimde sonuç farklı olabilir, ama bu doğrulanmadı.

## F1: Boş veritabanına ilk yüklemede istatistik eksikliği (tek seferlik tanı, benchmark değil)

Kaynak: `results/F1_first_load_missing_statistics.json`. Ölçümler n=1'dir.

**Belirti:**

- İlk `--rebuild` denemesinde boş `olist_perf`'e gerçek veriyle yapılan ilk ETL, `sql/tests/080_reporting_analyses_consistent.sql` kontrolünde takıldı.
- Kontrol 8 dk 59 s'den uzun çalıştı ve elle iptal edildi. Çalışma 639,748 s sonunda `failed` kaydedildi; önceki veri korundu.

**Neden:**

- Yükleme tek bir işlem içinde yapılıyor ve dw tabloları o ana kadar hiç ANALYZE görmemişti (`reltuples` 0).
- Autovacuum işlemdeki taahhüt edilmemiş satırları göremez.
- Planlayıcı tahminleri gerçekten uzaktı (`dim_customer` için 62.350; gerçek 99.441).
- `olist` veritabanında önceki yüklemelerden kalan istatistikler bu sorunu gizlemişti.

**Düzeltme** (`sql/transform/load_dw.sql`):

- Geçici `q_*` tablolarına ve dw tablolarına, işlemin içinde `ANALYZE` eklendi. ANALYZE, aynı işlemin eklediği satırları görür.
- Tanıda, işlem içinde dw ANALYZE 1.163 ms sürdü (n=1) ve sonrasında aynı kontrol 6.954 ms'de ihlalsiz bitti (n=1).

**Doğrulama:**

- Düzeltmeden sonra boş veritabanına ilk yükleme iki ayrı kurulumda başarıyla tamamlandı: 93,135 s ve 94,952 s (B: `results/rebuild.json`).
- Düzeltmeden önceki durum, kod değiştiği için `perf` komutuyla yeniden üretilemez.

## D1: Dashboard sorguları (Aşama 7; tekrarlı ölçüm)

Kaynak: `results/D1_dashboard_queries.json`. Ortam: `results/partial_environment.json`.

- **Sorgular:** Dashboard'un (`dashboard/data.py`) çağırdığı 14 reporting fonksiyonu çağrısı, gerçek veri kapsamı ve 1 aylık aralık (2018-03) ile.
- **Durumlar:** (a) ek indeks yok, (b) ana modeldeki 6 ek indeksin hepsi. Model indekslerinin kurulumu 757,268 ms sürdü (n=1).
- **Yöntem:** Aynı yöntem (2 ısınma + 7 ölçüm, medyan ms). Sonuç MD5'leri iki durumda da 14/14 aynı.

| Sorgu | ek indeks yok | model indeksleri | kullanılan model indeksi |
|---|---:|---:|---|
| overview_full | 574,107 | 569,682 | — |
| overview_one_month | 123,389 | 69,163 | `fact_sales_purchase_date_idx` |
| overview_states_SP_RJ_full | 362,234 | 347,9 | — |
| overview_category_full | 171,489 | 174,463 | — |
| monthly_full | 598,103 | 581,09 | — |
| monthly_state_RJ | 176,281 | 209,238 | — |
| category_full | 457,132 | 463,918 | — |
| category_one_month | 127,539 | 71,31 | `fact_sales_purchase_date_idx` |
| delivery_region_full | 190,332 | 189,527 | — |
| delivery_region_one_month | 76,214 | 24,453 | `fact_orders_purchase_date_idx` |
| delivery_monthly_full | 177,446 | 181,294 | — |
| repeat_full | 327,108 | 325,109 | — |
| repeat_one_month | 79,544 | 26,612 | `fact_orders_purchase_date_idx` |
| rfm_segments | 1.064,389 | 1.022,657 | — |

Bulgular:

- **Kullanılanlar:** Dashboard sorguları yalnızca iki tarih indeksini kullanıyor ve yalnızca dar aralıklarda.
- **Tam aralık:** Tam aralıkta indeks kullanılmıyor; farklar gürültü düzeyinde. Örneğin `monthly_state_RJ` model indeksleriyle 176 → 209 ms oldu ve plan indeks kullanmadı.
- **Kullanılmayanlar:** `dim_customer_unique_id_idx`, `fact_orders_status_idx`, `fact_sales_product_idx` ve `fact_sales_seller_idx` hiçbir dashboard sorgusunda kullanılmadı.

## F2: ETL silmelerinde yabancı anahtar kontrolleri (tek seferlik tanı, benchmark değil)

Kaynak: `results/F2_etl_delete_fk_checks.json` (n=1).

- **Yöntem:** ETL'in silme sırası (`fact_payments`, `fact_sales`, `fact_orders`, ardından boyutlar) `olist_perf` üzerinde, geri alınan bir işlem içinde çalıştırıldı.

| Ölçülen DELETE | indeks yok | indeksli |
|---|---:|---:|
| `DELETE FROM dw.dim_product` | **> 120.000 ms (zaman aşımı)** | 592,723 ms (`fact_sales_product_idx`) |
| `DELETE FROM dw.dim_seller` | 13.223,166 ms | 164,398 ms (`fact_sales_seller_idx`) |

- **Neden:** Her silinen ürün veya satıcı için PostgreSQL bir yabancı anahtar kontrolü çalıştırıyor (`SELECT 1 FROM ONLY dw.fact_sales x WHERE … product_id …`). Alt tablonun anahtar kolonunda indeks yoksa bu kontrol her satır için tam tarama yapıyor.
- **Kanıt:** Ana veritabanının indeks sayaçları bununla tutarlı: `fact_sales_product_idx` 197.744 tarama, yani tam olarak 6 × 32.951 ürün; `fact_sales_seller_idx` 18.584 tarama, yani tam olarak 6 × 3.095 satıcı.
- **Sonuç:** D1'de "kullanılmayan" görünen bu iki indeks ETL için **zorunlu**. Tek bir sorgu ailesine bakarak kaldırılmamalı.

## Öneriler

Aşama 6'nın önerileri Aşama 7'de D1 ve F2 kanıtıyla yeniden değerlendirildi.

| Nesne | Kanıt | Karar / öneri |
|---|---|---|
| `v_repeat_purchase` | E4: tek geçişli sürüm indekssiz ~3,7× hızlı, sonucu aynı | **Uygulandı** (`sql/170_...`); gerçek veride iki yönlü EXCEPT ile 0 fark |
| `fact_sales_product_idx`, `fact_sales_seller_idx` | F2: ETL DELETE'lerindeki FK kontrolleri için gerekli | **Korunmalı.** 6. aşamadaki "seller indeksini birleşik indeksle değiştir" önerisi ancak birleşik indeks `seller_id` ile başlarsa (FK kontrolünü karşılar) ve ölçülürse uygulanabilir; uygulanmadı |
| `fact_orders_purchase_date_idx`, `fact_sales_purchase_date_idx` | D1: dar tarih aralıklarında 1,8–3,1× | **Korunmalı** |
| `fact_orders_status_idx` | E3 ve D1'de kullanılmadı; ama ana veritabanında 11 tarama kaydı var, kaynağı belirlenmedi | **Değiştirilmedi.** Kaldırmadan önce hangi sorgunun kullandığı (`pg_stat_statements` veya plan incelemesi) belirlenmeli |
| `dim_customer_unique_id_idx` | E1'de 13,5×; tek geçişli `v_repeat_purchase` artık bu indekse bağımlı değil; D1'de kullanılmadı | **Değiştirilmedi.** Kişi bazında sorgu (dashboard'da yok) gelmezse yeniden değerlendirilmeli |
| `mv_category_sales`, `mv_monthly_sales` | Okuma < 1 ms; yenileme ~0,55 s; depolama 40 KB | Korunmalı |
| Partitioning | Ay sorgusu 1,54×, tüm satırlar 0,81× | Eklenmemeli |
| `work_mem` | Etki yok | Değiştirilmemeli |
| Yükleme | COPY, `to_sql`'den ~2,9× hızlı | Mevcut COPY korunmalı |

## Açık noktalar

- Ölçümler tek bir makinede ve sıcak önbellekle yapıldı; soğuk önbellek veya eşzamanlı yük ölçülmedi.
- Alt-milisaniye ölçümler gürültüye açık (A/B arasında ~%32'ye kadar fark).
- Düzeltilmiş ETL asıl `olist` veritabanında başarılı oldu (9/9 kontrol, dw içeriği aynı). Ancak tek çalışmada 118,148 s sürdü; önceki tek çalışma 81,2 s idi. Bu fark ölçülmedi ve nedeni belirlenmedi (`ANALYZE` eklemesi, plan değişikliği veya gürültü olabilir). İki tek ölçüm bir benchmark değildir.

## Yeniden çalıştırma

```powershell
.\scripts\up.ps1
.\scripts\perf.ps1 --rebuild                        # olist_perf'i gerçek veriden kur + tüm deneyler (~10 dk)
.\scripts\perf.ps1 --only E3_open_orders,load       # seçili deneyler (olist_perf mevcutsa yeniden kurmaz)
```

Kimlikler: `catalog`, `E1_customer_history`, `E2_seller_date_range`, `E3_open_orders`, `E4_repeat_purchase_rewrite`, `E5_category_sales_mv`, `E6_rfm_work_mem`, `mv`, `partition`, `load`.

`--rebuild` kullanılmadan yapılan bir çalışma, önceki çalışmanın zaten kaldırdığı indeksleri listelemez (`baseline_state.json` içinde "kaldırılan: yok" görünür). Tam ve tutarlı kayıt için `--rebuild` kullanın.
