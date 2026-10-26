# Özgeçmiş Maddeleri: Olist Sales Intelligence

Kişisel portföy projesi · PostgreSQL 16, Python 3.11, Docker Compose, Streamlit, Plotly, pytest

- Olist'in herkese açık e-ticaret verisini (99.441 sipariş, 112.650 sipariş kalemi, 9 CSV) PostgreSQL'de staging → yıldız şema → raporlama katmanlarına taşıyan, Docker Compose ile tamamen yerel çalışan bir veri ambarı kurdum. Müşteri metriklerinde siparişe özgü `customer_id` yerine `customer_unique_id` kullandım; sipariş, kalem ve müşteri sayılarını ayrı metrikler olarak tanımladım.
- `COPY` ile yükleyen, tek işlemde tam yenileme yapan bir ETL yazdım. Hatalı ve çelişkili kayıtlar gerekçesiyle ayrı tabloya yazılıyor, her çalışma `run_id` ile kaydediliyor. Kalite kontrolü başarısız olduğunda önceki veri ve hata kaydı korunuyor; bu davranış hem sentetik testlerle hem gerçek veride bilerek düşürülen bir yüklemeyle doğrulandı.
- Aylık büyüme (tam/kısmi ay ayrımıyla), RFM, Pareto kategori payı ve teslimat analizlerini window function, `ROLLUP` ve `GROUPING SETS` ile SQL'de yazdım. Dört sayfalık Streamlit panelinin KPI'larını, salt okunur bir veritabanı rolüyle bağlanan uygulamada 7 örnek filtrede doğrudan SQL ile karşılaştırdım; hepsi eşleşti. Projede 89 otomatik test var.
- Ayrı bir veritabanında, gerçek veriyle indeks, sorgu yeniden yazma, materialized view ve partitioning deneyleri yaptım (sıcak önbellek, 7 tekrarın medyanı, sonuç eşitliği MD5 ile kontrol edildi). İndekssiz hâlde 60 saniye sınırını aşan tekrar satın alma sorgusunu tek geçişli toplamayla 406 ms'ye indirip ana modele uyguladım. Hızlandırmayan `work_mem` ve partitioning değişikliklerini ise uygulamadım.

## Kullanırken dikkat

- Sayılar `docs/project_state.md` ve `docs/performance.md` kayıtlarındandır. 406 ms, deney veritabanında ve sıcak önbellekte ölçüldü; uygulamanın bütününün hızlandığı anlamına gelmez.
- "99.441 sipariş" tüm durumları kapsar. Satış metrikleri yalnızca teslim edilmiş 96.478 siparişle hesaplanır. Kalem sayısı adet sayısı değildir.
- "Production-ready", "hatasız" gibi ifadeler kullanmayın. Proje yerel bir demodur; sınırlamalar README bölüm 16'da yazılıdır.
