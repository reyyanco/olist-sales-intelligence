# Yükleme Hattı (CSV → staging → dw)

Tek komut:

```powershell
.\scripts\etl.ps1
```

Komut, konteynerde `python -m etl run` çalıştırır:

1. Numaralı SQL dosyalarını uygular (`migrate`).
2. Tam yenileme yapar: `data/raw` → staging → dw → reporting.
3. Kalite kontrollerini çalıştırır.

Son çalışmaları görmek için: `.\scripts\etl.ps1 runs`.

## Strateji: tam yenileme

- Her çalışma staging ve dw'yi kaynak dosyalardan **baştan** kurar.
- **Artımlı yükleme uygulanmadı.** Değişen satırları algılama veya yalnızca yeni dosyaları yükleme gibi bir özellik yoktur.
- Aynı dosyalarla ikinci çalıştırma aynı sonucu üretir. Bu, testte ve gerçek veride satır içerik özetleriyle doğrulandı (bkz. `docs/project_state.md`, Aşama 4).

## İşlem (transaction) sınırları

| Adım | İşlem |
|---|---|
| `meta.etl_runs` → `running` | Ayrı, kısa işlem; hemen taahhüt edilir |
| Dosya varlığı, SHA-256, kayıt sayısı | İşlem dışı; dosyalar yalnızca okunur (`rb`) |
| Advisory lock; staging `TRUNCATE ... RESTART IDENTITY` + `COPY FROM STDIN`; doğrulama, ret ve tekrar ayrımı; dw `DELETE` + `INSERT`; `REFRESH MATERIALIZED VIEW`; kalite kontrolleri; dosya özetinin yeniden kontrolü; ret kayıtları, dosya sayımları, kontrol sonuçları | **Tek işlem** |
| `meta.etl_runs` → `succeeded` / `failed` + süre + hata | Ayrı işlem; başarısız çalışmada o ana kadar toplanan dosya sayımları ve kontrol sonuçları da burada yazılır |

Sonuçları:

- **Başarısızlıkta veri korunur.** Herhangi bir adım hata verirse ya da `error` düzeyindeki bir kontrol başarısız olursa staging, dw, reporting ve ret kayıtları birlikte geri alınır; önceki geçerli veri olduğu gibi kalır.
- **Başarısızlık kaydı kaybolmaz.** Çalışma kaydı veri işleminden ayrı yazıldığı için `failed` durumu ve hata nedeni rollback'ten etkilenmez.
- **Okuyanlar yarım veri görmez.** dw tabloları `TRUNCATE` yerine `DELETE` ile yenilenir. Yükleme sürerken dashboard gibi okuyan oturumlar kilit beklemeden önceki taahhüt edilmiş veriyi görür (MVCC); yeni veri, işlem bittiği anda bütünüyle görünür hale gelir. `mv_monthly_sales` doluysa `CONCURRENTLY` ile yenilenir.
- **Aynı anda iki yükleme çalışmaz.** İkinci çalışma advisory lock'ta bekler.

Bilinen bedel: `DELETE` ölü satır bırakır; PostgreSQL autovacuum bunları temizler. Ana veritabanı 388.693.015 bayt iken aynı verinin yedekten geri yüklenmiş kopyası 321.608.727 bayttı (`docs/validation/backup_restore_check.json`); fark bu birikimle tutarlıdır ama ayrıca ölçülmedi.

Süre (tek ölçümler, benchmark değil; `meta.etl_runs`): Aşama 4–5'te 71–83 s; `ANALYZE` eklemesinden ve 160–180 migration'larından sonra ana veritabanında 118,1 s ve 137,1 s; boş volume'a temiz kurulumda 76,2 s ve 102,9 s. Farkın nedeni ölçülmedi.

## Dosya ve kolon kontrolleri

- **Dosya:** 9 dosyanın tamamı bulunmalıdır; eksik dosya varsa çalışma başlamadan başarısız olur.
- **Kolon:** Başlıkta bütün zorunlu kolonlar bulunmalı, bilinmeyen veya tekrarlanan kolon olmamalıdır. Hata mesajı eksik, fazla ve tekrarlanan kolonları ayrı ayrı listeler. Kolon sırası farklı olabilir.
- **Ön kontrol:** Bütün başlıklar, hiçbir tablo boşaltılmadan **önce** kontrol edilir.
- **Satır mutabakatı:** Python CSV okuyucuyla sayılan kayıt sayısı, COPY ile staging'e giren satır sayısına eşit olmalıdır (`000_source_rows_match_staging`).
- **Kaynak dosyalar değiştirilmez:** Dosyalar yalnızca okunur, `data/raw` konteynere salt okunur bağlanır. SHA-256 değeri yüklemenin başında ve sonunda karşılaştırılır; dosya yükleme sırasında değiştiyse çalışma başarısız olur.

## Dönüşüm kuralları

| Konu | Kural |
|---|---|
| Boş değer | Boş metin (`''`) ve NULL aynı kabul edilir (eksik değer). COPY CSV'de tırnaksız boş hücre NULL gelir. |
| Kimlikler | Metin; `^[0-9a-f]{32}$`. Değiştirilmez, kırpılmaz. |
| Posta kodu öneki | Metin; `^[0-9]{5}$`. Baştaki sıfır korunur, sayıya dönüştürülmez. |
| Eyalet | `^[A-Z]{2}$` |
| Zaman | `YYYY-MM-DD HH:MM:SS` ve takvimde geçerli (`meta.is_valid_timestamp`). `timestamp without time zone` olarak saklanır; **saat dilimi dönüşümü yapılmaz**. |
| Zorunlu zamanlar | Satın alma zamanı ve tahmini teslim. Onay, kargoya veriliş ve teslim zamanı boş olabilir. |
| Tahmini teslim | Saat kısmı `00:00:00` olmalı; `date` olarak saklanır. |
| Zaman sıralaması | Onay ve teslim, satın almadan önce olamaz. Kargoya veriliş için kural yok (gerçek veride 166 istisna). |
| Para | `^[0-9]{1,10}(\.[0-9]{1,2})?$` → `numeric(12,2)`. 2'den fazla ondalık hane **reddedilir**, yuvarlanmaz. Fiyat > 0, kargo ve ödeme ≥ 0. |
| Tam sayılar | `order_item_id`, `payment_sequential` 1–9999; taksit 0–9999; yorum puanı 1–5; ürün ölçüleri tam sayı (boş olabilir). |
| Durum ve ödeme türü | Bilinen değer kümeleri (`docs/data_dictionary.md`). |
| Metin alanları | Şehir adları ve yorum metinleri olduğu gibi saklanır. |

## Hatalı kayıtlar

Her ret `meta.etl_rejected_rows` tablosuna şu bilgilerle yazılır: `run_id`, kaynak tablo, kaynak kayıt sırası (`_row_id`), doğal anahtar, **neden listesi** ve ham kayıt (jsonb). Ret nedenleri:

- **Satırın kendi doğrulaması:** `invalid_purchase_timestamp`, `invalid_price`, `invalid_review_score` gibi.
- **İlişkiler:**
  - `customer_not_found`, `product_not_found`, `seller_not_found`, `order_not_found`: üst kayıt kaynakta hiç yok.
  - `customer_rejected`, `product_rejected`, `seller_rejected`, `order_rejected`: üst kayıt kaynakta var ama reddedildi.
- **Sipariş bütünlüğü:**
  - Bir kalemi veya ödemesi reddedilen sipariş eksik tutarla yüklenmez, bütünüyle reddedilir (`item_rejected` / `payment_rejected`).
  - Reddedilen siparişin kalemleri, ödemeleri ve yorumları da reddedilir (`order_rejected`).
  - Yorum reddi siparişi etkilemez; yorumlar satış tutarına girmez.
- **Tekrarlar:** aşağıdaki bölüme bakın.

Özet rapor: `sql/reports/010_rejections_by_reason.sql`. Kayıtlar her çalışma için ayrı tutulur.

## Tekrar kayıtlar ve çelişkili anahtarlar

| Durum | Tanım | Karar |
|---|---|---|
| Birebir tekrar | Aynı doğal anahtar, tüm kaynak kolonları aynı | İlk kaynak satırı kalır; diğerleri `duplicate_removed` (`exact_duplicate`) |
| Çelişkili anahtar | Aynı doğal anahtar, en az bir kolonu farklı | **Hiçbir sürüm seçilmez**; hepsi `rejected` (`conflicting_key`). Bağlı kayıtlar ilişki kurallarıyla reddedilir. |

Doğal anahtarlar `docs/data_dictionary.md` içindedir. Rapor: `sql/reports/040_duplicates_and_conflicts.sql`. Gerçek veride ikisi de 0 çıktı.

## Kategori çevirisi politikası

| Durum | `category_name_english` | `category_label` | `category_translation_status` |
|---|---|---|---|
| Kategori var, çeviri var | çeviri | çeviri | `translated` |
| Kategori var, çeviri yok | NULL | Portekizce ad, değiştirilmeden | `untranslated` |
| Kategori boş | NULL | `uncategorized` | `missing_category` |

Uydurma çeviri yazılmaz. Raporlarda `category_label` kullanılır. Gerçek veride 32.328 ürün `translated`, 13 ürün `untranslated` (`pc_gamer` ve `portateis_cozinha_e_preparadores_de_alimentos`), 610 ürün `missing_category`.

## Kalite kontrolleri

`error` düzeyi: başarısızsa yükleme geri alınır.

| Kontrol | İçerik |
|---|---|
| `000_source_rows_match_staging` | Kaynak kayıt sayısı = staging satır sayısı |
| `010_row_counts_match_staging.sql` | staging = dw + ret + tekrar (tablo başına) |
| `020_order_totals_match_detail.sql` | `fact_orders` toplamları = `fact_sales` / `fact_payments` ayrıntısı |
| `030_reporting_totals_not_duplicated.sql` | Raporlama toplamları = kabul edilen kaynak satırlarından hesaplanan toplamlar |
| `040_dim_date_covers_orders.sql` | Tarih boyutu boşluksuz ve sipariş tarih aralığıyla aynı |
| `050_natural_keys_unique.sql` | Kabul edilen doğal anahtarlar tekil; çelişkili anahtar dw'ye girmemiş |
| `060_no_orphans_in_dw.sql` | Yetim FK yok |
| `070_order_and_item_counts.sql` | Sipariş sayısı, kalem sayısı ve kalem tutarları ayrı ayrı (tüm durumlar ve teslim edilmiş) |
| `080_reporting_analyses_consistent.sql` | Raporlama analizlerinin toplamları `v_sales_kpis` ile aynı; aylık raporlar yalnızca gözlem aralığındaki ayları içerir (Aşama 5, 9 öncesi) |
| `090_dashboard_functions_consistent.sql` | Dashboard fonksiyonları filtresiz ve ay ortası aralıkta raporlama nesneleriyle tutarlı (Aşama 7–8) |

`info` düzeyi: açıklama amaçlı, `meta.etl_run_checks.details` içinde saklanır.

| Rapor | İçerik |
|---|---|
| `010_rejections_by_reason` | Tablo ve nedene göre ret/tekrar sayıları |
| `020_out_of_scope_orders` | Satış kapsamı dışındaki durumlar |
| `030_payment_vs_items_difference` | Ödeme ile kalem + kargo farkları (zorla eşitlenmez) |
| `040_duplicates_and_conflicts` | Tekrar ve çelişki sayıları |
| `050_category_translation_policy` | Kategori politikası sonucu |

## Gerçek veri ve test verisi

| | Gerçek | Test |
|---|---|---|
| Dosyalar | `data/raw/` (git dışında) | `tests/fixtures/olist_sample/` (temiz), `tests/fixtures/olist_quality_sample/` (hatalı senaryolar); tamamı sentetik |
| Veritabanı | `olist` | `olist_test` ve testlerde geçici `olist_*_test` veritabanları |
