# Doğrulama Raporu (Aşama 8, 2026-10-25; Aşama 9 eki aşağıda)

> **Sonuçların zamanı:** A–F bölümleri Aşama 8'e aittir ve `sql/200` öncesindeki kodla çalıştırıldı (o andaki pytest sayısı 85). Aşama 9 öncesi düzeltmeden sonra 87 ve 89 test raporlandı (`docs/project_state.md`). Aşama 9'da yeniden çalıştırılanlar yalnızca **G** bölümündedir; diğer satırlar yeniden çalıştırılmış gibi okunmamalıdır.

Projenin kodu doğru varsayılmadan incelendi. Bulunan sorunlar düzeltildi ve kontroller düzeltmelerden **sonra** yeniden çalıştırıldı. Her satırdaki sonucun ham kaynağı belirtilmiştir.

**Özet:**

- Çalıştırılabilen kritik kontrollerin tamamı geçti.
- Denetimde 1 gerçek hata bulundu ve düzeltildi: dashboard aylık serisinin tarih kapsamı (K-11).
- 2 çalıştırma/belge sorunu düzeltildi (README kurulum adımları; Docker ekran görüntüsü yolu).
- Çalıştırılamayan veya kapsam dışı kalan kontroller "Çalıştırılamayan / yapılmayan kontroller" bölümünde listelenmiştir. Bu yüzden proje **"bütünüyle doğrulanmış" ilan edilmemektedir**; kalan eksiklerin etkisi aşağıda açıklanmıştır.

## Yeniden üretme

```powershell
.\scripts\validate-clean-install.ps1           # ayrı Compose projesi + ayrı volume; ana veriye dokunmaz
.\scripts\test.ps1                              # sentetik veri, olist_test
.\scripts\etl.ps1 verify                        # ana veritabanında sql/tests
.\scripts\verify-dashboard.ps1                  # ana veritabanında dashboard KPI = doğrudan SQL
.\scripts\screenshots.ps1 -LocalChrome          # tarayıcıda görsel + etkileşim (kurulu Chrome)
.\scripts\screenshots.ps1 -OutDir docs\validation\screenshots_docker   # aynı kontroller, Docker imajı
```

## Kullanılan veri

| Etiket | Veri | Nerede |
|---|---|---|
| **GERÇEK-TEMİZ** | Gerçek Olist CSV'leri (`data/raw`), **ayrı** `olist-validation` Compose projesinde, **boş** volume'a sıfırdan yüklendi. Veritabanı adı `.env`'deki `olist`'tir, ama kendi ayrı PostgreSQL kümesinde. Sonunda yalnızca bu proje ve volume'u silindi. | `docs/validation/*.json` |
| **GERÇEK-ANA** | Kullanıcının mevcut `olist` veritabanı (silinmedi, yeniden yüklenmedi); yalnızca migration `190` uygulandı | çıktılar aşağıda |
| **SENTETİK** | `tests/fixtures/*` (3 küçük set; beklenen sonuçlar elle hesaplanmış), ayrı `olist_test` ve geçici `olist_*_test` veritabanları | `tests/` |

## Bulunan ve düzeltilen sorunlar

| # | Sorun | Nasıl bulundu | Etki | Düzeltme | Doğrulama |
|---|---|---|---|---|---|
| H-1 | `reporting.fn_monthly_sales` aylık tutarları tarih filtresi **olmadan** tam aylar üzerinden topluyordu. | Gerçek veride KPI ile aylık seri toplamı karşılaştırıldı: 15.01–10.03.2018 aralığında KPI 1.657.285,69 BRL / 12.891 sipariş, grafik toplamı 2.704.438,38 / 20.627. | Ay ortasında başlayan/biten aralıklarda dashboard grafiği seçilmeyen günleri gösteriyor, KPI'lar ile tutmuyordu ("KPI ve grafik aynı kapsam" kuralı ihlali). Tam ay aralıklarında sorun yoktu; bu yüzden önceki testler (tam aylar) yakalamamıştı. | `sql/190_report_monthly_sales_date_scope_fix.sql`: gösterilen değerler seçili aralıkla; büyüme yalnızca tam aylarda, tam ay değerlerinden (`partial_month` durumu). | K-11, K-23; yeni test `test_monthly_series_uses_same_date_scope_as_kpis`; `090` kontrolüne kalıcı değişmez eklendi. |
| H-2 | README "İlk kurulum" adımlarında veri indirme ve dashboard adımı yoktu. | README'nin sıfırdan okunması. | Talimatı izleyen biri ETL'de "Eksik kaynak dosyalar" hatası alırdı. | README güncellendi. Görsel araç için isteğe bağlı gereksinimler de yazıldı. | K-30 (belge incelemesi) |
| H-3 | `scripts/screenshots.ps1` Docker yolu hiç çalışmamıştı. İlk denemede `ModuleNotFoundError: playwright`. | İmaj indirildikten sonra çalıştırıldı. | Belgelenmiş bir komut çalışmıyordu. | Resmî imajda Python `playwright` paketi yok; aynı sürüm (1.64.1) konteynerde kuruluyor; imaj digest ile sabitlendi. | K-29 |

Not: Aşama 7'de Playwright imajının indirme görevi "durmuş" diye kaydedilmişti. Bu yanlıştı: görev ~42 dakikada (2.516 s) başarıyla bitti. Aşama 7'deki görsel kontroller yine de kurulu Chrome ile gerçekten yapılmıştı.

## Kontroller

Durum değerleri: **geçti** / **başarısız** / **çalıştırılamadı**.

### A. Temiz kurulum akışı (GERÇEK-TEMİZ)

Kaynak: `docs/validation/clean_install_steps.json`; komut `.\scripts\validate-clean-install.ps1`.

| # | Kontrol | Amaç | Beklenen | Gerçek | Durum |
|---|---|---|---|---|---|
| K-1 | Önceki doğrulama projesini temizleme, imaj derleme, boş volume ile `db` | Ana veriye dokunmadan sıfırdan başlangıç | çıkış 0; db healthy | 0 / 0 / 0; healthy | geçti |
| K-2 | Şema + ilk ETL (`python -m etl run`) | Boş veritabanında migration'lar (010–190) ve ilk yükleme | succeeded, tüm kalite kontrolleri geçer | çıkış 0; run `3b32aaa1…` 76,216 s | geçti |
| K-3 | İkinci ETL | Tam yenileme tekrarında başarı | succeeded | çıkış 0; run `8f3aa77f…` 102,860 s | geçti |
| K-4 | İkinci yüklemenin aynı sonucu vermesi | Tekrar yüklemede çoğalma / değişiklik yok | 11 nesnenin satır sayısı ve içerik MD5'i aynı | aynı (`snapshot_first_load.json` = `snapshot_second_load.json`) | geçti |
| K-5 | `setup-dashboard-role` ×2 | Rol kurulumu tekrarlanabilir | 1. "oluşturuldu", 2. "güncellendi", çıkış 0 | aynı | geçti |
| K-6 | pytest (temiz küme) | Testlerin ayrı ve boş kümede de geçmesi | hepsi geçer | **85 passed** | geçti |
| K-7 | Dashboard başlatma (port 8502) | Uygulama açılır | healthy | healthy | geçti |
| K-8 | Doğrulama projesinin silinmesi | Yalnızca kendi kaynaklarını siler | `olist-validation_pgdata` ve ağ silinir | silindi; ana volume `olist-sales-intelligence_pgdata` duruyor | geçti |

### B. Doğruluk değişmezleri (GERÇEK-TEMİZ)

Kaynak: `docs/validation/invariants.json`; `python -m validation.checks invariants`. Beklenen değerler reporting nesnelerinden **bağımsız**, doğrudan dw/staging tablolarından hesaplandı.

| # | Kontrol | Beklenen | Gerçek | Durum |
|---|---|---|---|---|
| K-9 | Kalem/ödeme/yorum join'leri tutarı çoğaltmıyor | staging'den 13.221.498,11 | `v_sales_kpis` 13.221.498,11. Bilgi: doğrudan join edilseydi 13.757.136,52 olurdu | geçti |
| K-10 | Ödeme tutarı ürün satış tutarıyla karışmıyor | ürün 13.221.498,11 · ödeme 15.422.461,77 | aynı | geçti |
| K-11 | Dashboard aylık seri = KPI = doğrudan SQL (15.01–10.03.2018) | 1.657.285,69 BRL / 12.891 | KPI ve aylık toplam 1.657.285,69 / 12.891 | geçti (H-1 düzeltmesinden sonra) |
| K-12 | Sipariş ≠ kalem | sipariş 96.478 · kalem 110.197 | aynı | geçti |
| K-13 | Müşteri = `customer_unique_id` | 93.358 (`customer_id` ile 96.478 olurdu) | 93.358 | geçti |
| K-14 | Teslimat paydaları (ham zamanlardan) | ort. 12,56 gün; payda 96.470; geç 6.534; oran 0,0677; ölçülemeyen 8 | aynı | geçti |
| K-15 | RFM gözlem tarihinden sonraki satın almalar dışlanıyor (as_of 2018-01-01) | 42.395 kişi; frequency toplamı 43.695 (farklı sipariş); son satın alma ≤ 2017-12-31; monetary 6.003.372,99 | aynı | geçti |
| K-16 | Tekrar satın alma: `customer_unique_id`, ≥ 2 farklı sipariş | 93.358 / 2.801 | aynı | geçti |
| K-17 | Raporlar arasında tek sipariş durumu kuralı | yalnızca `= 'delivered'` | katalog taraması: 5 view'de yalnızca `= 'delivered'`; başka literal yok | geçti |

### C. Rutinler ve başarısızlık (GERÇEK-TEMİZ)

Kaynak: `docs/validation/routines.json`, `controlled_failure.json`.

| # | Kontrol | Amaç | Beklenen | Gerçek | Durum |
|---|---|---|---|---|---|
| K-18 | `sp_refresh_reports` ×2 + `sp_load_monthly_summary(2017)` ×2 | Tekrar çağrıda çoğalma yok | `monthly_summary` 27 satır (= dim_date ay sayısı); içerik MD5 değişmez | 27; MD5 `2d653b47…` önce = sonra | geçti |
| K-19 | Yenileme kayıtları | Her çağrı kayıt bırakır | +2 succeeded | +2 | geçti |
| K-20 | MV'ler dolu | CONCURRENTLY önkoşulu | 2/2 populated | 2/2 | geçti |
| K-21 | Başarısız yüklemede kısmi veri yok | Gerçek veriyle tam yeniden yükleme, son kontrolde bilerek düşer | istisna; 11 nesnenin özeti değişmez; run `failed` | istisna; özet aynı; `failed` | geçti |

### D. Ana veritabanı (GERÇEK-ANA)

| # | Kontrol | Komut | Beklenen | Gerçek | Durum |
|---|---|---|---|---|---|
| K-22 | Düzeltmenin uygulanması | `.\scripts\etl.ps1 migrate` | `190` uygulanır | "Uygulandı: 190_…" | geçti |
| K-23 | Kalite kontrolleri (yeni ay ortası değişmezleri dahil) | `.\scripts\etl.ps1 verify` | 9/9 | 9 geçti / 0 başarısız | geçti |
| K-24 | Dashboard KPI = doğrudan SQL (7 örnek filtre) | `.\scripts\verify-dashboard.ps1` | 7/7 eşleşir | 7 OK / 0 FARK (`docs/dashboard_verification.json`) | geçti |
| K-25 | Aynı KPI kontrolü, temiz kurulumda | adım 15 | 7/7 | `all_match: true` (`docs/validation/dashboard_verification.json`) | geçti |

### E. Sentetik veri testleri (SENTETİK)

| # | Kontrol | Komut | Beklenen | Gerçek | Durum |
|---|---|---|---|---|---|
| K-26 | Tüm pytest | `.\scripts\test.ps1` (ana proje) | hepsi geçer | **85 passed** | geçti |

Kapsam: elle hesaplanmış KPI/RFM/aylık/kategori/teslimat değerleri; çoğalmama (3 kalem × 2 ödeme × 2 yorum); ret/tekrar/çelişkili anahtar; ikinci yükleme; COPY hatası ve kalite kontrolü hatasında geri alma; okuyucu yalıtımı; rutin tekrar çağrısı; işlem içi `CALL` reddi; kilit zaman aşımında hata kaydının kalıcılığı; dashboard KPI = doğrudan SQL; dashboard rol yetkileri; parametreli sorgu; boş sonuç / yüklenmemiş veri / bağlantı hatası / beklenmeyen hata mesajları.

### F. Güvenlik, sırlar, bağımlılıklar

| # | Kontrol | Yöntem | Beklenen | Gerçek | Durum |
|---|---|---|---|---|---|
| K-27 | Parametreli sorgular | Kod incelemesi (`dashboard/data.py`, `dashboard/verify.py`, `etl/*`) ve test | Kullanıcı girdisi SQL metnine eklenmez | Dashboard tüm girdileri bağlama parametresi olarak geçiyor. f-string kullanılan yerler yalnızca sabit tablo adları veya doğrulanmış kimlikler (`sql_runner` regex, `load_staging` başlığı beklenen kolon kümesiyle kısıtlı, `psycopg2.sql.Identifier`). Enjeksiyon testi tabloya dokunmadı. | geçti |
| K-28 | Dashboard yetkileri | `test_dashboard_role_can_read_reporting_only` (K-26 içinde) + K-5 | dw/meta/staging ve rutinler 42501; salt okunur oturum; süper kullanıcı değil | aynı | geçti |
| K-29 | Görsel ve etkileşim kontrolü | `screenshots.ps1 -LocalChrome` (8502, temiz kurulum) ve Docker yolu (8501, ana) | 13 görüntüde taşma ve hata yok; 6 etkileşimde KPI ve grafik değişir; boş sonuç mesajı | iki yolda da 13/13 temiz, 6/6 geçti (Chrome 156.0.8078.47 / imaj Chromium 156.0.8078.4); Docker yolu H-3 düzeltmesinden sonra | geçti |
| K-30 | Sırlar Git dışında | `git check-ignore`; commit'e alınacak 253 dosyada `.env` parola değerlerinin aranması (değerler yazdırılmadan) | `.env`, `data/raw/*.csv`, `tools/.venv` hariç; sızıntı yok | hariç; 2 parola anahtarı için sızıntı yok | geçti |
| K-31 | Bağımlılıklar | Kod incelemesi | Sürümler sabit, imajlar digest'li | PostgreSQL 16.15 ve Python 3.11.17 digest'li; `requirements.txt` tam kilit; imaj derlemesinde `pip check`; Playwright 1.64.0/1.64.1 sabit (yalnızca doğrulama araçları); README talimatları güncellendi (H-2) | geçti |

### G. Aşama 9: yedekleme, geri yükleme ve teslim kontrolleri (2026-10-25, bu aşamada çalıştırıldı)

Veri: GERÇEK-ANA (yedeğin kaynağı; değiştirilmedi) ve bu yedekten oluşturulan ayrı veritabanları. Ham çıktılar: `docs/validation/backup_restore_check.json`, `docs/validation/backup_restore_fresh_cluster.json`, `docs/screenshots/report.json`, `docs/screenshots/interactions.json`.

| # | Kontrol | Komut | Beklenen | Gerçek | Durum |
|---|---|---|---|---|---|
| K-32 | pytest, güncel kod ve yeniden derlenmiş imaj | `docker compose run --rm tests pytest -q` (`test.ps1` ile aynı servis) | hepsi geçer | **89 passed** (15,8 s; ~14:51 UTC) | geçti |
| K-33 | Yalnızca Genel Bakış görüntülerinin yenilenmesi | `.\scripts\screenshots.ps1 -LocalChrome -OverviewOnly` | 6 görüntüde taşma ve hata yok; filtrelerde KPI ve grafik değişir | 6/6 temiz; RJ, `health_beauty`, 2018-Q1 değerleri Aşama 7 kaydıyla aynı. İlk deneme otomasyon hatasıyla (`hover` zaman aşımı) düştü, düzeltilip tekrarlandı | geçti |
| K-34 | Büyüme oranının tam önceki aydan hesaplanması (tarayıcıda) | aynı komut, tarih 10.06–29.08.2018 | Çubuklar 593.244,06 / 867.953,46 / 838.576,64; toplam = KPI 2.299.774,16; Temmuz "tam aylar %1,4" | aynı; bilgi kutusu "Önceki aya göre (tam aylar): %1,4"; açıklama metni görünüyor | geçti |
| K-35 | Yedek alma | `.\scripts\backup.ps1` | Dosya oluşur, arşiv okunur, konteyner ve Windows SHA-256'sı aynı | `olist_20261025_174001.dump`, 74.432.354 bayt, 201 girdi, SHA-256 aynı; 9,5 s | geçti |
| K-36 | Ayrı veritabanına geri yükleme ve karşılaştırma | `restore.ps1` → `verify-restore.ps1` (`olist_restore_test`) | İş verisi, nesneler, yetkiler aynı; meta ayrı değerlendirilir; hedefte 9/9 kontrol | 26 tablo/MV satır sayısı + içerik MD5 aynı; finansal toplamlar aynı; meta aynı; 9/9 geçti; ardından `-DropAfter` ile silindi | geçti |
| K-37 | Var olan ama boş hedefe geri yükleme (felaket kurtarma yolu) | `createdb olist_restore_empty_test` → `restore.ps1` → `verify-restore.ps1` | aynı | aynı; deneme veritabanı elle silindi (`-DropAfter` ad koruması `_restore_test` ile bitmediği için reddetti; beklenen davranış) | geçti |
| K-38 | Yeni ve boş kümeye geri yükleme, rollerin yeniden kurulması | Ayrı Compose projesi `olist-restore-check` (`COMPOSE_PROJECT_NAME`, port 8503) | Rol yokken geri yükleme çalışır; `setup-dashboard-role` sonrası dashboard çalışır | Önce yalnızca `olist` rolü vardı; geri yükleme `olist_reporting_reader`'ı oluşturdu; 9/9 kontrol; `migrate` yeni dosya yok; dashboard healthy; `dashboard.verify` 7/7 `all_match: true`; içerik ana veritabanıyla aynı. Proje ve volume'u silindi, ana volume duruyor | geçti |
| K-39 | Koruma: dolu hedefe yazmama | `restore.ps1 -TargetDatabase olist` ve `olist_test` | reddedilir, hiçbir şey değişmez | ikisi de "boş değil" hatasıyla reddedildi | geçti |
| K-40 | Koruma: bozulmuş/değişmiş yedek | yanlış `.sha256` ile kopya dosya | reddedilir | "SHA-256 eşleşmiyor" hatasıyla reddedildi; deneme dosyaları silindi | geçti |
| K-41 | Git'e girecek dosyalarda sır ve veri yok | `git ls-files --others --exclude-standard`; `.env` parola değerleri yazdırılmadan arandı | `.env`, yedek, ham CSV, `tools/.venv` yok | 301 dosya; 0 eşleşme; `.env`, `backups/*`, `data/raw/*.csv`, `tools/.venv` `git check-ignore` ile hariç | geçti |
| K-42 | Belgelerde kontrol karakteri ve bağlantılar | betikle tarama (`docs/project_state.md`, Aşama 9) | bozuk karakter yok; göreli bağlantılar var olan dosyalara gider | bkz. `docs/project_state.md` Aşama 9 | geçti |

| K-43 | Aylık grafikte ay etiketlerinin çakışmaması (teslim sonrası düzeltme) | `.\scripts\screenshots.ps1 -LocalChrome -OverviewOnly`; `x_tick_labels` ölçümü; eski davranışla negatif kontrol | 390 ve 1440 px'te çakışan komşu çift 0; çubuklar ve toplamlar değişmez | 1440 px: 24 etiket, 0 çakışma; 390 px: 12 etiket, 0 çakışma (öncesi 23). 24 çubuk, toplam 13.221.498,11; Temmuz %1,4. Görüntüler incelendi. pytest 89 passed | geçti |

Aşama 9'da bulunan ve düzeltilenler:

- `verify-restore.ps1` ilk sürümünde kalite kontrol satırlarını JSON'a bozuk Türkçe karakterle yazdı ("ğ" yerine Unicode yerine koyma karakteri). Satırlar artık günlük düzeyi ve dosya adından dil bağımsız yazılıyor; yeniden çalıştırıldı.
- `dashboard.ps1`, port ortam değişkeniyle değiştirildiğinde ekrana yine `.env`'deki portu yazıyordu (K-38'de görüldü); artık Compose ile aynı önceliği izliyor.
- Kanıt JSON'unu üreten geçici bir Python komutu ters eğik çizgi kaçışı yüzünden sözdizimi hatası verdi; dosya yazılmadan durdu. Yollar düz eğik çizgiyle yazıldı.

Aşama 9'da yeniden çalıştırılmayanlar: temiz kurulum betiği, `etl.ps1 verify` (ana veritabanı ve SQL değişmedi; aynı kontroller K-36/K-38'de geri yüklenen kopyalarda çalıştı), `verify-dashboard.ps1` (ana; K-38'de geri yüklenen kümede çalıştı), performans deneyleri, Docker ekran görüntüsü yolu, Genel Bakış dışındaki görüntüler.

## Testlerin niteliği

- **Bağımsız doğruluk koşulu kontrol edenler:**
  - Elle hesaplanmış sabit değerler (`test_reporting`, `test_dw_model`, `test_pipeline`, `test_dashboard`).
  - Reporting nesnelerini kullanmayan doğrudan SQL: `test_dashboard`, `dashboard/verify.py`, `validation/checks.py`.
  - Staging'den bağımsız toplam: `sql/tests/030`, `070`.
  - Gerçek bir başarısızlık oluşturup sonucunu ölçenler (COPY hatası, kilit zaman aşımı, kontrollü kalite hatası).
- **Yalnızca iç tutarlılık ölçenler:** `sql/tests/080` ve `090` analizleri `v_sales_kpis` ile karşılaştırır. `v_sales_kpis` yanlış olsaydı birlikte yanılırlardı. Bu risk K-9..K-16'daki bağımsız hesaplarla ve sentetik verideki elle hesaplanmış değerlerle karşılanıyor.
- **Zayıf testler:**
  - `test_profile` rapor metninde satır arar.
  - `test_schema_fresh_db` nesne listesini karşılaştırır; yeni nesne eklendikçe güncellenmesi gerekir (Aşama 4–7'de 4 kez yapıldı).
  - `test_perf_harness` yalnızca yardımcı fonksiyonları sınar.
- **Kaçırılan hata:** H-1, testlerin seçtiği senaryoların (tam aylar) gerçek kullanım aralığını kapsamamasından kaçtı. Artık hem sentetik testte hem `090` içinde ay ortası aralık var.

## Çalıştırılamayan / yapılmayan kontroller

| Kontrol | Durum | Neden | Etki |
|---|---|---|---|
| README "İlk kurulum"un **elle**, veri indirme dahil sıfırdan izlenmesi | çalıştırılamadı | Temiz kurulum betiği mevcut `data/raw` dosyalarını kullandı; Kaggle'dan yeniden indirme yapılmadı | Veri indirme adımı Aşama 3'te (2026-10-24) bir kez çalıştı, sonrasında yeniden sınanmadı. Kaggle API'si değişirse README güncellenmelidir. |
| Firefox / Safari / tablet genişliği, ekran okuyucu, klavye erişimi | yapılmadı | Kapsam ve araç | Chromium dışı tarayıcılarda ve erişilebilirlikte sorun olabilir. |
| Soğuk önbellek, eşzamanlı kullanıcı yükü | yapılmadı | Kapsam | Performans rakamları yalnızca sıcak önbellek, tek kullanıcı içindir. |
| Yedekleme / geri yükleme | ~~yapılmadı~~ **Aşama 9'da yapıldı** | Aşama 8'de projede tanımlı değildi | G bölümü: K-35..K-40 |
| Kaynak verinin dışarıda doğrulanması (para birimi BRL, saat dilimi, "her kalem = 1 adet") | çalıştırılamadı | Kaynak belgelerde belirtilmiyor | Metrik adları ve açıklamaları bu varsayımları belirtiyor (`docs/metric_definitions.md`). |

## Kalan sorunlar ve etkileri

| Sorun | Etki | Öneri |
|---|---|---|
| ~~`reporting.v_monthly_sales_growth` ve `reporting.monthly_summary`, tarih boyutu tahmini teslim tarihleri nedeniyle 2018-09..11'i 0 satışla içeriyor.~~ | **Giderildi (Aşama 9 öncesi, `sql/200`).** Aylık raporlar satış gözlem aralığıyla sınırlandı; gözlem dışı aylar `v_sales_observation_months` içinde ayrıca işaretli. Sonuçlar: `docs/validation/main_invariants_observation_window.json`. | — |
| Satış kapsamı kuralı (`= 'delivered'`) 5 view'de ayrı ayrı yazılı. | Şu an tutarlı (K-17), ama ileride bir view'de değiştirilirse ayrışabilir. | K-17 taraması `validation/checks.py` ile tekrarlanabilir; istenirse tek bir view'den türetilecek biçimde sadeleştirilebilir. |
| `fact_orders_status_idx` ve `dim_customer_unique_id_idx` için karar verilmedi. | Her ETL'de küçük yazma maliyeti (`docs/performance.md`, D1/F2). | Kullanım kaynağı belirlenince değerlendirilmeli. |
| Sipariş durumu kaynağın son anlık görüntüsü. | Geçmiş bir `as_of` için RFM, o tarihteki durumu değil bugünkü durumu kullanır. | Belgelendi (`docs/reporting.md`); kaynakta tarihsel durum yok. |
| Docker ekran görüntüsü yolu her çalıştırmada PyPI'dan paket indirir. | İnternet gerekir; ağ yavaşsa uzun sürer. | Kalıcı ihtiyaç olursa küçük bir türetilmiş imaj sabitlenebilir. |
| Git deposunda commit yok. | Değişiklik geçmişi yok; geri dönüş noktası yok. | Kullanıcı kararı. |
| Yedekler elle alınır ve ana veritabanıyla aynı diskte durur. | Disk arızasında yedek de kaybolabilir. | Gerekirse `backups\` başka bir diske elle kopyalanmalı. |
| ~~Dar ekranda aylık grafiğin 24 ay etiketi üst üste biniyor (Aşama 9'da görüldü).~~ | **Giderildi (K-43).** 390 px'te 12 dik etiket, 1440 px'te 24 dik etiket; ölçülen çakışma 0. | Ara genişlikler (ör. 768 px) ölçülmedi. |
