# Olist Sales Intelligence — Çalışma Kuralları

Bu dosya projenin tamamı boyunca geçerli kuralları içerir. İlerleme durumu `docs/project_state.md` dosyasında tutulur.

## Proje

Yerel olarak çalışan bir satış veri ambarı ve SQL raporlama paneli. Hedef bileşenler (tamamı Docker içinde):

- PostgreSQL 16
- Python 3.11 (ETL ve testler)
- Streamlit dashboard

PostgreSQL ve Python Windows'a ayrıca kurulmaz; proje için yalnızca Docker içinde çalışır.

## Çalışma kuralları

1. Dosya ve terminal erişimi varsa işi doğrudan yap; yalnızca uygulama talimatı yazmakla yetinme.
2. Her mesajda yalnızca istenen aşamayı tamamla.
3. Rutin kararları gerekçeli biçimde kendin ver; gerekli düzeltmeler için sürekli onay isteme.
4. Çalıştırılmamış testi geçmiş, ölçülmemiş performansı ölçülmüş, görülmemiş ekranı doğrulanmış sayma.
5. Gerçek veri ile test verisini açıkça ayır (ayrı klasör, ayrı şema/veritabanı, açık adlandırma).
6. Parolaları koda yazma; gizli bilgileri çıktılarda gösterme. Gizli değerler `.env` dosyasında tutulur ve git'e eklenmez; şablon olarak `.env.example` kullanılır.
7. Üretim kodunda uygulanmamış fonksiyon veya göstermelik başarı mesajı bırakma.
8. Hata bulunduğunda nedenini düzelt; testi yanlış sonuca uydurarak geçirme.
9. Açıklamalar ve belgeler Türkçe; kod, dosya, tablo, sütun ve diğer veritabanı adları İngilizce.
10. Her aşamanın sonunda `docs/project_state.md` dosyasını güncelle: tamamlanan işler, kararlar, gerçek test sonuçları ve eksikler.

## Araç ve güvenlik kuralları

- Kurulu ve doğru çalışan araçları yeniden kurma.
- Eksik araçları yalnızca resmî kaynaklardan kur. WinGet kullanılırsa paket kimliği, yayıncı ve kaynak doğrulanır.
- İndirilen Windows kurulum dosyalarının dijital imzası ve yayıncısı kontrol edilir; kontrol başarısızsa dosya çalıştırılmaz.
- Güvenlik korumaları kapatılmaz, imza kontrolleri atlanmaz.
- Yönetici onayı, hesap girişi, lisans kabulü, BIOS ayarı veya yeniden başlatma gerekiyorsa kullanıcıya açıkça bildirilir.

## Ücretsiz ve yerel kullanım kuralı

- Uygulama tamamen yerel çalışır.
- Kişisel kullanım için ücretsiz Docker Desktop kullanılır.
- Yalnızca PostgreSQL, Python, Streamlit, Plotly ve diğer ücretsiz/açık kaynak bileşenler kullanılır.
- Ücretli bulut servisi, Docker Build Cloud, ücretli veritabanı, ücretli API veya deneme süresi sonunda ödeme isteyen hizmet eklenmez.
- Docker derlemeleri bilgisayardaki yerel motorla yapılır (yerel `docker` sürücülü builder).
- Satın alma, abonelik yükseltme, kredi satın alma veya ek ücretli kullanım etkinleştirilmez.
- Uygulamanın çalışması Claude, OpenAI veya başka bir ücretli yapay zekâ API'sine bağlı olmaz.

## Ortam notları

- Windows 11, VS Code, Claude Code, Git, Docker Desktop (WSL 2 arka ucu).
- Docker CLI yolu: `C:\Program Files\Docker\Docker\resources\bin`. Kurulumdan önce açılmış terminallerde PATH eski kalabilir; terminali yeniden açmak gerekir.
