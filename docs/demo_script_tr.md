# Demo Akışı (yaklaşık 3 dakika)

## Demo öncesi hazırlık (5 dakika önce)

1. Docker Desktop'ı açın, "Engine running" olmasını bekleyin.
2. PowerShell'de proje klasöründe:

   ```powershell
   .\scripts\up.ps1
   .\scripts\dashboard.ps1
   .\scripts\etl.ps1 runs --limit 5    # son başarılı ve bilerek düşürülmüş çalışmayı görmek için
   ```

3. Tarayıcıda http://127.0.0.1:8501 adresini açın. Sayfa ilk açılışta birkaç saniye hesaplar; önbellek ısınsın diye dört sayfayı bir kez dolaşın.
4. VS Code'da şu sekmeleri hazır tutun:
   - [../sql/200_report_monthly_observation_window.sql](../sql/200_report_monthly_observation_window.sql)
   - [../sql/170_report_repeat_purchase_single_pass.sql](../sql/170_report_repeat_purchase_single_pass.sql)
   - [performance.md](performance.md) (E4 bölümü)
   - [validation/backup_restore_check.json](validation/backup_restore_check.json)
5. Yedek ekran: Docker çalışmazsa [screenshots/](screenshots/) altındaki gerçek görüntülerle aynı akışı anlatın ve bunun canlı demo olmadığını söyleyin.

## Akış

| Süre | Ekran | Yapılacak | Anlatılacak |
|---|---|---|---|
| 0:00–0:20 | Genel Bakış | — | "Olist'in açık verisi, Docker içinde PostgreSQL'e yüklendi. Panel yalnızca okuma yetkili bir rolle bağlanıyor." |
| 0:20–0:50 | Genel Bakış, filtresiz | KPI kartlarını gösterin | "Ürün satış tutarı 13,2 milyon BRL; kargo ve ödeme ayrı metrikler, bu kâr değil. 96.478 sipariş ama 93.358 müşteri: müşteriyi `customer_unique_id` ile sayıyorum, `customer_id` her siparişte yeni." 11.2016 çubuğunun 0 olduğunu gösterin: "Gözlem aralığında gerçekten satış yok; 2018-09 sonrası ise gözlenmediği için hiç gösterilmiyor." |
| 0:50–1:30 | Genel Bakış | Tarihi **10.06.2018 – 29.08.2018** yapın; fareyi Temmuz çubuğuna getirin | "Haziran çubuğu yalnızca seçtiğim günleri gösteriyor ve açık renkli, yani kısmi. Temmuz'un %1,4 büyümesi bu kısa çubuğa değil, tam Haziran'a göre. Kısa çubuğa göre hesaplasaydım %46 gibi yanlış bir oran çıkardı." Grafiğin altındaki açıklamayı gösterin. |
| 1:30–1:45 | VS Code: `sql/200` | `growth_status` değerlerini gösterin | "Bu kural SQL'de. Panel metriği yeniden hesaplamıyor, yalnızca okuyor." |
| 1:45–2:10 | Kategori Analizi | "Tüm veri kapsamı" düğmesine basın | "Pareto: satışın %80'ine 18. kategoride ulaşılıyor. Kümülatifte `ROWS` çerçevesi kullandım, çünkü eşit tutarlı kategorilerde `RANGE` yanlış birleştirir." |
| 2:10–2:25 | Müşteri Analizi | — | "Tekrar satın alma oranı %3; müşterilerin %97'si tek siparişli. Bu yüzden RFM'de frequency için sabit eşik kullandım." |
| 2:25–2:40 | Teslimat Performansı | Eyaleti **BA** seçin | "Ortalama teslimat 19,3 gün, geç teslimat %12,2; ülke geneli 12,6 gün ve %6,8. Teslim zamanı boş 8 sipariş paydadan çıkarılıyor." |
| 2:40–3:00 | VS Code: `performance.md` E4 ve `sql/170`; terminalde `runs` çıktısı | — | "Tekrar alım sorgusu indekssiz 60 saniyeyi aşıyordu; tek geçişli toplamayla 406 ms oldu. Bu ölçüm sıcak önbellekte ve deney veritabanında yapıldı. Listede bilerek düşürülmüş bir yükleme var; o çalışmada önceki veri korundu. Yedeği de ayrı bir veritabanına geri yükleyip satır sayıları ve içerik özetleriyle karşılaştırdım." |

## Kullanılan değerler (doğrulama kaynağı)

| Değer | Kaynak |
|---|---|
| 13.221.498,11 BRL; 96.478 sipariş; 93.358 müşteri | `reporting.v_sales_kpis`; [screenshots/report.json](screenshots/report.json) |
| Haziran 593.244,06; Temmuz %1,4; tam Haziran 856.077,86 | [screenshots/interactions.json](screenshots/interactions.json) (`overview_growth_full_month_base`), [project_state.md](project_state.md) |
| 18. kategoride %80 | [reporting.md](reporting.md) bölüm 3 |
| %3,00; %97 tek siparişli | [reporting.md](reporting.md) bölüm 2 ve 5 |
| BA: 19,34 gün, %12,16 | [dashboard.md](dashboard.md) "Arayüz etkileşimleri" |
| 60 s zaman aşımı → 405,891 ms | [perf/results/E4_repeat_purchase_rewrite.json](perf/results/E4_repeat_purchase_rewrite.json) |

## Demo sırasında söylememeniz gerekenler

- "Uygulama 147 kat hızlandı": yanlış. Tek bir sorgu deney ortamında hızlandı; başlangıç zaman aşımına uğradığı için kesin bir katsayı da yok.
- "Hatasız" veya "canlı ortama hazır": doğrulama kapsamı ve sınırlamalar README bölüm 16'da.
- "Müşteri sayısı 99.441": bu, tüm durumlardaki `customer_id` sayısıdır.
