# Raporlama Katmanı

İş mantığı PostgreSQL'dedir (`reporting` şeması). Dashboard ve diğer istemciler metrikleri yeniden hesaplamaz; bu nesneleri okur. Metrik tanımları `docs/metric_definitions.md` dosyasındadır. Her analizin toplamı her ETL çalışmasında `reporting.v_sales_kpis` ile karşılaştırılır (`sql/tests/080_reporting_analyses_consistent.sql`); tutmazsa yükleme geri alınır.

Örnek değerler gerçek veriden (`run_id=d899f00e-d5f4-4451-9159-918932d5d307`) alınmıştır.

## Analizler

| Analiz | Nesne | SQL dosyası | Teknik |
|---|---|---|---|
| Aylık ürün satışı ve büyüme | `reporting.v_monthly_sales_growth` (view), `reporting.v_sales_observation_months` | `sql/100_report_monthly_sales_growth.sql`, yerini alan `sql/200_report_monthly_observation_window.sql` | gözlem aralığında boşluksuz ay serisi, `LAG` |
| Müşteri RFM | `reporting.fn_customer_rfm(as_of date)` (fonksiyon) | `sql/110_report_customer_rfm.sql` | CTE, window function |
| Kategori satışları ve kümülatif pay | `reporting.mv_category_sales` (materialized view) | `sql/120_report_category_sales.sql` | `SUM() OVER (... ROWS ...)` |
| Teslimat süresi ve geç teslim oranı | `reporting.v_delivery_performance` (view) | `sql/130_report_delivery_performance.sql` | sipariş seviyesi, `CASE`, `GROUP BY ROLLUP` |
| Tekrar satın alma oranı | `reporting.v_repeat_purchase` (view) | `sql/140_report_repeat_purchase.sql`, yerini alan `sql/170_report_repeat_purchase_single_pass.sql` | tek geçişli toplama (önce `EXISTS`), `GROUPING SETS` |
| Dashboard fonksiyonları | `reporting.fn_overview_kpis`, `fn_monthly_sales`, `fn_category_sales`, `fn_delivery_by_region`, `fn_delivery_monthly`, `fn_repeat_purchase`, `fn_rfm_segments` | `sql/160_report_dashboard_functions.sql`; `fn_monthly_sales` için `sql/190_report_monthly_sales_date_scope_fix.sql` | parametreli SQL fonksiyonları (docs/dashboard.md). `190` (Aşama 8): aylık değerler seçili tarih aralığıyla hesaplanır (KPI ile aynı kapsam); büyüme yalnızca tam aylardan, kısmi aylarda `growth_status = 'partial_month'` ve oran NULL |
| Rutinler | `sp_load_monthly_summary`, `refresh_report_objects`, `sp_refresh_reports` | `sql/150_report_routines.sql` | PL/pgSQL |

### 1. Aylık ürün satışı ve büyüme

Ay listesi (`sql/200_report_monthly_observation_window.sql`, Aşama 9 öncesi düzeltme):

- **Satış gözlem aralığı:** Satış kapsamındaki ilk satın alma gününden son satın alma gününe kadardır. Bu, RFM gözlem aralığıyla aynı tanımdır (`reporting.v_rfm_observation`, `docs/metric_definitions.md` bölüm 8).
- `reporting.v_sales_observation_months` tarih boyutunun her ayını sınıflandırır:

  | `observation_status` | Anlamı | Gerçek veri |
  |---|---|---|
  | `observed` | Ayın tamamı gözlem aralığında | 2016-10 … 2018-07 |
  | `partial` | Ayın bir kısmı gözlem aralığının başında veya sonunda kalıyor | 2016-09 (15–30), 2018-08 (1–29) |
  | `not_observed` | Ay gözlem aralığının dışında | 2018-09, 2018-10, 2018-11 |

- `v_monthly_sales_growth` ve `monthly_summary` yalnızca `observed` ve `partial` ayları içerir: gerçek veride **24 ay** (2016-09 … 2018-08).
  - Gözlem aralığı içinde satışı olmayan ay **0** olarak kalır. Bu gerçek bir sıfırdır: 2016-11'de hiç sipariş yoktur.
  - Gözlem dışı aylar raporda yer almaz; sıfır gibi de gösterilmez.
- **Gözlem dışı ayların nedeni:**
  - 2018-09'da 16, 2018-10'da 4 sipariş var, ama hiçbiri `delivered` değil. Bu ayların satışı kaynağın anlık görüntüsünde henüz gözlenemez.
  - 2018-11'de hiç sipariş yok. Ay tarih boyutunda yalnızca tahmini teslim tarihleri nedeniyle bulunur.
- Tarih boyutu **değişmedi**: teslimat metrikleri için tahmini teslim tarihlerini kapsamaya devam eder (2018-11-12'ye kadar; `sql/tests/040`).
- Yeni kolonlar: `is_partial_month`, `observed_from`, `observed_to`.

Büyüme (yalnızca iki tam gözlenmiş ay arasında):

| Durum | `growth_rate` | `growth_status` |
|---|---|---|
| Bu ay kısmi | NULL | `partial_month` |
| İlk ay | NULL | `no_previous_month` |
| Önceki ay kısmi | NULL | `previous_month_partial` |
| Önceki ay 0 (sıfır payda) | NULL | `previous_month_zero` |
| Diğer | `round((bu ay − önceki ay) / önceki ay, 4)` | `computed` |

- `prev_product_sales` ve `product_sales_change` ham değerlerdir ve her zaman tanımlıdır; nasıl yorumlanacakları `growth_status`'a göre belirlenir.
- Gerçek veride 2016-10'un büyümesi artık hesaplanmıyor. Önceden yalnızca 16 günü gözlenen Eylül'e (134,97) göre hesaplanıyordu.
- 2017-01'in büyümesi (`growth_rate = 10255.7303`; tutar önceki ayın yaklaşık 10.257 katı) iki tam ay arasında olduğu için hesaplanır. Önceki ayın (2016-12) tutarı yalnızca 10,90'dır; büyük oran bundan kaynaklanır.
- `reporting.fn_monthly_sales` (dashboard) aynı kuralı izler ve buna ek olarak kullanıcının tarih filtresini dikkate alır. İki tür kısmi ay birlikte şöyle değerlendirilir:

  | Durum | Kısmi ayın nedeni | O ayın çubuğu | O ayın oranı | Sonraki ayın oranı |
  |---|---|---|---|---|
  | Ay gözlem aralığının sınırında (2016-09, 2018-08) | veri yok / gözlenmedi | gözlenen günler | NULL, `partial_month` | NULL, `previous_month_partial` |
  | Ay tarih filtresiyle kesiliyor | kullanıcı seçimi; ay tamamen gözlenmiş | yalnızca seçili günler | NULL, `partial_month` | **hesaplanır**, önceki ayın **tam** değerinden |
  | İkisi birden | — | seçili ve gözlenen günler | NULL, `partial_month` | gözlem sınırı kuralı geçerli |

  - Oran her zaman iki tam takvim ayı arasındadır ve tarih filtresine bağlı değildir. Filtre yalnızca çubukları (gösterilen tutarları) sınırlar.
  - Örnek, 10.06–29.08.2018:
    - Haziran çubuğu 593.244,06 (filtreli); Temmuz oranı tam Haziran'dan (856.077,86) 0,0139.
    - Filtreli Haziran'dan hesaplansaydı oran 0,4631 olurdu; bu, ayın gerçek büyümesi değildir.
    - Arayüz bilgi kutusu bu yüzden "Önceki aya göre (tam aylar)" der, grafik açıklaması da bunu belirtir.
  - `prev_product_sales` önceki ayın **tam** değeridir; kısmi çubuktaki tutarla aynı olmayabilir.

- Sıfıra bölme yapılmaz ve "sonsuz büyüme" uydurulmaz.
- Mutlak fark (`product_sales_change`) her zaman verilir.
- Gerçek veride 2016-12, önceki ayı (2016-11) sıfır olduğu için `previous_month_zero` durumundadır.

### 2. Müşteri RFM: `fn_customer_rfm(as_of date)`

| Kural | Açıklama |
|---|---|
| Birim | `customer_unique_id`; yalnızca satış kapsamındaki (delivered) siparişler |
| `as_of` | Zorunlu (NULL → hata). `CURRENT_DATE` / `now()` kullanılmaz; bunu bir test kod düzeyinde doğrular |
| Tarih filtresi | `purchase_ts < as_of`: as_of günü ve sonrasındaki satın almalar dışlanır (as_of gözlem gününün başıdır) |
| Önerilen as_of | `reporting.v_rfm_observation.observation_date` (son satın alma günü + 1). Gerçek veride 2018-08-30 |
| Recency | `as_of − son satın alma günü` (gün, ≥ 1). Düşük daha iyi |
| Frequency | Farklı `order_id` sayısı (kalem değil). Yüksek daha iyi |
| Monetary | Ürün satış tutarı (kargo hariç). Yüksek daha iyi |

Bilinen sınır: sipariş durumu kaynağın son anlık görüntüsüdür. Geçmiş bir `as_of` için o tarihteki durum (ör. o an henüz teslim edilmemiş olması) bilinmez; filtre yalnızca satın alma zamanına uygulanır.

#### Puanlama (1–5, 5 en iyi)

- **R ve M:** kümülatif dağılıma göre beşli dilim.
  - Hesap: `ceil(5 × (değeri bu müşteriyle aynı veya daha düşük olan müşteri sayısı) / müşteri sayısı)`. R için `6 − bu değer`.
  - Tam sayı aritmetiğiyle hesaplanır; kayan nokta sınır hatası olmaz.
- **F:** sabit eşik: 1, 2, 3, 4, 5+ sipariş → 1..5.
  - Gerçek veride müşterilerin %97'si (90.557 / 93.358) tek siparişli. Dilim yöntemi bu kadar çok eşit değerle frequency için anlamsız olurdu.
- **NTILE kullanılmadı:**
  - `NTILE` eşit değerleri satır sırasına göre farklı dilimlere bölebilir, yani aynı recency'ye sahip iki müşteri farklı puan alabilir.
  - Eşitler arasında sıra tanımlı değilse sonuç her çalıştırmada değişebilir.
  - Kullanılan yöntemde eşit değerler **her zaman aynı puanı** alır.
- **Dilimlerin dengesi:** Gerçek veride R ve M dilimleri dengelidir (her biri ~18,2–19,0 bin). Eşitlik çok olduğunda dilimler eşit büyüklükte olmayabilir.
- **Küçük müşteri grupları:** Puanlar 1–5 aralığının tamamını kapsamayabilir. Örneğin 3 müşteride R puanları 4, 2, 1; 2 müşteride R puanları 3, 1 olur (testlerde doğrulandı). Segmentler bu nedenle puan eşikleriyle tanımlanır.

#### Segmentler (ilk eşleşen kural)

| Sıra | Segment | Kural | Gerçek veri |
|---|---|---|---:|
| 1 | `champions` | R ≥ 4, F ≥ 2, M ≥ 4 | 931 |
| 2 | `at_risk` | F ≥ 2, R ≤ 2 | 997 |
| 3 | `loyal` | F ≥ 2 (diğer) | 873 |
| 4 | `new_high_value` | F = 1, R ≥ 4, M ≥ 4 | 14.609 |
| 5 | `recent` | F = 1, R ≥ 4 | 21.509 |
| 6 | `hibernating_high_value` | F = 1, R ≤ 2, M ≥ 4 | 14.016 |
| 7 | `lost` | F = 1, R ≤ 2 | 22.376 |
| 8 | `needs_attention` | diğer (F = 1, R = 3) | 18.047 |

`rfm_code` = R, F ve M puanlarının yan yana yazılmış hali (ör. `125`).

### 3. Kategori satışları ve kümülatif pay

- Kategori adı `category_label`'dır (çeviri politikası: `docs/etl_pipeline.md`).
- Sıralama `product_sales` azalan, eşitlikte `category_label` artandır; yani deterministiktir.
- Kümülatif toplam açıkça `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` ile hesaplanır. Varsayılan `RANGE` çerçevesi eşit tutarlı kategorileri aynı kümülatif değerde birleştirirdi; bu fark testle gösterilir.
- `order_count` kategoride kalemi olan farklı sipariş sayısıdır. Bir sipariş birden çok kategoride olabileceğinden, kategorilerin sipariş sayıları toplanırsa toplam sipariş sayısını aşabilir.
- Gerçek veri:
  - 74 kategori var; satışın %80'ine 18. kategoride ulaşılıyor.
  - İlk sıra `health_beauty` (%9,33).
  - Kategorisiz ürünler (`uncategorized`) 21. sırada (%1,29).

### 4. Teslimat süresi ve geç teslim oranı

- Sipariş seviyesindedir (`v_orders`); kalem satırlarına inilmez.
- `GROUP BY ROLLUP (purchase_year, purchase_month)` → `grouping_level` değerleri `month`, `year`, `total`.
- Pay/payda kuralları `docs/metric_definitions.md` 5. ve 6. bölümdedir. Teslim zamanı ölçülen sipariş yoksa ortalama ve oran NULL olur.
- Süre dilimleri: 0–7, 7–14, 14–30, 30+ gün (üst sınır dahil).
- Gerçek veride geç teslim oranı yıllara göre: 2016 0,0112 · 2017 0,0565 · 2018 0,0773 · toplam 0,0677.

### 5. Tekrar satın alma

- Birim `customer_unique_id`'dir.
- Tekrar eden müşteri: kapsamda en az 2 **farklı** `order_id`'si olan kişi.
- Kohort = ilk satın alma ayı (`min(purchase_month)`); `GROUPING SETS` ile kohort satırları ve genel toplam.
- Gerçek veri: 2.801 / 93.358 = 0,0300.

**Tanım değişikliği yok, uygulama değişti** (`sql/170_report_repeat_purchase_single_pass.sql`, Aşama 7):

- **İlk sürüm** (`sql/140`): `DISTINCT ON` + seçim listesinde `EXISTS`. Ölçüm, bu `EXISTS`'in semi-join'e dönüşmediğini gösterdi: müşteri başına çalışan bir SubPlan oluyordu. `dim_customer(customer_unique_id)` indeksi olmadan 60 s zaman sınırını aştı; indeksle medyan 1.517,952 ms (docs/performance.md, E4).
- **Yeni sürüm**: müşteri başına `count(DISTINCT order_id)` ile tek geçişli toplama. İndekssiz medyan 405,891 ms.
- **Sonuç eşitliği:** İki çalışmanın (A ve B) MD5 özetleri ve gerçek `olist` veritabanında iki yönlü `EXCEPT ALL` karşılaştırması (0 / 0 fark, 24 / 24 satır) iki sürümün birebir aynı sonucu verdiğini gösterdi.
- **Bu bölüm, 5. aşamadaki "EXISTS seçildi" gerekçesinin yerini alır.**

## Rutinler ve işlem kuralları

| Rutin | Tür | İşlem kontrolü | Görev |
|---|---|---|---|
| `reporting.sp_load_monthly_summary(year int)` | prosedür | yok | `reporting.monthly_summary` içinde o yılı siler ve `v_monthly_sales_growth`'ten yeniden ekler. Tekrar çağrı çoğaltmaz (PK `month_start`; advisory lock ile sıralanır). Tarih boyutunda olmayan yıl hata verir. |
| `reporting.refresh_report_objects()` | fonksiyon | yok | Tüm `reporting` MV'lerini ve tüm yılların aylık özetini yeniler; ne yaptığını jsonb döndürür. ETL bunu yükleme işleminin içinde çağırır. |
| `reporting.sp_refresh_reports()` | prosedür | **var** | Yukarıdakini çalıştırır ve sonucu `meta.report_refresh_runs` tablosuna kalıcı yazar. |

### PostgreSQL 16 kuralları

Kaynaklar: [plpgsql-transactions](https://www.postgresql.org/docs/16/plpgsql-transactions.html), [REFRESH MATERIALIZED VIEW](https://www.postgresql.org/docs/16/sql-refreshmaterializedview.html).

**Transaction kontrolü:**

- COMMIT/ROLLBACK yalnızca üst düzeyden (veya araya `SELECT` gibi başka bir komut girmeden iç içe) çağrılan `CALL`/`DO` içinde yapılabilir.
  - Bu yüzden `sp_refresh_reports` istemciden **autocommit** modunda çağrılır: `.\scripts\etl.ps1 refresh-reports`.
  - Açık bir `BEGIN` bloğu içinden çağrılırsa ilk `COMMIT` `invalid transaction termination` hatası verir ve hiçbir kayıt kalmaz. Belge bu durumu açıkça yazmadığı için davranış testle doğrulandı.
- "A transaction cannot be ended inside a block with exception handlers": `sp_refresh_reports` içinde COMMIT'ler EXCEPTION bloğunun **dışındadır**. Akış:
  1. `running` kaydı → `COMMIT`.
  2. `BEGIN … EXCEPTION`: yenileme. Hata olursa bloğun yaptığı her şey (MV ve özet değişiklikleri) geri alınır; handler `failed` ve hata nedenini yazar.
  3. `COMMIT` (bloğun dışında): sonuç kaydı kalıcı olur.
  4. Hata olduysa özgün SQLSTATE ile yeniden yükseltilir; çağıran başarısızlığı görür, kayıt kalır.
- Fonksiyonlarda işlem kontrolü kullanılmadı; bu sayede `refresh_report_objects()` hem ETL işleminin içinde hem prosedürde güvenle çağrılabiliyor.

**Materialized view yenileme:**

- `CONCURRENTLY` yalnızca MV **doldurulmuşsa** ve yalnızca kolon adlarından oluşan, `WHERE` içermeyen bir `UNIQUE` index varsa kullanılabilir. `WITH NO DATA` ile birlikte kullanılamaz.
- `refresh_report_objects()` iki koşulu katalogdan (`pg_matviews.ispopulated`, `pg_index`) kontrol eder. Koşullar sağlanmıyorsa normal (okumaları engelleyebilen) `REFRESH` yapar ve hangi yöntemi kullandığını sonuca yazar: `initial_population` veya `blocking_no_unique_index`.

| MV | İlk doldurma | UNIQUE index |
|---|---|---|
| `mv_monthly_sales` | `WITH NO DATA` ile oluşturuldu; ilk yenileme normal REFRESH ile (`initial_population`) | `purchase_month` |
| `mv_category_sales` | `WITH DATA` ile oluşturuldu (boş veritabanında 0 satırla doldurulmuş sayılır) | `category_label` |

Gerçek veride iki `sp_refresh_reports` çağrısı da başarılı oldu; ikisi de `concurrently` modunda çalıştı ve ~1,4 s sürdü.

### Testlerle doğrulanan davranışlar

`tests/test_reporting.py` dosyasındaki testler; elle hesaplanmış beklenen değerlerle karşılaştırılır.

**Analizler:**

- Çoklu ödeme sipariş ve tutarları çoğaltmıyor.
- Satışsız ay 0 olarak görünüyor; ardından gelen ayda sıfır payda `NULL` / `previous_month_zero` veriyor.
- Kategorilerde eşit tutarlar deterministik sıralanıyor ve kümülatif toplam `ROWS` çerçevesiyle doğru.
- ROLLUP ara toplamı ve genel toplamı doğru; geç teslim oranında sıfır payda `NULL` veriyor.
- Tekrar alım, farklı `customer_id`'lerle aynı kişi için doğru sayılıyor (Aşama 7'deki yeni sürümle de aynı test geçiyor).

**RFM:**

- Gözlem tarihi sınırı doğru: gözlem günündeki satın alma dışlanıyor.
- `as_of` boşsa hata veriyor.
- Puanlar ve segmentler beklenen değerlerle aynı.

**Rutinler:**

- `sp_load_monthly_summary` hem ayrı çağrılarda hem aynı işlem içinde iki kez çağrıldığında çoğaltma yapmıyor.
- `sp_refresh_reports` boş veritabanında önce `initial_population`, sonra `concurrently` modunda çalışıyor; tekrar çağrılar sonucu değiştirmiyor.
- Açık işlem içinden yapılan çağrı reddediliyor.
- Kilit zaman aşımıyla düşen yenilemede `failed` kaydı ve `55P03` kodu kalıcı oluyor, aylık özet değişmiyor.

## Bilinen sınırlar

- Dashboard bu nesneleri `sql/160` içindeki parametreli `fn_*` fonksiyonları üzerinden gösterir (`docs/dashboard.md`).
- `fn_customer_rfm('2018-08-30')` tekrarlı ölçümde medyan 1.571,508 ms sürdü (`docs/performance.md`, E6; sıcak önbellek, migration 170–200'den önceki şema). `work_mem` artışı hızlandırmadı.
- Geçmiş tarihli RFM tam bir tarihsel durum analizi değildir: kaynakta sipariş durumlarının geçmişi yoktur (yukarıdaki "Bilinen sınır").
- Rapor nesneleri ETL'in sonunda zaten yenilenir. `sp_refresh_reports` ise ETL dışında elle veya zamanlanmış olarak yenilemek ve bu yenilemeyi kayıt altına almak içindir.
