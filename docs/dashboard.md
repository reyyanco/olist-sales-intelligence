# Dashboard: Olist Sales Intelligence

Streamlit + Plotly; yalnızca bu bilgisayardan erişilir: http://127.0.0.1:8501

```powershell
.\scripts\new-env.ps1          # .env'de eksik anahtarlar varsa ekler (dashboard parolası rastgele)
.\scripts\dashboard.ps1        # şemayı uygular, salt okunur rolü hazırlar, dashboard'u başlatır
.\scripts\verify-dashboard.ps1 # gerçek veride örnek filtrelerdeki KPI'ları doğrudan SQL ile karşılaştırır
.\scripts\screenshots.ps1 -LocalChrome  # çalışan uygulamadan ekran görüntüleri + arayüz etkileşim kontrolleri (kurulu Chrome)
```

## Mimari

| Katman | Dosya | Görev |
|---|---|---|
| İş mantığı | `sql/160_report_dashboard_functions.sql` | Parametreli `reporting.fn_*` fonksiyonları ve dashboard view'leri. Metrikler burada hesaplanır. |
| Yetki | `sql/180_dashboard_reader_role.sql`, `etl/dashboard_role.py` | Salt okunur rol |
| Veri erişimi | `dashboard/data.py` | Yalnızca reporting fonksiyonlarını ve view'lerini parametreli sorgularla okur; önbellek; hata eşleme |
| Görünüm | `dashboard/ui.py`, `dashboard/filters.py`, `dashboard/views.py`, `dashboard/app.py`, `dashboard/page_*.py` | Biçimlendirme, filtreler, sayfalar. Metrik yeniden hesaplanmaz. |
| Tutarlılık | `sql/tests/090_dashboard_functions_consistent.sql` | Her ETL'de, filtresiz ve tam kapsamda fonksiyonlar `v_sales_kpis`, `mv_category_sales`, `v_monthly_sales_growth` ve `v_repeat_purchase` ile aynı olmalı; değilse yükleme geri alınır |

## Sayfalar ve veri kaynakları

| Sayfa | İçerik | Fonksiyon | Uygulanan filtreler |
|---|---|---|---|
| Genel Bakış | Ürün satış tutarı, sipariş sayısı, müşteri sayısı, ortalama sepet; aylık trend | `fn_overview_kpis`, `fn_monthly_sales` | tarih, eyalet, kategori |
| Kategori Analizi | Kategori satışları, sıra, pay, kümülatif pay (Pareto) | `fn_category_sales` | tarih, eyalet |
| Müşteri Analizi | Tekrar satın alma; RFM segmentleri | `fn_repeat_purchase`, `fn_rfm_segments` (`fn_customer_rfm`) | tarih |
| Teslimat Performansı | Ortalama teslimat süresi, geç teslimat oranı, bölge (IBGE) ve eyalet kırılımı, aylık eğilim | `fn_delivery_by_region`, `fn_delivery_monthly` | tarih, eyalet |

Her sayfanın başında "Filtre kapsamı" satırı, o sayfada hangi filtrenin uygulandığını ve hangisinin uygulanmadığını yazar.

## Filtre kuralları

- **Tarih:** satın alma günü, iki uç dahil.
  - Varsayılan aralık, teslim edilmiş siparişlerin ilk ve son satın alma günüdür (`reporting.v_data_coverage`; gerçek veride 15.09.2016 – 29.08.2018).
  - Seçim bu kapsamla sınırlıdır.
  - "Tüm veri kapsamı" düğmesi varsayılana döner.
- **Eyalet:** siparişi veren müşterinin eyaleti.
- **Kategori:** kalem düzeyinde uygulanır.
  - Tutar, seçili kategorilerdeki kalemlerin fiyat toplamıdır.
  - Sipariş sayısı, seçili kategoride en az bir kalemi olan **farklı** sipariş sayısıdır (`count(DISTINCT order_id)`). Birden çok seçili kategoride kalemi olan sipariş bir kez sayılır.
  - Ortalama sepet = bu tutar / bu sipariş sayısı.
- **Müşteri Analizi:**
  - Tekrar satın alma, seçili aralıktaki siparişlerle hesaplanır.
  - RFM gözlem tarihi = seçili bitiş günü + 1; o güne kadarki tüm geçmiş kullanılır. Bu nedenle RFM için başlangıç günü uygulanmaz.
  - Eyalet ve kategori bu sayfada uygulanmaz, çünkü bir kişinin birden çok eyalette veya kategoride siparişi olabilir.
- **KPI ve grafikler:** Aynı sayfadaki KPI kartları ve grafikler aynı `Filters` nesnesiyle aynı fonksiyonlardan beslenir.

## Aylık grafikler

- **Gelecek aylar yok:** Aylar veri kapsamıyla sınırlıdır (`fn_monthly_sales`). Tarih boyutu tahmini teslim tarihleri nedeniyle 2018-11'e kadar uzasa da 2018-09..11 grafikte **gösterilmez**; bu aylar gerçek sıfır satış dönemleri gibi görünmez.
- **Gerçek sıfır aylar:** Kapsam içinde satışı olmayan aylar 0 olarak gösterilir ve altta açıklanır. Gerçek veride 2016-11'de teslim edilmiş sipariş yoktur.
- **Kısmi aylar:** Seçili aralık veya veri kapsamı ayın tamamını içermiyorsa ay açık turkuaz çubukla gösterilir (`is_partial_month`).
- **Tutarlar:** Aylık çubuklar yalnızca seçili tarih aralığındaki günleri içerir; çubukların toplamı KPI kartıyla aynıdır (Aşama 8'de düzeltildi, migration `190`).
- **Büyüme:** Önceki aya göre büyüme veritabanında, yalnızca **tam aylar** için ve tam ay değerlerinden hesaplanır. Kısmi aylarda "hesaplanmaz (kısmi ay)" gösterilir. Önceki ay veri kapsamı tarafından kesiliyorsa (gerçek veride 2016-10) "hesaplanmaz (önceki ay kısmi)" gösterilir (migration `200`).
  - Önceki ay yalnızca tarih filtresiyle kesiliyorsa oran, o ayın **tam** değerinden hesaplanır.
  - Bilgi kutusu bu yüzden "Önceki aya göre (tam aylar)" der. Grafiğin altındaki açıklama, oranın kısmi çubukla karşılaştırılamayacağını belirtir (iki tür kısmi ayın tablosu: `docs/reporting.md`, bölüm 1).
  - Negatif oranlar Türkçe biçimde yazılır: `-%75,0`. Önceki ay 0 ise "hesaplanamaz (önceki ay 0)" gösterilir; sıfıra bölme yapılmaz.

## Görsel kurallar

| Unsur | Kural |
|---|---|
| Tema | Açık arka plan `#F7FAFC`, koyu lacivert metin `#0B1F3A`, turkuaz vurgu `#0E9AA7` (`compose.yaml` → `STREAMLIT_THEME_*`) |
| Renk anlamları (tüm sayfalarda) | turkuaz = ürün satış tutarı · lacivert = sipariş ve müşteri sayıları · turuncu `#E07A1F` = geç teslimat / risk · açık turkuaz = kısmi ay |
| Sayılar | Türkçe biçim (binlik nokta, ondalık virgül); para `13.221.498,11 BRL`; oran `%6,77` |
| Para birimi | Kaynakta belirtilmemiştir; Brezilya verisi olduğu için BRL varsayılır. Bu not arayüzde de yazar. |
| Dar ekran | Streamlit kolonları dar ekranda alt alta dizilir; kategori ve bölge grafikleri yatay çubuktur (adlar okunur). Tablolar kendi içinde yatay kaydırılır. Görsel kontrol sonucu aşağıda. |
| Adres | Genel Bakış kök adreste (`/`); diğerleri `/kategori`, `/musteri`, `/teslimat` |

## Güvenlik ve yetkiler

- **Rol:** Dashboard yönetici hesabıyla değil, `DASHBOARD_DB_USER` (varsayılan `olist_dashboard`) ile bağlanır.
  - Bu rol yalnızca `olist_reporting_reader` üyesidir: `reporting` şemasında `USAGE`, dashboard view'lerinde ve MV'lerde `SELECT`, dashboard fonksiyonlarında `EXECUTE`.
  - `dw`, `staging` ve `meta` şemalarına erişimi yoktur.
  - `sp_refresh_reports`, `sp_load_monthly_summary` ve `refresh_report_objects` çalıştıramaz; PUBLIC'in varsayılan EXECUTE yetkisi reporting rutinlerinden kaldırıldı.
  - Rol `NOSUPERUSER NOCREATEDB NOCREATEROLE`'dür; oturumları `default_transaction_read_only = on` ve `statement_timeout = 30s` ile açılır.
  - Bu sınırların her biri testle doğrulandı (`tests/test_dashboard.py`).
- **Parola:** Parola koda yazılmaz; `.env`'den okunur. `setup-dashboard-role` parolayı `psycopg2.sql.Literal` ile alıntılayarak verir ve hiçbir çıktıya yazmaz.
- **Parametreli sorgular:** Kullanıcı girdileri her zaman bağlama parametresidir (`dashboard/data.py`). SQL enjeksiyonu denemesi testte sonuçsuz kaldı ve tabloyu etkilemedi.
- **Hata gösterimi:**
  - Ham hata çıktısı gösterilmez: `STREAMLIT_CLIENT_SHOW_ERROR_DETAILS=false`.
  - Veri hataları kullanıcıya anlaşılır mesajla gösterilir; teknik ayrıntı yalnızca sunucu günlüğüne yazılır.
  - Testte bağlantı hatasında parola, `Traceback` ve sürücü adı arayüzde görünmedi.

## Önbellek ve yenileme

| Konu | Davranış |
|---|---|
| Veri sorguları | `st.cache_data(ttl=600 s)`; önbellek anahtarı filtreler + son başarılı yüklemenin `run_id`'si |
| Tazelik bilgisi | `st.cache_data(ttl=60 s)` (`reporting.v_data_freshness`) |
| Yeni ETL | `run_id` değiştiği için en geç 60 s içinde yeni veri okunur; eski önbellek girdileri kullanılmaz |
| "Verileri yenile" düğmesi | Tüm önbelleği hemen temizler |
| Son başarılı yükleme | Kenar çubuğunda UTC olarak gösterilir |

## Durum mesajları

| Durum | Arayüz |
|---|---|
| Veritabanına bağlanılamıyor | "Veritabanına bağlanılamadı. …" (hata kutusu, teknik ayrıntı yok) |
| Raporlama nesneleri yok / yetki yok | Şemanın ve rolün hazırlanması için yönlendirme |
| Hiç başarılı yükleme yok veya satış verisi yok | "Henüz yüklenmiş satış verisi yok. Yükleme için: `.\scripts\etl.ps1`" |
| Filtre sonucu boş | "Seçilen filtrelerle sonuç bulunamadı. …" |
| Tarih aralığı yarım seçilmiş | "Tarih aralığı için başlangıç ve bitiş günlerini seçin." |

## Doğrulama

**Otomatik testler** (`tests/test_dashboard.py`, sentetik veri):

- Dört sayfanın hatasız çizilmesi.
- 4 filtre senaryosunda KPI'ların hem elle hesaplanan değerlerle hem de reporting fonksiyonlarını kullanmayan doğrudan SQL ile aynı olması.
- Varsayılan tarih aralığı.
- Aylık serinin veri kapsamında bitmesi ve kısmi ay işaretleri.
- Kategori filtresinde sipariş çoğalmaması.
- Boş sonuç, henüz yüklenmemiş veri ve bağlantı hatası durumları.
- Parametreli sorgu.
- Rol yetkileri.

**Gerçek veri** (`docs/dashboard_verification.json`): 7 örnek filtrede uygulamanın gösterdiği KPI'lar doğrudan SQL ile birebir eşleşti. Örnekler:

- Varsayılan kapsam.
- `health_beauty`.
- SP + RJ, 2018 ilk yarı.
- `bed_bath_table` + MG, 2017.
- İki kategori, 2018-03.
- Teslimat BA, 2017.
- Müşteri 2017.

## Performans

Dashboard sorgularının ölçümü ve indeks kararları `docs/performance.md`, D1 ve F2 bölümlerindedir.

- Tam kapsamda en yavaş çağrı `fn_rfm_segments` (~1,0 s); diğerleri 0,1–0,6 s.
- Sonuçlar 10 dakika önbellekte tutulur.
- Yeni indeks eklenmedi: dashboard'un kullandığı iki tarih indeksi zaten modelde var.

## Görsel kontrol (2026-10-25, gerçek veri, gerçek tarayıcı)

**Araç:**

- Playwright 1.64.0 (Python) ile bilgisayarda kurulu **Google Chrome 156.0.8078.47** kullanıldı; ayrı bir tarayıcı indirilmedi.
- Uygulama `http://127.0.0.1:8501`'de, salt okunur `olist_dashboard` rolüyle çalışıyordu.
- Komut: `.\scripts\screenshots.ps1 -LocalChrome`.
- Aşama 7'de Docker yolu çalıştırılmadı (imaj indirmesinin durduğu sanılmıştı; aslında 2.516 s sonra tamamlanmıştı).
- **Aşama 8:** Docker yolu çalıştırıldı ve düzeltildi.
  - Resmî imajda Python `playwright` paketi olmadığından aynı sürüm (1.64.1) konteynerde kuruluyor; imaj digest ile sabit.
  - Komut: `.\scripts\screenshots.ps1 -OutDir docs\validation\screenshots_docker`.
  - Sonuç: Chromium 156.0.8078.4 ile 13/13 görüntü taşmasız ve hatasız; 6/6 etkileşim geçti.

**Çıktılar** (`docs/screenshots/`):

- 14 PNG.
- `report.json`: her görüntü için yatay taşma, hata öğeleri, KPI metinleri, çizilmiş grafik verisi; Aşama 9'da yenilenen kayıtlarda `captured_at_utc`.
- `interactions.json`: etkileşim kontrolleri.

**Aşama 9 güncellemesi (2026-10-25, ~14:50 UTC):** İlk görüntüler 13:05 UTC'de, migration `200` ve büyüme açıklaması (`dashboard/views.py`, `GROWTH_NOTE`) eklenmeden önce alınmıştı. Bu değişikliklerden yalnızca Genel Bakış etkilendiği için yalnızca o sayfa yeniden alındı: `.\scripts\screenshots.ps1 -LocalChrome -OverviewOnly`.

| Görüntü | Durum |
|---|---|
| `desktop_genel-bakis.png`, `narrow_genel-bakis.png` | Yenilendi (varsayılan kapsam 15.09.2016–29.08.2018) |
| `filter_overview_state_RJ.png`, `filter_overview_category_health_beauty.png`, `filter_overview_dates_2018Q1.png` | Yenilendi; KPI ve çubuk toplamları ilk çekimle aynı |
| `filter_overview_dates_2018-06-10_2018-08-29_hover_july.png` | **Yeni.** Tarih 10.06–29.08.2018; fare Temmuz çubuğunda. Bilgi kutusu: "Önceki aya göre (tam aylar): %1,4". Çubuklar 593.244,06 / 867.953,46 / 838.576,64; toplam 2.299.774,16 BRL = KPI (`interactions.json`, `overview_growth_full_month_base`) |
| Kategori, Müşteri, Teslimat (masaüstü / dar), `filter_delivery_state_BA.png`, `empty_result_overview.png` | Yeniden alınmadı: değişen kod bu sayfaların görüntüsünü etkilemiyor (boş sonuç ekranında grafik ve açıklama yok). 13:05 UTC çekimleri geçerli |

İlk çalıştırmada Temmuz çubuğuna `hover()` Plotly'nin sürükleme katmanı yüzünden zaman aşımına uğradı (otomasyon hatası; rapor dosyaları yazılmadı). Fare çubuğun ortasına taşınacak şekilde düzeltilip yeniden çalıştırıldı.

**Düzeltme: dar ekranda aylık grafiğin ay etiketleri (2026-10-25, ~16:15 UTC).**

| | Önce | Sonra |
|---|---|---|
| Eksen | tarih ekseni, `dtick="M1"` (her ay zorunlu), -45° | kategori ekseni (`"%m.%Y"` metinleri), sabit `dtick` yok, `autotickangles=[0, 90]` (`dashboard/views.py`) |
| 1440 px | 24 etiket, çakışma 0 | 24 etiket (her ay), dik, çakışma 0, en küçük aralık 20,4 px |
| 390 px | 24 etiket, **23 komşu çift çakışıyor** | 12 etiket (iki ayda bir), dik, çakışma 0, en küçük aralık 4,9 px |
| Veri | 24 çubuk, toplam 13.221.498,11 | aynı: 24 çubuk, aynı toplam; her ayın bilgi kutusu duruyor |

- Kategori ekseninde Plotly etiket sıklığını tarayıcıdaki eksen genişliğine göre seçer; açı, etiketlerin sığdığı ilk değerdir (yatay, sığmazsa dik).
- 45° denendi ve bırakıldı: 390 px'te Plotly 12 etiketi 45° ile çizdi, ama ölçümde komşular 2,2 px çakıştı. Büyütülmüş görüntüde de birbirine değiyordu. Eğik paralel etiketlerin aralığını yazı yüksekliği belirlediği için dik yazı seçildi.
- `tickangle="auto"` değeri Plotly'de geçersiz çıktı ve sayfa hata verdi (hata ekranı görüntüleri hemen yeniden alındı).
- Ölçüm: `tools/screenshots.py` her grafik için `x_tick_labels` kaydeder (etiket sayısı, açı, çakışan komşu çiftleri, en küçük aralık). Döndürülmüş etiketlerde dik mesafe = yatay aralık × |sin açı| − yazı satırı yüksekliği. Bu, gerçek harf izinden daha katı bir ölçüttür.
- Negatif kontrol: Eski davranış (her ay etiketli) geçici olarak geri konup git dışı `tmp\` klasörüne ölçüldü: 390 px'te 23 çakışma, 1440 px'te 0. Sonuçlar ölçütün çakışmayı yakaladığını gösteriyor. Geçici değişiklik geri alındı, klasör silindi.
- Yeniden alınan görüntüler: Genel Bakış'ın 6 görüntüsü (`.\scripts\screenshots.ps1 -LocalChrome -OverviewOnly`). Diğer sayfalarda aylık grafik yok; Teslimat eğilim grafiği bu değişiklikten etkilenmedi ve yeniden alınmadı.

Docker yolundaki (`docs/validation/screenshots_docker/`) ve temiz kurulumdaki (`docs/validation/screenshots/`) görüntüler Aşama 8'e aittir ve büyüme açıklamasından öncedir; yeniden alınmadı.

### Sayfalar ve boyutlar

| Görüntü | Boyut | Yatay taşma | Hata öğesi | Grafik |
|---|---|---|---|---:|
| Genel Bakış / Kategori / Müşteri / Teslimat | masaüstü 1440 px | yok | 0 | 1 / 1 / 1 / 2 |
| Genel Bakış / Kategori / Müşteri / Teslimat | dar ekran 390 px | yok | 0 | 1 / 1 / 1 / 2 |

Görüntüler tek tek incelendi. Streamlit içeriği kendi kaydırma alanında gösterdiği için sayfanın tamamını görebilmek amacıyla pencere yüksekliği 2400 / 3200 px kullanıldı; genişlik ve dolayısıyla yerleşim değişmedi.

### Arayüz etkileşimleri

Tarayıcıda gerçek tıklama ve yazmayla yapıldı; `interactions.json`.

| Etkileşim | Sonuç |
|---|---|
| Eyalet = RJ (multiselect'e yazıp seçme) | KPI'lar ve grafik değişti; kapsam satırında "Eyalet: RJ". Çizilmiş aylık çubukların toplamı 1.759.651,13 = KPI ürün satış tutarı. Doğrudan SQL: 1.759.651,13 / 12.350 / 11.917 / 142,48 (eşleşti). |
| Kategori = health_beauty | Değişti; 1.233.131,72 BRL / 8.647 / 8.498 / 142,61 BRL (`dashboard_verification.json` ile aynı). Grafik toplamı = KPI. |
| Tarih 01.01.2018 – 31.03.2018 (gün/ay/yıl parçalarına yazma, takvimi kapatma) | Değişti; grafikte 3 ay; toplam 2.704.438,38 = KPI. Doğrudan SQL: 2.704.438,38 / 20.627 / 20.211 / 131,11 (eşleşti). |
| Kenar çubuğundan "Teslimat Performansı"na tıklama | Sayfa açıldı (`/teslimat`). |
| Teslimat, eyalet = BA | KPI ve grafikler değişti; 19,34 gün / %12,16 / 3.256 (eyalet tablosundaki BA satırıyla aynı). |
| Boş sonuç: AC + arts_and_craftmanship (SQL ile 0 sipariş olduğu önceden doğrulandı) | "Seçilen filtrelerle sonuç bulunamadı…" bilgisi; KPI, grafik ve hata yok. |

### Bulunan ve düzeltilen görsel / işlevsel sorunlar

| # | Sorun (görüntüde görüldü) | Neden | Düzeltme |
|---|---|---|---|
| 1 | Genel Bakış `/genel-bakis` adresinde "Page not found" iletişim kutusu; tıklamaları engelliyordu | Varsayılan sayfa her zaman `/`'de sunulur; `url_path` ölü bağlantı oluşturuyordu | Varsayılan sayfadan `url_path` kaldırıldı |
| 2 | Uygulama adı gezinme menüsünün altında | `st.navigation` menüyü kenar çubuğunun en üstüne koyar | `st.logo` ile SVG yazı logosu (`dashboard/assets/logo.svg`) |
| 3 | İkincil eksen başlıkları yanlış ("Kümülatif pay" ekseni "BRL", oran ekseni "Gün") | Ortak stil başlığı tüm y eksenlerine uyguluyordu | Başlık yalnız birincil eksene; ikincil eksenlere kendi başlıkları |
| 4 | Yüzde eksenleri "97,1%"; düzensiz değerler (%19,35 / %14,51) | Plotly sonek biçimi; bindirilmiş eksen birincil eksenin çizgilerine hizalanıyordu | Türkçe "%20" ön eki; aralık ve adım açıkça veriliyor (`ui.percent_axis`) |
| 5 | Teslimat eğiliminde 2016 sonu (1'er sipariş, ~54 gün, %91 geç) ekseni sıkıştırıyordu | Çok az ölçülen siparişi olan aylar | Bu grafikte < 30 ölçülen siparişli aylar gösterilmiyor ve altta listeleniyor (09.2016 (1), 12.2016 (1)); KPI ve tablolar değişmedi |
| 6 | Eksenlerde "5k", "1M" | Plotly SI kısaltması | Binlik ayraçlı tam sayı ("1.000.000") |
| 7 | RFM grafiğinde x ekseni başlığı yok | — | "Müşteri sayısı" |
| 8 | Dar ekranda kategori ve bölge adları üst üste / eğik, okunmuyor | Dikey çubuklarda 20 ad 390 px'e sığmıyor | Kategori ve bölge grafikleri yatay çubuk; kümülatif pay üst eksende çizgi |
| 9 | Dar ekranda kategori grafiğinin göstergesi eksen başlığıyla çakışıyordu | Gösterge alt kenarda | Gösterge kaldırıldı; seriler eksen başlıkları ve açıklama satırıyla adlandırılıyor |
| 10 | Düzeltme sırasında Teslimat sayfasında yakalanmamış `TypeError` (Streamlit ayrıntıyı gizledi ama İngilizce hata kutusu gösterdi) | Aynı parametre iki kez verilmişti | Parametre düzeltildi. Sayfa koruması artık beklenmeyen hataları da yakalıyor: Türkçe mesaj gösteriliyor, ayrıntı sunucu günlüğüne yazılıyor (test eklendi) |

### Düzeltmelerden sonra çalıştırılan kontroller

| Kontrol | Sonuç |
|---|---|
| `.\scripts\screenshots.ps1 -LocalChrome` | 13/13 görüntüde taşma yok, hata yok; 6 etkileşim kontrolü geçti |
| `.\scripts\test.ps1` | 84 passed (yeni: beklenmeyen hata yolu testi) |
| `.\scripts\verify-dashboard.ps1` | Gerçek veride 7/7 örnek filtre doğrudan SQL ile eşleşti |

### Yapılmayan / sınırlar

- **Docker yolu:** Aşama 8'de doğrulandı (yukarıda). Resmî imaj ilk kez indirilirken (Aşama 8'de ~42 dk) ve her çalıştırmada `playwright==1.64.1` PyPI'dan kurulduğu için internet gerekir; ağ yoksa veya PyPI'ya erişilemezse bu yol çalışmaz. Bu yol Aşama 9'da yeniden çalıştırılmadı.
- **Ay etiketi yerleşimi yalnızca 1440 ve 390 px'te ölçüldü.** Plotly ara genişliklerde (ör. 768 px) etiket sıklığını ve açısını kendisi seçer; bu genişliklerde bakılmadı.
- **Tarayıcı:** Yalnızca Chrome 156 (Chromium motoru) ile bakıldı; Edge, Firefox ve Safari'de bakılmadı.
- **Yerel ayar:** Tarayıcı `tr-TR` yerel ayarıyla açıldı; başka yerel ayar denenmedi.
- **Ekran boyutları:** Yalnızca 1440 px ve 390 px genişlik denendi; tablet genişlikleri (ör. 768 px) denenmedi.
- **Grafik ayrıntıları:** Grafik üzerine gelince açılan bilgi kutuları (hover) görüntülerde yok; içerikleri kodda var ama ekranda incelenmedi.
- **Uzun liste:** "Tümü" (74 kategori) seçeneği ekranda açılmadı. Grafik yüksekliği kategori sayısıyla büyüyor; tamamı görüntüde incelenmedi.
- **Ekran okuyucu ve klavye:** Ekran okuyucu ve tam klavye erişilebilirliği sınanmadı.
