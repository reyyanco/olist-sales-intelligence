# Mülakat Rehberi: Olist Sales Intelligence

Bu belge projeyi kendi cümlelerinizle anlatabilmeniz için hazırlandı. Her cevap projedeki bir dosyaya veya ölçüme dayanır; bağlantılar o kanıtı gösterir. Ezberlemek yerine her bölümdeki "neden" kısmını anlamaya çalışın.

## 1. Yaklaşık bir dakikalık anlatım

> Olist'in herkese açık Brezilya e-ticaret verisiyle uçtan uca bir satış analitiği projesi yaptım. Dokuz CSV dosyasını Docker içindeki PostgreSQL 16'ya yükleyen bir ETL yazdım. Veri önce metin olarak staging'e giriyor, orada doğrulanıyor ve sipariş, kalem ve ödeme olgularından oluşan bir yıldız şemaya dönüşüyor. Yükleme tek bir transaction içinde yapılıyor; kalite kontrolü başarısız olursa önceki veri olduğu gibi kalıyor, başarısızlık kaydı da ayrı bir transaction'da tutulduğu için kaybolmuyor.
>
> Metrikleri tanımlarken iki tuzağa dikkat ettim. Birincisi, kalem, ödeme ve yorum tablolarını doğrudan join'lemek tutarları çoğaltıyor. Bu yüzden her birini sipariş düzeyinde ayrı topladım. İkincisi, müşteri kimliği: `customer_id` her siparişte yeniden üretiliyor, kişiyi `customer_unique_id` temsil ediyor.
>
> Analizleri SQL'de yazdım: aylık büyüme, RFM, Pareto ve teslimat performansı. Streamlit paneli bu fonksiyonları salt okunur bir rolle okuyor. Ayrıca ayrı bir veritabanında indeks ve sorgu deneyleri yaptım. Örneğin tekrar satın alma sorgusu indeks olmadan 60 saniyeyi aşıyordu; sorguyu yeniden yazarak indekssiz 406 milisaniyeye indirdim. Sonuçları testlerle, gerçek veride doğrudan SQL karşılaştırmalarıyla ve bir yedek/geri yükleme denemesiyle doğruladım.

## 2. Temel kararlar ve gerekçeleri

### Veri modelleme

- Üç olgu tablosu, üç ayrı grain: `fact_orders` (sipariş), `fact_sales` (kalem), `fact_payments` (ödeme). Ödeme türü analizi ödeme grain'i gerektirdiği için `fact_payments` ayrı tutuldu.
- Yorumlar ayrı olgu yapılmadı; sipariş başına `review_count` ve `review_score_avg` olarak `fact_orders`'a yazıldı.
- `geolocation` boyut olarak modellenmedi: aynı posta kodu önekine çok sayıda satır düşüyor, yani anahtar benzersiz değil.
- Doğal metin anahtarlar kullanıldı. Hepsi 32 haneli hex ve değişmiyor; vekil anahtar ek bir fayda sağlamıyordu.
- Kaynak: [er_diagram.md](er_diagram.md), [data_dictionary.md](data_dictionary.md), [../sql/030_dw_dimensions.sql](../sql/030_dw_dimensions.sql), [../sql/040_dw_facts.sql](../sql/040_dw_facts.sql)

### Müşteri kimliği

- Profilde 2.997 kişinin birden fazla `customer_id`'si çıktı. Teslim edilmiş siparişlerde 96.478 farklı `customer_id` var, bu da sipariş sayısına eşit. Gerçek kişi sayısı 93.358 `customer_unique_id`.
- Tekrar satın alma oranı `customer_id` ile hesaplansaydı sıfıra yakın çıkardı, çünkü her `customer_id`'nin tek siparişi var.
- Kaynak: [metric_definitions.md](metric_definitions.md) bölüm 3, bağımsız kontrol K-13 ([validation_report.md](validation_report.md)).

### Join çoğalması

- Bir siparişte 3 kalem, 2 ödeme ve 2 yorum varsa doğrudan join 3 × 2 × 2 = 12 satır üretir. Sentetik testte ürün tutarı 250,50 yerine 1.002,00, ödeme 275,75 yerine 1.654,50 çıktı.
- Çözüm: kalemler, ödemeler ve yorumlar her biri ayrı ayrı sipariş başına toplanıp `fact_orders`'a yazılıyor.
- Gerçek veride doğrudan join ürün tutarını 13.221.498,11 yerine 13.757.136,52 yapardı (K-9).
- Her yüklemede [../sql/tests/030_reporting_totals_not_duplicated.sql](../sql/tests/030_reporting_totals_not_duplicated.sql) bunu kontrol ediyor.

### ETL ve transaction

- Tam yenileme: staging `TRUNCATE` + `COPY`; dw `DELETE` + `INSERT`; MV yenileme ve kalite kontrolleri aynı transaction'da.
- Neden `DELETE` (dw için)? `TRUNCATE` erişimi kilitler. `DELETE` ile okuyan oturumlar (dashboard) yükleme sırasında kilit beklemeden önceki taahhüt edilmiş veriyi görür (MVCC). Bedeli ölü satırlar; autovacuum temizliyor.
- Çalışma kaydı (`meta.etl_runs`) ayrı transaction'da yazılıyor; bu sayede rollback olsa bile `failed` durumu kalıyor.
- Advisory lock aynı anda iki yüklemeyi engelliyor.
- İşlem içinde `ANALYZE`: boş veritabanına ilk yüklemede tablolar hiç istatistik görmediği için bir kontrol 9 dakikayı aştı. ANALYZE aynı işlemin eklediği satırları görebildiği için çözüm buydu (F1).
- Kaynak: [etl_pipeline.md](etl_pipeline.md), [../etl/pipeline.py](../etl/pipeline.py), [../sql/transform/load_dw.sql](../sql/transform/load_dw.sql)

### Veri kalitesi

- Biçim kuralları açık: kimlik `^[0-9a-f]{32}$`, posta kodu 5 haneli metin, para en fazla 2 ondalık (fazlası yuvarlanmaz, reddedilir).
- Birebir tekrar: ilk satır kalır. Çelişkili anahtar: hiçbir sürüm seçilmez, hepsi reddedilir.
- Bir kalemi reddedilen sipariş eksik tutarla yüklenmez, bütünüyle reddedilir.
- Ret kayıtları neden listesi ve ham satırla `meta.etl_rejected_rows`'a yazılıyor.
- Dürüst not: gerçek veride hiç ret çıkmadı. Ret mantığını sentetik bir "hatalı örnek" veri setiyle sınadım ([../tests/fixtures/olist_quality_sample/](../tests/fixtures/olist_quality_sample/)).

### SQL ve indeks kararları

- Pareto'da kümülatif toplam için `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` kullandım. Varsayılan `RANGE` çerçevesi eşit tutarlı kategorileri aynı değerde birleştirir.
- RFM'de `NTILE` yerine eşitlik güvenli kümülatif dilim kullandım (soru 5).
- İndekslerde ölçüme göre karar verdim:
  - `order_status <> 'delivered'` koşulunda B-tree durum indeksi hiç kullanılmadı (E3, 1,01×), buna karşın yazma maliyetini artırdı.
  - Dashboard sorguları yalnızca iki tarih indeksini, o da dar aralıklarda kullandı (D1).
  - Dashboard'da "kullanılmayan" görünen ürün ve satıcı indeksleri ise ETL'deki `DELETE` sırasında yabancı anahtar kontrolleri için şart çıktı: indeks olmadan `DELETE dim_product` 120 saniyeyi aştı, indeksle 593 ms sürdü (F2, tek ölçüm).
- Kaynak: [performance.md](performance.md)

## 3. Aylık büyümede tam ve kısmi ay ayrımı

İki farklı "kısmi ay" var ve aynı şekilde ele alınmıyorlar:

| Durum | Örnek | Çubuk | Bu ayın oranı | Sonraki ayın oranı |
|---|---|---|---|---|
| Veri kapsamı ayı kesiyor | 2016-09 (15'inden başlıyor), 2018-08 (29'unda bitiyor) | gözlenen günler | gösterilmez | gösterilmez: referans ay eksik |
| Kullanıcı filtresi ayı kesiyor | 10.06–29.08.2018 seçiminde Haziran | yalnızca seçili günler | gösterilmez | **hesaplanır**, tam önceki aya göre |

- Örnekte Haziran çubuğu 593.244,06 BRL'dir, tam Haziran ise 856.077,86. Temmuz büyümesi (867.953,46 − 856.077,86) / 856.077,86 = %1,4 çıkar. Filtreli çubuğa göre hesaplansaydı %46,3 çıkardı; bu, Temmuz'un gerçek büyümesi değildir.
- Neden böyle? Büyüme bir ayın kendine ait özelliğidir; kullanıcının ekranda neyi kestiğine göre değişmemeli. Çubuklar ise KPI kartıyla aynı kapsamı göstermeli, yani filtreyi izlemeli.
- Gözlem dışı aylar (2018-09..11) gösterilmez. Tarih boyutunda yalnızca tahmini teslim tarihleri yüzünden bulunurlar ve o aylarda teslim edilmiş sipariş henüz gözlenmemiştir. 2016-11 ise gözlem aralığında gerçekten satışsız bir aydır ve 0 olarak gösterilir.
- Bu kural iki hatanın düzeltilmesiyle oturdu:
  - Aşama 8'de aylık çubukların seçili aralığı değil tam ayları gösterdiği bulundu: 15.01–10.03.2018'de grafik 2.704.438,38, KPI 1.657.285,69 BRL'ydi.
  - Ardından 2016-10'un büyümesinin 16 günlük Eylül'e göre hesaplandığı fark edildi.
- Kaynak: [../sql/190_report_monthly_sales_date_scope_fix.sql](../sql/190_report_monthly_sales_date_scope_fix.sql), [../sql/200_report_monthly_observation_window.sql](../sql/200_report_monthly_observation_window.sql), [metric_definitions.md](metric_definitions.md) bölüm 11, tarayıcı kanıtı [screenshots/filter_overview_dates_2018-06-10_2018-08-29_hover_july.png](screenshots/filter_overview_dates_2018-06-10_2018-08-29_hover_july.png)

## 4. On teknik soru ve projeye özgü cevaplar

**1. Satış tutarı olarak neyi raporluyorsunuz? Bu gelir mi?**
Teslim edilmiş siparişlerin kalem fiyatlarının brüt toplamını, yani ürün satış tutarını raporluyorum: 13.221.498,11 BRL. Bu kargoyu (2.198.275,64) içermez. Ödeme tutarı da değildir: ödeme 15.422.461,77 BRL ve sipariş başına kalem + kargodan farklı olabiliyor. Bu farkları eşitlemeden raporladım. Maliyet, iade ve vergi bilgisi olmadığı için net gelir veya kâr demiyorum. → [metric_definitions.md](metric_definitions.md) bölüm 2

**2. Bir sipariş birden çok kategoride kalem içeriyorsa kategori filtresi sipariş sayısını nasıl hesaplıyor?**
Tutar, seçili kategorilerdeki kalemlerin toplamı. Sipariş sayısı ise o kategorilerde en az bir kalemi olan farklı siparişlerin sayısı (`count(DISTINCT order_id)`); iki seçili kategoride kalemi olan sipariş bir kez sayılıyor. Kategori sayfasında kategorilerin sipariş sayılarını toplarsanız toplam sipariş sayısını aşabilirsiniz; bu bilinçli bir durum. → [dashboard.md](dashboard.md) "Filtre kuralları", [../sql/160_report_dashboard_functions.sql](../sql/160_report_dashboard_functions.sql)

**3. Yükleme ortasında hata olursa dashboard ne görür?**
Önceki veriyi. Staging, dw, reporting ve ret kayıtları aynı transaction'da olduğu için birlikte geri alınıyor. Bunu bir testte iki oturumla gösterdim: yazan oturum 2 sipariş görürken okuyan oturum kilit beklemeden eski 3 siparişi gördü. Gerçek veride de bilerek düşürülen bir yüklemede tüm tabloların içerik özeti öncekiyle aynı kaldı ve çalışma `failed` olarak kaydedildi. → [etl_pipeline.md](etl_pipeline.md), [../tests/test_pipeline.py](../tests/test_pipeline.py), [validation/controlled_failure.json](validation/controlled_failure.json)

**4. Aynı dosyaları iki kez yüklerseniz ne olur?**
Tam yenileme olduğu için ikinci yükleme aynı sonucu üretir. Bunu iki yükleme sonrası 11 nesnenin satır sayısı ve tüm satırların MD5 özetiyle karşılaştırdım; birebir aynı çıktı. Artımlı yükleme yok; değişen satırları algılamıyorum. → [validation/snapshot_first_load.json](validation/snapshot_first_load.json), [validation/snapshot_second_load.json](validation/snapshot_second_load.json)

**5. RFM puanlamasında neden `NTILE` kullanmadınız? Geçmiş bir tarih için RFM ne kadar doğru?**
`NTILE`, eşit değerleri satır sırasına göre farklı dilimlere bölebiliyor; aynı recency'ye sahip iki müşteri farklı puan alabiliyor. Ben "değeri bu müşteriyle aynı veya daha düşük olan müşteri oranı"na göre dilimledim; eşitler her zaman aynı puanı alıyor. Frequency için sabit eşik kullandım, çünkü müşterilerin %97'si tek siparişli. Geçmiş tarih için önemli bir sınır var: kaynakta sipariş durumlarının geçmişi yok. `as_of` yalnızca satın alma zamanına uygulanıyor ve durum olarak bugünkü anlık görüntü kullanılıyor. Bu yüzden geçmiş RFM tam bir tarihsel durum analizi değil. → [reporting.md](reporting.md) bölüm 2, [../sql/110_report_customer_rfm.sql](../sql/110_report_customer_rfm.sql)

**6. Bir indeks eklemenin bedeli neydi?**
Okuma kazancı yazma maliyetiyle birlikte ölçüldü. Örneğin `customer_unique_id` indeksi kişi sorgusunu 12,9 ms'den 0,96 ms'ye indirdi, ama `dim_customer`'a tüm satırları ekleme süresini 51 ms'den 428 ms'ye çıkardı. Tam yenileme her çalışmada bu tabloyu yeniden yazdığı için bu bedel her ETL'de ödeniyor. E3'teki durum indeksi ise hiç kullanılmadı, yalnızca yazma maliyeti getirdi. → [performance.md](performance.md) E1, E3

**7. Tekrar satın alma sorgusunu nasıl hızlandırdınız?**
İlk sürüm `DISTINCT ON` ile seçim listesinde bir `EXISTS` kullanıyordu. Plan bu `EXISTS`'in semi-join'e dönüşmediğini, müşteri başına çalışan bir SubPlan olduğunu gösterdi. İndeks yokken her seferinde `dim_customer` taranıyordu ve sorgu 60 saniye sınırını aştı. Müşteri başına `count(DISTINCT order_id)` ile tek geçişte toplayınca indekssiz 406 ms'ye indi; indeksli eski sürüm 1.518 ms'ydi. Sonucun aynı olduğunu MD5 ve gerçek veride iki yönlü `EXCEPT ALL` ile gösterdim, sonra ana modele uyguladım. Başlangıç zaman aşımına uğradığı için kesin bir katsayı söylemiyorum. → [../sql/170_report_repeat_purchase_single_pass.sql](../sql/170_report_repeat_purchase_single_pass.sql), [perf/results/E4_repeat_purchase_rewrite.json](perf/results/E4_repeat_purchase_rewrite.json)

**8. Materialized view'i ne zaman tercih edersiniz?**
Veri seyrek değişip sık okunuyorsa. Kategori raporunun hesabı 569 ms, MV'den okumak 0,6 ms; bir yenileme 550–565 ms sürüyor ve depolama 40 KB. Bedeli güncellik: bir fiyatı değiştirdiğimde MV yenilenene kadar eski toplamı gösterdi. Bu projede MV'ler ETL transaction'ının sonunda yenileniyor. `CONCURRENTLY` için MV'nin dolu olması ve `WHERE` içermeyen bir UNIQUE indeks gerekiyor; prosedür bunu katalogdan kontrol ediyor. → [performance.md](performance.md) E5, [reporting.md](reporting.md) "Materialized view yenileme"

**9. Dashboard veritabanına nasıl bağlanıyor, güvenlik için ne yaptınız?**
Yönetici hesabıyla değil, `olist_dashboard` rolüyle bağlanıyor. Bu rol yalnızca `reporting` şemasındaki view'leri okuyabiliyor ve dashboard fonksiyonlarını çalıştırabiliyor. Oturumları salt okunur ve 30 saniye zaman sınırlı. `dw`, `staging` ve `meta`'ya erişimi yok; PUBLIC'in varsayılan EXECUTE yetkisini kaldırdım. Kullanıcı girdileri her zaman bağlama parametresi olarak geçiyor. Parola `.env`'den geliyor ve hiçbir çıktıya yazılmıyor. Her sınırı testte 42501 yetki hatasıyla doğruladım. → [../sql/180_dashboard_reader_role.sql](../sql/180_dashboard_reader_role.sql), [../etl/dashboard_role.py](../etl/dashboard_role.py)

**10. Yedekten geri yüklemenin çalıştığını nasıl biliyorsunuz?**
Dosyanın oluşmasını yeterli saymadım. Yedeği ayrı bir veritabanına geri yükledim ve kaynakla aynı sorguyu iki tarafta çalıştırdım: 26 tablonun satır sayısı ve içerik MD5'i, nesne sayıları, finansal toplamlar ve rol yetkileri aynı çıktı. Çalışma kayıtlarını ayrı değerlendirdim. Hedefte 9 kalite kontrolünü de çalıştırdım. Ayrıca rollerin olmadığı yeni bir PostgreSQL kümesine geri yükleyip dashboard'u çalıştırdım. `pg_dump` rolleri ve parolaları içermediği için parolasız okuma rolünü betik oluşturuyor, giriş rolünü `setup-dashboard-role` `.env`'den kuruyor. → [validation/backup_restore_check.json](validation/backup_restore_check.json), [validation/backup_restore_fresh_cluster.json](validation/backup_restore_fresh_cluster.json), [../scripts/restore.ps1](../scripts/restore.ps1)

## 5. Bilmediğiniz veya ölçmediğiniz konularda dürüst cevap örnekleri

**"Soğuk önbellekte veya 50 eşzamanlı kullanıcıda dashboard ne kadar hızlı?"**
> Ölçmedim. Tüm ölçümlerim sıcak önbellekte ve tek kullanıcıyla. Tam kapsamda en yavaş dashboard çağrısı RFM segmentleriydi, yaklaşık 1 saniye. Eşzamanlı yükü ölçmek isteseydim `pgbench` ile özel bir senaryo yazar, önbelleği temizleyip tekrar ölçerdim. Bunu yapmadan bir sayı vermem doğru olmaz.

**"ETL süresi neden 81 saniyeden 137 saniyeye çıktı?"**
> Nedenini belirlemedim. Bunlar tek ölçümler, benchmark değil. Arada işlem içi `ANALYZE` ve yeni rapor nesneleri eklendi. Temiz kurulumda 76 ve 103 saniye ölçüldü. Kesin bir neden için adım adım süre kaydı tutup birkaç kez tekrarlamam gerekir.

**"Para birimi BRL mi, zamanlar hangi saat diliminde?"**
> Kaynak bunları açıkça belirtmiyor. Veri Brezilya'ya ait olduğu için BRL ve yerel saat varsaydım. Bunu belgelerde ve arayüzde varsayım olarak yazdım, saat dilimi dönüşümü yapmadım.

**"Bu sistem canlı ortama hazır mı?"**
> Hayır, bunu iddia etmiyorum. Yerel, tek kullanıcılı bir portföy demosu. Artımlı yükleme, zamanlanmış yedek, izleme ve çok kullanıcılı yük testi yok. Bunların hangilerinin önce ekleneceğini kullanım ihtiyacına göre seçerdim.

**"Firefox'ta veya ekran okuyucuyla çalışıyor mu?"**
> Sınamadım. Yalnızca Chrome'da (Chromium) 1440 ve 390 piksel genişlikte gerçek tarayıcı kontrolü yaptım. Bu kontrolde dar ekranda aylık grafiğin ay etiketlerinin üst üste bindiğini gördüm. Etiketleri genişliğe göre seyrelten ve dik yazan bir eksen ayarına geçtim. Düzeltmenin işe yaradığını tarayıcıda etiketlerin konumunu ölçerek gösterdim; eski hâlde aynı ölçüm 23 çakışma buluyordu.
