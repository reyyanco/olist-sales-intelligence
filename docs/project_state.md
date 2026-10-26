# Proje Durumu

Son güncelleme: 2026-10-25 (Aşama 9: belgeler, yedekleme ve teslim)

> Not: Aşama numaraları kullanıcının numaralandırmasıyla hizalandı (önceden "Aşama 0" ve "0.1" idi). Aşama 1 = araçlar, Aşama 2 = proje temeli.

## Aşama 1 — Araçlar ve çalışma klasörü (tamamlandı)

### Başlangıç durumu

- Proje klasörü (`<kullanıcı klasörü>\Projects\olist-sales-intelligence`) mevcuttu, boştu ve yazılabilirdi. Korunması gereken mevcut çalışma yoktu.

### Sistem bilgileri (komutlarla okundu)

| Bilgi | Değer |
|---|---|
| İşletim sistemi | Windows 11 Home Single Language, 25H2, build 26200.9711, 64 bit |
| İşlemci | AMD Ryzen 7 5700U, 8 çekirdek / 16 mantıksal işlemci, x64 (AMD64) |
| RAM | 15,3 GB toplam (ölçüm anında 2,8 GB boş) |
| Disk | C: 475,9 GB, 315,1 GB boş |
| Sanallaştırma | Firmware'de etkin; hypervisor çalışıyor; VirtualMachinePlatform etkin |
| Oturum | Yönetici olmayan kullanıcı (yükseltme UAC ile yapıldı) |

Not: `VMMonitorModeExtensions` ve `SLAT` değerleri `False` döndü. Hypervisor çalışırken Windows bu alanları böyle raporlar; WSL 2 ve Docker'ın gerçekten çalışması sanallaştırmanın kullanılabildiğini doğruluyor.

### Araçlar

| Araç | Sürüm | Durum |
|---|---|---|
| Git | 2.54.0.windows.1 | Önceden kuruluydu; yeniden kurulmadı. Global `user.name` ve `user.email` tanımlı. |
| VS Code | 1.142.0 | Önceden kuruluydu. |
| WSL | 2.7.12.0 (çekirdek 6.18.33.2-2), varsayılan sürüm 2 | Önceden kuruluydu. |
| WinGet | 1.29.380 (App Installer, yayıncı Microsoft Corporation) | Önceden kuruluydu; bu kabuğun PATH'inde değildi, tam yolla kullanıldı. |
| Docker Desktop | 4.96.3 (244472) | **Bu aşamada kuruldu.** |
| Docker Engine / CLI | 29.9.2 | Docker Desktop ile geldi. |
| Docker Compose | v5.6.1 | Docker Desktop ile geldi. |

Windows'a ayrıca kurulu bir Python 3.14 bulundu. Projede kullanılmayacak; proje Python'u Docker içinde 3.11 olacak.

### Docker Desktop kurulum doğrulaması

- WinGet paketi: `Docker.DockerDesktop`, yayıncı `Docker Inc.`, kaynak `winget` (`https://cdn.winget.microsoft.com/cache`).
- İndirme adresi: `https://desktop.docker.com/win/main/amd64/244472/Docker%20Desktop%20Installer.exe`.
- SHA256 `3D8ADAD4F6C86583E0B00EA19A76197C51CCF5C83437C9ED775B739756452507`: winget manifestiyle eşleşti.
- Authenticode imzası: `Valid`, imzalayan `CN=Docker Inc`, düzenleyen `DigiCert Trusted G4 Code Signing RSA4096 SHA384 2021 CA1`, zaman damgalı.
- Kurulum `install --quiet --backend=wsl-2` ile, UAC onayıyla çalıştırıldı; çıkış kodu 0.
- Lisans sözleşmesi kullanıcı adına kabul edilmedi (`--accept-license` kullanılmadı).
- Kurulu `Docker Desktop.exe` imzası da `Valid` / `CN=Docker Inc`.

### Gerçek test sonuçları

| Test | Sonuç |
|---|---|
| `docker version` (istemci + sunucu) | Geçti; sunucu `linux/amd64`, Engine 29.9.2 |
| `wsl -l -v` | `docker-desktop` dağıtımı Running, sürüm 2 |
| `docker run --rm hello-world` | İlk denemede **başarısız** (çıkış 127: `docker-credential-desktop` PATH'te yok). Neden: kurulumdan önce açılmış oturumun PATH'i eskiydi. PATH kayıt defterinden yenilenince **geçti** (çıkış 0, "Hello from Docker!"). |
| `docker compose up` (hello-world servisi) | PATH düzeltmesinden sonra **geçti** (`--exit-code-from smoke`, çıkış 0); `down` çıkış 0 |
| `docker info` | 16 CPU, ~7,4 GiB bellek Docker'a ayrılmış, depolama `overlayfs` |

Test imajı (`hello-world`) silindi. Test dosyaları proje dışında, geçici klasörde tutuldu.

### Kararlar

- Docker Desktop, kurulumu doğrudan çalıştırmak yerine önce `winget download` ile indirildi; hash ve imza kontrolünden sonra çalıştırıldı.
- Arka uç olarak WSL 2 seçildi (Windows Home'da Hyper-V arka ucu yok; hedef ortam da WSL 2).
- Ayrı bir Linux dağıtımı (Ubuntu vb.) kurulmadı; Docker Desktop kendi `docker-desktop` dağıtımını kullanıyor ve proje için ek dağıtım gerekmiyor.
- Proje klasöründe git deposu başlatıldı (`main` dalı); henüz commit yapılmadı.

### Kullanıcı adımları (yapıldı)

- Bilgisayar yeniden başlatıldı; Docker Desktop açıldı. Ayarlarda `LicenseTermsVersion = 2` görülüyor, yani lisans kullanıcı tarafından kabul edilmiş.
- Kullanıcı doğrulama komutlarını çalıştırdı: Git, Docker istemci/sunucu, Compose ve WSL 2 çalıştı; `hello-world` indirilemedi (aşağıya bakın).

## Aşama 1.1 — Yeniden başlatma sonrası imaj indirme sorunu (2026-10-23)

### Belirti (kullanıcının bildirdiği)

```
failed to resolve reference "docker.io/library/hello-world:latest"
lookup registry-1.docker.io: no such host
```

### Teşhis (ölçülen)

Windows tarafı:

- Proxy yok: WinHTTP "Direct access", kullanıcı proxy'si kapalı (`ProxyEnable = 0`), PAC yok, proxy ortam değişkeni yok. VPN bağdaştırıcısı yok.
- DNS sunucusu: Wi-Fi üzerinde DHCP'den gelen tek bir sunucu var (yerel ağın özel IP adresi; yayımlanan belgede yazılmadı). Ağ geçidi DNS hizmeti vermiyor (15/15 sorgu başarısız).
- Bu DNS sunucusuna 15 sorgu: 15'i başarılı, ortalama **~2,4 s**. Karşılaştırma için yalnızca test sorgusu (ayar değiştirilmedi): 1.1.1.1 14/15, ~1,0 s; 8.8.8.8 15/15, ~0,6 s.
- Sistem çözümleyicisi aralıklı başarısız oldu: `registry-1.docker.io` bir sorguda çözüldü ve TCP 443 bağlantısı kuruldu (`True`). Hemen ardından `Invoke-WebRequest` aynı adı çözemedi. `auth.docker.io` ve `production.cloudflare.docker.com` zaman aşımına düştü.

Docker tarafı (Windows'tan ayrı değerlendirildi):

- Docker ayarları varsayılan; özel DNS, proxy veya mirror yok. `http.docker.internal:3128` Docker Desktop'ın kendi iç proxy'si; dış proxy değil.
- Kayıtlar (`%LOCALAPPDATA%\Docker\log`):
  - Yeniden başlatmadan önce (12:16 UTC) VM içinde `registry-1.docker.io` çözülmüş, host proxy bağlantısı başarılı olmuş.
  - Yeniden başlatmadan sonra (12:22 UTC'den itibaren) host tarafındaki `httpproxy` / `com.docker.backend` süreçleri Docker alan adları için `dial tcp: lookup ...: no such host` kaydetmiş. WSL DNS tüneli için `i/o timeout` görülmüş.
  - Proxy kimlik doğrulaması (407) veya TLS hatası yok.
- VM içinden `nslookup` (`wsl -d docker-desktop`), şu anki durumda: 3 Docker adı için 15/15 başarılı, ~170 ms.

### Sonuç

- Neden: host'un DNS çözümlemesi yeniden başlatma sonrasında başarısız oldu. Docker'ın imaj çekme trafiği Windows çözümleyicisine (yerel ağın DNS sunucusuna) dayanıyor. Bu sunucu yavaş yanıt veriyor ve zaman zaman Windows'ta bile zaman aşımına düşüyor.
- Proxy gerektiğine dair kanıt bulunmadı.
- Belirsizlik: hatanın tam o anda neden kalıcı göründüğü (Wi-Fi/DNS'in açılışta henüz hazır olmaması mı, sunucunun geçici aşırı yükü mü) kesin olarak ayırt edilemedi.

### Yapılan müdahale

- **Hiçbir ayar değiştirilmedi.** Docker Desktop yeniden başlatılmadı. Çalışan container yoktu (`docker ps`: 0).
- En az müdahaleli adım olarak hiçbir şeyi değiştirmeden yeniden denendi; sorun bu anda yaşanmadı.
- Kalıcı DNS değişikliği yapılmadı. Ağın DNS'i çalışıyor; yalnızca yavaş. Ayrıca bu ağdaki iç adlar bu DNS sunucusuna bağlı olabilir; genel bir DNS'e geçmek o adları bozabilir.

### Gerçek test sonuçları

| Test | Sonuç |
|---|---|
| `docker pull hello-world` (ilk) | Geçti, çıkış 0, **64 s** (yavaş DNS ile tutarlı) |
| `docker run --rm hello-world` | Geçti, çıkış 0, "Hello from Docker!" görüldü |
| `docker pull hello-world` ×3 (tekrar) | 3/3 geçti, çıkış 0, ~1,6 s her biri |

Not: bir ara denemede `docker run` çıktısı `Select-Object -First 4` ile kesildiği için çıkış kodu -1 döndü. Bu ölçüm hatasıydı ve başarı sayılmadı; komut tam çıktıyla yeniden çalıştırılınca çıkış 0 verdi.

`hello-world` imajı yerelde bırakıldı.

### Kalan risk

- Ağın DNS sunucusu yavaş ve aralıklı. Büyük imajlar (`postgres:16`, `python:3.11`) çekilirken hata tekrarlayabilir. Önerilen sıra:
  1. Komutu yeniden deneyin.
  2. Tekrarlarsa ölçüm yapıp kanıt toplayın: aynı anda `Resolve-DnsName registry-1.docker.io` ve `Resolve-DnsName registry-1.docker.io -Server 8.8.8.8` sonuçlarını karşılaştırın.
  3. Kanıt varsa ve ağ yöneticisi sakınca görmüyorsa, Wi-Fi bağdaştırıcısına ikincil/alternatif DNS eklemeyi değerlendirin. Bu yönetici yetkisi ve kullanıcı onayı gerektirir.
- Docker'ın `daemon.json` içindeki `dns` alanı yalnızca container'ların DNS'ini etkiler, imaj çekmeyi düzeltmez; bu yüzden çözüm olarak kullanılmadı.

### Eksikler / sonraki aşama

- Aşama 1 tamam. Araçlar ve imaj çekme doğrulandı.
- Uygulama kodu (Docker Compose dosyası, PostgreSQL şeması, ETL, testler, dashboard) henüz yazılmadı; Aşama 2'de başlayacak.

## Aşama 2 — Proje temeli (tamamlandı, 2026-10-23 / 2026-10-24)

### Oluşturulanlar

- Klasörler: `data/raw/`, `etl/`, `sql/`, `sql/queries/`, `sql/tests/`, `dashboard/`, `tests/fixtures/`, `docs/`, `scripts/`. Boş klasörler `.gitkeep` ile tutuluyor.
- Dosyalar: `README.md`, `compose.yaml`, `compose.db-port.yaml`, `Dockerfile`, `.dockerignore`, `.env.example`, `.gitignore`, `requirements.in`, `requirements.txt`, `pytest.ini`.
- Kod:
  - `etl/settings.py`: ortam değişkenlerinden ayar okur; parola `repr` çıktısında görünmez.
  - `etl/db.py`: engine oluşturur ve sunucu bilgisini sorgular.
  - `etl/sql_runner.py`: numaralı SQL dosyalarını uygular.
  - `etl/__main__.py`: `check` ve `migrate` komutları.
  - `dashboard/app.py`: bağlantı durumu iskeleti.
- SQL: `sql/010_create_schemas.sql` yalnızca `staging` ve `dw` şemalarını oluşturur. Veri modeli Aşama 3 ve sonrasına bırakıldı.
- Betikler (`scripts/`, UTF-8 BOM'lu; Windows PowerShell 5.1 Türkçe karakterleri doğru okusun diye):
  - `new-env.ps1`, `up.ps1`, `etl.ps1`, `test.ps1`, `dashboard.ps1`
  - `down.ps1`: veriyi korur.
  - `reset.ps1`: veriyi siler; proje adının yazılmasıyla onay ister.
- `.env`: `new-env.ps1` ile oluşturuldu; parola 48 haneli rastgele hex, hiçbir çıktıda gösterilmedi. `git check-ignore .env` doğrulandı.

### Sürüm sabitleme

- PostgreSQL: `postgres:16.15-bookworm@sha256:d81f7b51697014367236d07ec58b54153fc28f828b72bf247fe5c7487520bcb0`
- Python: `python:3.11.17-slim-bookworm@sha256:f06d01d4ba3f8ad5af45a3ec87df19c1d317d8e8961edc0fabda61811af6f7cf`
- Paketler: `requirements.in` içinde doğrudan bağımlılıklar (pandas 3.1.0, SQLAlchemy 2.1.6, psycopg2-binary 2.9.13, streamlit 1.66.1, plotly 7.1.0, pytest 9.1.1). `requirements.txt` bunların Python 3.11.17 içinde kurulup `pip freeze` ile alınmış tam listesi (42 paket); `pip check` temiz.
- Yenileme yöntemi: `requirements.in` güncellenir, aynı Python imajında kurulur, `pip freeze` çıktısı `requirements.txt`'ye yazılır, `pip check` çalıştırılır.
- Dockerfile `pip install --no-deps -r requirements.txt && pip check` kullanır; liste dışı paket gelmez.

### Kararlar

- Tek Python imajı (ETL, testler, dashboard). İmaj yalnızca `app` servisinde derlenir; diğer servisler `pull_policy: never` ile o imajı kullanır.
- Tek seferlik işler (`etl`, `tests`) `jobs` profilinde ve `docker compose run --rm` ile çalışır. Sürekli servisler `db` (profilsiz) ve `dashboard` (`dashboard` profili).
- PostgreSQL portu varsayılan olarak açılmaz; gerekirse `compose.db-port.yaml` portu yalnızca `127.0.0.1` üzerinden açar. Dashboard yalnızca `127.0.0.1:8501` adresine bağlanır.
- `db` sağlık kontrolü: `pg_isready` + TCP üzerinden `SELECT 1`. İlk kurulumdaki geçici sunucu yalnızca Unix soketini dinlediği için bu kontrol erken "sağlıklı" sonucunu önler.
- Gerçek/test ayrımı: testler `olist_test` veritabanını kullanır (yoksa oluşturur) ve `data/raw` bağlanmaz. Test veritabanı adı `_test` ile bitmiyorsa veya ana veritabanıyla aynıysa testler çalışmaz.
- SQL sırası: `sql/NNN_aciklama.sql` dosyaları numaraya göre uygulanır; `meta.schema_migrations` SHA-256 ile izlenir; uygulanmış dosya değişirse hata verilir; her dosya kendi işleminde çalışır; aynı anda iki uygulayıcı çalışmasın diye advisory lock alınır.
- Dashboard'a bilinçli olarak yalnızca bağlantı durumu kondu ve "analiz panelleri henüz geliştirilmedi" uyarısı gösteriliyor.
- Git deposu korunuyor; henüz commit yapılmadı (kullanıcı istemedi).

### Bulunan ve kökünden düzeltilen hatalar

1. **İlk imaj derlemesi başarısız oldu:** `ReadTimeoutError` (`files.pythonhosted.org`); `docker buildx history` ile teşhis edildi. Aynı imaj üç servis için paralel derlendiği için paketler üç kez aynı anda indiriliyordu.
   Düzeltme: imaj yalnızca `app` servisinde derleniyor; `PIP_DEFAULT_TIMEOUT=60`, `PIP_RETRIES=10`; pip önbelleği BuildKit önbelleğinde tutuluyor. Sonrasında sıfırdan derleme tek seferde ve başarılı.
2. **`etl/sql_runner.py` içinde `%` hatası:** `exec_driver_sql` boş parametre sözlüğü geçiriyor ve psycopg2 SQL içindeki `%` karakterini biçim işareti sayıyordu (`TypeError`). Hatayı `test_apply_runs_each_file_once` yakaladı.
   Düzeltme: SQL ham DBAPI imleciyle, aynı işlem içinde, parametresiz çalıştırılıyor. Test değiştirilmedi.
3. **`_common.ps1` stderr sorunu:** Windows PowerShell 5.1'de çıktı yönlendirilince Docker'ın stderr'e yazdığı ilerleme satırları ölümcül hataya dönüşüyordu.
   Düzeltme: yerel komut çağrısında `ErrorActionPreference` geçici olarak `Continue`; başarı çıkış koduyla ölçülüyor.

### İlk çalıştırma test sonuçları (2026-10-23)

- `up.ps1`: başarılı; `db` healthy.
- `etl.ps1 check`: PostgreSQL 16.15'e bağlanıp SELECT çalıştırdı.
- `etl.ps1`: ilk çalıştırmada `010_create_schemas.sql` uygulandı; ikinci çalıştırmada "Uygulanacak yeni SQL dosyası yok".
- `test.ps1 -v`: önce 18 geçti / 1 kaldı (hata 2), düzeltmeden sonra 19/19 geçti.
- Önceki yanıt bu noktada API bağlantı hatasıyla (`ENOTFOUND`) kesildi. Dashboard, `down` ve README o oturumda doğrulanmadı ve yazılmadı.

## Aşama 2.1 — Docker nesneleri silindikten sonra kurtarma (2026-10-24)

### Başlangıç durumu (ölçülen)

- Kaynak dosyaları ve `.env` yerindeydi (6 anahtarın tamamı mevcut; değerler gösterilmedi). `README.md` yoktu.
- Docker motoru kapalıydı (`AutoStart = False`); Docker Desktop başlatıldı.

| Nesne | Durum |
|---|---|
| `olist-sales-intelligence-db-1` konteyneri | **Silinmiş** |
| `olist-sales-intelligence_default` ağı | **Yok** (konteynerle birlikte kaldırılmış olabilir) |
| `olist-sales-intelligence_pgdata` volume'u | Mevcut; 2026-10-23 13:20:56 UTC'de oluşturulmuş (orijinal), 70 MB, PG_VERSION 16 |
| `olist-sales-intelligence-app:local` imajı | Mevcut, ancak `sql_runner` düzeltmesinden önce derlenmişti |
| `postgres:16.15-bookworm`, `python:3.11.17-slim-bookworm` | Mevcut |

### Kimlik bilgisi uyumu

- `.env` 2026-10-23 13:09 UTC'de yazılmış ve sonra değişmemiş. Volume 13:20 UTC'de bu `.env` ile başlatılmış.
- `pg_hba.conf` ağ bağlantılarında `scram-sha-256` istiyor. Python konteynerinden parola ile bağlantının başarılı olması uyumu doğruluyor; yeni parola üretilmedi.

### Yeniden oluşturulanlar

- `up.ps1` ile: `app` imajı yerel motorda yeniden derlendi (önbellekten; ağ indirmesi olmadı), `olist-sales-intelligence_default` ağı ve `db` konteyneri oluşturuldu.
- `dashboard.ps1` ile `dashboard` konteyneri oluşturuldu.
- Volume yeniden oluşturulmadı. PostgreSQL "Database directory appears to contain a database; Skipping initialization" diyerek mevcut veriyi kullandı.

### Veri kaybı değerlendirmesi

- Volume'da bulunanlar: `olist` ve `olist_test` veritabanları, `meta`/`staging`/`dw` şemaları ve `meta.schema_migrations` içinde `010_create_schemas.sql` (2026-10-23 13:22:06 UTC).
- `staging`/`dw` altında 0 tablo var. Aşama 2'de henüz veri yüklenmediği için beklenen durum bu.
- **Veri kaybı tespit edilmedi.** Silinen nesneler (konteyner, ağ) veri içermiyordu.

### Doğrulama sonuçları (gerçek çıkış kodlarıyla)

Betikler `try/catch` ile çalıştırıldı: betik başarısızlıkta istisna fırlatır. Tam çıktı dosyaya yazıldı, filtre yalnızca özet için kullanıldı.

| Kontrol | Sonuç |
|---|---|
| `up.ps1` | Başarılı (24 s); `db` healthy, son sağlık kontrolü çıkış kodu 0; port yayınlanmamış |
| `etl.ps1 check` (Python konteynerinden SELECT) | Başarılı: PostgreSQL 16.15, veritabanı `olist`, kullanıcı `olist` |
| `etl.ps1` (×2) | Başarılı; ikisinde de "Uygulanacak yeni SQL dosyası yok" (dosya volume'da zaten uygulanmıştı) |
| `test.ps1 -v` | Başarılı: **19 passed** |
| Negatif kontrol: `etl.ps1 no-such-command` | Beklendiği gibi **başarısız** (çıkış 2). Başarı ölçümünün hatayı yakaladığını gösteriyor |
| `dashboard.ps1` | Başarılı; konteyner healthy; port yalnızca `127.0.0.1:8501` |
| `GET http://127.0.0.1:8501/_stcore/health` | 200 `ok` |
| `GET http://127.0.0.1:8501/` | 200 (yalnızca Streamlit kabuk HTML'i; içerik tarayıcıda çizilir) |
| Wi-Fi IP'si üzerinden TCP 8501 | Bağlanamadı (beklenen: yalnızca yerel erişim) |
| Çalışan dashboard konteynerinde `AppTest` ile `dashboard/app.py`, gerçek `olist` veritabanına karşı | 0 istisna, 0 hata; uyarı "Analiz panelleri henüz geliştirilmedi..."; metrikler PostgreSQL 16.15 / `olist` / `olist`; SQL tablosunda `010_create_schemas.sql` |
| `down.ps1` → `up.ps1` → `etl.ps1` | `down` sonrası 0 konteyner, volume yerinde; yeniden başlatınca healthy ve SQL kaydı korunmuş |

Yapılmayan kontroller:

- Dashboard'un tarayıcıdaki görüntüsü **görülmedi**; içerik `AppTest` ile doğrulandı.
- `reset.ps1` **çalıştırılmadı**, çünkü volume'u siler ve kullanıcı volume'ların korunmasını istedi.
- Boş veritabanına ilk uygulama bu oturumda gerçek veritabanında tekrarlanmadı. Bu davranışı test veritabanındaki yalıtılmış şemalarda `test_apply_runs_each_file_once` doğruluyor; 2026-10-23'te gerçek veritabanında da gözlendi.

İnternet/DNS sorunu bu oturumda yaşanmadı (imaj önbellekten derlendi, temel imajlar yereldeydi).

### Ücretsiz kullanım

- Kural `CLAUDE.md` dosyasına eklendi.
- Builder'lar yalnızca yerel `docker` sürücülü (`default`, `desktop-linux`); Build Cloud yok.
- Projede ücretli servis, bulut bağımlılığı veya yapay zekâ API'si yok.

### Eksikler / sonraki aşama

- Aşama 2 tamamlandı.
- Aşama 3: Olist CSV'lerinin `data/raw/` klasörüne indirilmesi, staging tablolarının ve ETL yükleme adımının yazılması.
- Docker Desktop otomatik başlamıyor; her oturumda elle açılması gerekiyor (isteğe bağlı ayar: Settings > General > "Start Docker Desktop when you sign in").
- Git deposunda henüz commit yok.

## Aşama 3 — Kaynak profili, veri ambarı ve metrik tanımları (tamamlandı, 2026-10-24)

### Veri erişimi

- `data/raw` boştu. `Downloads` klasöründe yalnızca tek dosyalık bir `olist_customers_dataset.csv.zip` vardı; bu dosyaya dokunulmadı.
- Resmî Kaggle API'si (`/api/v1/datasets/download/olistbr/brazilian-ecommerce`) herkese açık veri setini giriş istemeden sundu (302 ile Kaggle'ın imzalı depolama adresine yönlendirme). Kimlik doğrulama aşılmadı.
- Meta veri: sahibi Olist, lisans CC BY-NC-SA 4.0, sürüm 2, `totalBytes` 126.186.995.
- Arşiv boş bir geçici klasöre indirildi (44.717.580 bayt, SHA-256 `967e41e0…a784`). 9 girdinin hepsinin düz dosya adı taşıdığı (klasör veya `..` içermediği) doğrulandı; açılmış toplam boyut `totalBytes` ile aynı. Yalnızca CSV'ler `data/raw` klasörüne çıkarıldı. Dosya özetleri `meta.etl_run_files` tablosunda.

### Profil (`docs/data_profile.md`, `python -m etl profile` ile dosyalardan üretilir)

Tasarımı belirleyen ölçümler:

- **Anahtarlar:**
  - `(order_id, order_item_id)` benzersiz; `order_item_id` 1..n kesintisiz.
  - `orders.customer_id` benzersiz: 1 sipariş = 1 `customer_id`.
  - 2.997 `customer_unique_id` değerinin birden fazla `customer_id` değeri var.
  - `review_id` benzersiz değil (789); anahtar `(review_id, order_id)` çifti.
- **Eksik ilişkiler ve boşluklar:**
  - 775 siparişin kalemi, 1 siparişin ödemesi, 768 siparişin yorumu yok.
  - 610 ürünün kategorisi boş; 2 kategorinin İngilizce çevirisi yok.
- **Zaman:**
  - `delivered` durumundaki 8 siparişin teslim tarihi boş; 6 iptal siparişin teslim tarihi dolu.
  - 166 siparişte kargoya veriliş zamanı satın almadan önce.
  - Tahmini teslim zamanı her satırda 00:00:00.
- **Biçimler:**
  - Para alanlarında en fazla 2 ondalık hane; en büyük değer 13664.08.
  - Posta kodları 5 haneli metin; baştaki sıfırlar anlamlı.
  - `product_category_name_translation.csv` dosyasının başında BOM var.

### Oluşturulanlar

- **Şema SQL dosyaları:**
  - `sql/020_staging_tables.sql`: kaynak kolon adları korunur, tüm değerler metin.
  - `030_dw_dimensions.sql`: `dim_date`, `dim_customer`, `dim_product`, `dim_seller`.
  - `040_dw_facts.sql`: `fact_orders` (sipariş), `fact_sales` (kalem), `fact_payments` (ödeme).
  - `050_reporting_views.sql`: view'ler ve `mv_monthly_sales`.
- **Dönüşüm:** `sql/transform/load_dw.sql`.
- **Belgeler:** `docs/metric_definitions.md`, `docs/data_dictionary.md`, `docs/er_diagram.md` (Mermaid).
- **Test verisi:** `tests/fixtures/olist_sample/` (sentetik).

### Kararlar

- `fact_payments` istenen listenin dışında eklendi. Gerekçe: ödeme türü analizi için ödeme grain'i gerekiyor; sipariş toplamı yine `fact_orders` içinde.
- **Yorumlar:** ayrı olgu tablosu oluşturulmadı; `fact_orders` içine `review_count` ve `review_score_avg` olarak toplandı.
- **geolocation:** yalnızca staging'de tutuluyor; posta kodu başına çok satır olduğundan boyut olarak modellenmedi.
- **Doğal anahtarlar:** dw'de vekil (surrogate) anahtar yerine doğal metin anahtarlar kullanılıyor. Anahtarlar 32 hex olarak doğrulanıyor ve sabit.
- **Para:** `numeric(12,2)`.
- **Zaman:** `timestamp without time zone`; saat dilimi dönüşümü yok.

### Doğrulanmamış varsayımlar

- Zamanlar Brezilya yerel saati.
- Para birimi BRL.
- Her kalem satırının bir adet olduğu. Kaynakta quantity yok; metrik bu yüzden "kalem sayısı" olarak adlandırıldı.
- Ödeme farklarının nedeni (taksit faizi, kupon vb.) bilinmiyor.

### Test sonuçları (2026-10-24)

- 33 test geçti. Kapsam:
  - Boş bir veritabanında sıfırdan şema kurulumu (`test_schema_fresh_db`).
  - Çoğalmama gösterimi: 3 kalem × 2 ödeme × 2 yorum.
    - Doğrudan birleştirme 12 satır, ürün tutarı 1.002,00 ve ödeme tutarı 1.654,50 üretiyor.
    - Model 250,50 ürün tutarı ve 275,75 ödeme tutarı veriyor.
- Gerçek veriyle ilk yükleme başarılı; o sürümdeki 4 SQL doğrulamasının hepsi geçti.
- Bu oturum yükleme sonrası `ECONNRESET` ile kesildi. Belgeler (metrik tanımları, veri sözlüğü, ER diyagramı), README lisans notu ve bu kayıt Aşama 4 oturumunda tamamlandı.

## Aşama 4 — Yükleme hattı (tamamlandı, 2026-10-24)

### Mevcut uygulamayla karşılaştırma ve tamamlananlar

| Gereksinim | Önce | Şimdi |
|---|---|---|
| Dosya ve zorunlu kolon kontrolü | Yalnızca birebir başlık eşleşmesi | Eksik, fazla ve tekrarlanan kolonlar ayrı ayrı bildiriliyor; tüm başlıklar herhangi bir tablo boşaltılmadan önce kontrol ediliyor |
| Kimlik ve posta kodu metin | Var | Korundu; biçim doğrulaması dönüşümde |
| Tarih, boş değer, sayı kuralları | Hatalı değer tüm yüklemeyi durduruyordu | Açık kurallar (`docs/etl_pipeline.md`); hatalı satır nedeniyle reddediliyor |
| Kaynak dosyalar değiştirilmez | Salt okunur bağlama | + başta ve sonda SHA-256 karşılaştırması |
| Hatalı kayıt raporu | Yok | `meta.etl_rejected_rows`: kaynak satır, neden listesi, ham kayıt |
| Tekrar / çelişkili anahtar | Yok | Birebir tekrar ayıklanıyor; çelişkili anahtarın tüm sürümleri reddediliyor |
| Kategori çevirisi | Yalnızca NULL | `category_label` ve `category_translation_status` politikası (CHECK ile zorunlu) |
| COPY FROM STDIN | Var | Korundu |
| run_id ve çalışma kaydı | Yok | `meta.etl_runs`, `etl_run_files`, `etl_run_checks` |
| İşlem sınırları | staging ve dw ayrı işlemlerde; `TRUNCATE` | Tek işlem; dw `DELETE` (MVCC); MV `CONCURRENTLY`; çalışma kaydı ayrı işlemde |
| Kalite kontrolleri | 4 SQL kontrolü | 8 hata kontrolü + 5 bilgi raporu |

Yeni ve değişen dosyalar:

- **Şema:** `sql/060_etl_run_log.sql`, `070_staging_row_ids.sql`, `080_product_category_policy.sql`, `090_reporting_payment_differences.sql`.
- **Kod:** `etl/pipeline.py` (yeni); `etl/load_staging.py`, `etl/transform.py`, `etl/__main__.py` (genişletildi).
- **SQL:**
  - `sql/transform/load_dw.sql`: doğrulama, ret ve tekrar katmanı eklendi; boyut ve olgu mantığı aynı kaldı.
  - `sql/tests/050`–`070`: yeni kontroller.
  - `sql/reports/*`: yeni raporlar.
- **Test:** `tests/test_pipeline.py`, `tests/fixtures/olist_quality_sample/`.
- **Belge:** `docs/etl_pipeline.md`.

### Mevcut testlerde yapılan değişiklikler (gerekçeli)

- **`loaded_sample` fikstürü:** artık `run_pipeline` kullanıyor, çünkü dönüşüm artık bir `run_id` istiyor. Beklenen değerler değişmedi.
- **`sql/tests/010` ve `030`:** beklenen değerler artık staging'in tamamından değil, kabul edilen satırlardan hesaplanıyor. Bunun nedeni ret politikası; kontrollerin sıkılığı azalmadı.
- **`test_schema_fresh_db`:** beklenen nesne listesine yeni `meta` tabloları ve `v_order_payment_differences` eklendi.

### Hatalar ve düzeltmeler

- **Değerlendirme sırası:** `A OR B` / `A AND B` içindeki `::int` ve `::timestamp` dönüşümleri, PostgreSQL'de değerlendirme sırası garanti olmadığı için bozuk değerde tüm yüklemeyi hata ile durdurabilirdi. Sırayı garanti eden iç içe `CASE` yapısına geçildi (kod incelemesinde bulundu).
- **UUID parametresi:** psycopg2 `uuid.UUID` tipini SQL'e dönüştürmüyor; run_id metin olarak geçiriliyor.
- **Ölçüm hatası:** gerçek veri karşılaştırmasının ilk denemesinde `psql -F " "` argümanı PowerShell tarafından bozuldu ve iki boş dosya karşılaştırıldı. Sonuç **geçersiz sayıldı**; ölçüm Bash ile yeniden yapıldı.

### Test sonuçları

- pytest: **46 passed**. Önceki 33 test + `test_pipeline.py` içindeki 13 yeni test.
- Kalite örneği (`olist_quality_sample`): kaynak / kabul / ret / tekrar sayıları elle hesaplanan değerlerle aynı.

  | Tablo | Kaynak | Kabul | Ret | Tekrar |
  |---|---:|---:|---:|---:|
  | orders | 10 | 5 | 5 | 0 |
  | order_items | 11 | 6 | 5 | 0 |
  | order_payments | 11 | 6 | 4 | 1 |
  | customers | 9 | 8 | 0 | 1 |
  | sellers | 4 | 2 | 2 | 0 |
  | order_reviews | 6 | 5 | 1 | 0 |

  - Ret nedenleri doğru: `invalid_purchase_timestamp`, `customer_not_found`, `product_not_found` → `item_rejected` → `order_rejected`, `conflicting_key`, `exact_duplicate`, `invalid_review_score`.
  - Teslim edilmiş satış metrikleri temiz örnekle aynı. Tekrar ödeme, sipariş toplamını ikiye katlamadı.
- Testle doğrulanan davranışlar:
  - İkinci yükleme dw tablolarının ve raporlamanın içerik özetlerini değiştirmiyor; iki çalışmada da 19 ret/tekrar kaydı var.
  - COPY hatasında (fazla kolonlu satır) önceki veri ve staging korunuyor; çalışma `failed` ve dosya bilgileri kayıtlı.
  - Kalite kontrolü hatasında farklı veriyle tam yenilemenin tamamı geri alınıyor; kontrol sonucu rollback'e rağmen kayıtlı, ret kayıtları veriyle birlikte geri alınmış.
  - Eksik zorunlu kolon (`freight_value`) bildiriliyor ve veri değişmiyor.
  - Yükleme işlemi sürerken ayrı bir oturum kilit beklemeden **önceki** veriyi görüyor (yazan işlem 2 sipariş, okuyan 3).

Gerçek veri (`.\scripts\etl.ps1`):

| Çalışma | Durum | Süre |
|---|---|---:|
| `00b9ad99…` (060–090 şema dosyaları uygulandı) | succeeded | 75,4 s |
| `1ccf4302…` | succeeded | 83,3 s |
| `77ff75fa…` | succeeded | 76,8 s |
| `5b1bdbc0…` (bilerek eklenen başarısız kontrolle) | **failed** | 71,4 s |

- Tüm dosyalarda kaynak = staging = kabul; 0 ret, 0 tekrar. Bu, profildeki "yetim ilişki ve çelişkili anahtar yok" bulgusuyla tutarlı.
- 8 hata kontrolünün tamamı geçti.
- **Tekrar yükleme:** `1ccf4302` sonrası ve `77ff75fa` sonrası özetler birebir aynı (Bash ile ölçüldü). Kapsam: 7 dw tablosu, `mv_monthly_sales` ve `v_sales_kpis`; her biri için satır sayısı ve tüm satırların MD5 özeti.
- **Başarısız yükleme:** `5b1bdbc0` tüm veriyi yeniden yükleyip kontrolde düştü. Özet, çalışmadan önceki özetle birebir aynı. Hata nedeni ve 7 kontrol kaydı korundu; `meta.current_run_id()` son başarılı çalışmayı gösteriyor.
- `.\scripts\etl.ps1 runs` ve `.\scripts\etl.ps1 verify` çalıştırıldı ve başarılı (7/7).
- Dashboard yeni imajla healthy.

### Gerçek veri metrikleri (`77ff75fa`)

| Metrik | Değer |
|---|---:|
| Teslim edilmiş sipariş | 96.478 |
| Müşteri (`customer_unique_id`) | 93.358 |
| Kalem | 110.197 |
| Ürün satış tutarı | 13.221.498,11 |
| Kargo tutarı | 2.198.275,64 |
| Ödeme tutarı | 15.422.461,77 |
| Ortalama sepet | 137,04 |
| Ortalama teslimat süresi | 12,56 gün (8 sipariş ölçülemedi) |
| Geç teslimat oranı | 0,0677 |
| Tekrar satın alma oranı | 0,0300 |

- RFM gözlem tarihi: 2018-08-30.
- Ödeme farkı (kapsamda, birebir karşılaştırma): 570 sipariş. Ayrıntı: `docs/metric_definitions.md`.

### Yapılmayan veya doğrulanmayan

- **Artımlı yükleme uygulanmadı;** her çalışma tam yenileme.
- Dashboard'un yükleme sırasında tarayıcıda nasıl göründüğü **görülmedi**. Okuyan oturum davranışı veritabanı düzeyinde testle doğrulandı.
- Gerçek veride hiç ret çıkmadı. Ret mantığı yalnızca sentetik kalite örneğiyle sınandı.
- `DELETE` tabanlı yenilemenin ölü satır ve disk etkisi ölçülmedi (autovacuum'a bırakıldı).
- Proje kodu için lisans tanımlı değil (kullanıcı kararı).
- Git deposunda henüz commit yok.

## Aşama 5 — Raporlama katmanı (tamamlandı, 2026-10-24)

Ayrıntılı belge: `docs/reporting.md`.

### Oluşturulanlar

Her analiz ayrı ve açıklamalı bir SQL dosyasında; iş mantığı PostgreSQL'de.

| Dosya | Nesne | Teknik |
|---|---|---|
| `sql/100_report_monthly_sales_growth.sql` | `reporting.v_monthly_sales_growth` | `dim_date` ile satışsız aylar, `LAG`, sıfır payda kuralı (`growth_status`) |
| `sql/110_report_customer_rfm.sql` | `reporting.fn_customer_rfm(as_of date)` | CTE + window function; `as_of` zorunlu; `purchase_ts < as_of`; frequency = farklı sipariş |
| `sql/120_report_category_sales.sql` | `reporting.mv_category_sales` | `SUM() OVER (... ROWS ...)`; eşitlikte `category_label`; UNIQUE index |
| `sql/130_report_delivery_performance.sql` | `reporting.v_delivery_performance` | sipariş seviyesi, `CASE`, `GROUP BY ROLLUP` |
| `sql/140_report_repeat_purchase.sql` | `reporting.v_repeat_purchase` | `EXISTS`, `GROUPING SETS` |
| `sql/150_report_routines.sql` | `reporting.monthly_summary`, `meta.report_refresh_runs`, `sp_load_monthly_summary(year)`, `refresh_report_objects()`, `sp_refresh_reports()` | PL/pgSQL |
| `sql/tests/080_reporting_analyses_consistent.sql` | ETL hata kontrolü | Her analizin toplamı `v_sales_kpis` ile aynı olmalı |

Diğer değişiklikler:

- **Dönüşüm:** `sql/transform/load_dw.sql` sonunda yalnızca `mv_monthly_sales` yerine `reporting.refresh_report_objects()` çağrılıyor. Böylece tüm rapor nesneleri ETL işlemiyle birlikte (atomik) yenileniyor.
- **CLI:** `python -m etl refresh-reports` (`.\scripts\etl.ps1 refresh-reports`): autocommit modunda `CALL`.
- **Test:** `tests/test_reporting.py` (18 test) ve sentetik `tests/fixtures/olist_reporting_sample/`. Beklenen sonuçlar CSV'lerden elle hesaplandı.
- **Belgeler:** `docs/reporting.md`; `docs/metric_definitions.md` (RFM `as_of` kuralı); `docs/data_dictionary.md`; README.

### Kararlar

- **RFM puanlaması:**
  - R ve M için `NTILE` yerine eşitlik güvenli kümülatif dilim kullanıldı: eşit değerler aynı puanı alıyor, sonuç satır sırasına bağlı değil, tam sayı aritmetiğiyle hesaplanıyor.
  - F için sabit eşik (1..5+) kullanıldı; gerçek veride müşterilerin %97'si tek siparişli.
- **RFM tarihi:** `as_of` gözlem gününün başı; aynı gündeki satın almalar dışarıda. Önerilen `as_of` = `v_rfm_observation.observation_date`.
- **Segmentler:** 8 kural, ilk eşleşen kural geçerli (`docs/reporting.md`).
- **Büyüme:** önceki ay 0 ise `growth_rate` NULL ve `previous_month_zero`; ilk ay `no_previous_month`. Mutlak fark her zaman veriliyor.
- **Mantık tek yerde:** Yenileme mantığı işlem kontrolü içermeyen bir fonksiyonda (`refresh_report_objects`); ETL içinde de kullanılabiliyor. `COMMIT` yalnızca `sp_refresh_reports` içinde ve EXCEPTION bloğunun dışında.
- **CONCURRENTLY:** yalnızca MV doldurulmuşsa ve kolon adlarından oluşan, `WHERE` içermeyen bir UNIQUE index varsa kullanılıyor. Aksi halde normal REFRESH yapılıyor ve kullanılan yöntem kaydediliyor.
- **Ek nesneler:** `mv_category_sales` ve `monthly_summary` yeni nesneler. `v_monthly_sales_growth`, `mv_monthly_sales` ile çakışmıyor: satışlı aylarda iki nesnenin değerlerinin aynı olduğu `080` kontrolüyle doğrulanıyor.

### PostgreSQL 16 kuralları

Belgeden okunan kurallar (iki resmî sayfa):

- `CONCURRENTLY` doldurulmuş bir MV ve uygun bir UNIQUE index gerektirir; `WITH NO DATA` ile kullanılamaz.
- İşlem kontrolü yalnızca üst düzey veya araya başka komut girmeyen iç içe `CALL`/`DO` içinde yapılabilir.
- EXCEPTION bloğu içinde işlem bitirilemez.

Belgede bulunmayan ve **testle doğrulanan** davranış: açık bir `BEGIN` bloğu içinden yapılan `CALL`'da prosedürdeki `COMMIT` `invalid transaction termination` hatası veriyor ve hiçbir kayıt kalmıyor.

### Bulunan ve düzeltilen

- **RFM hata mesajı:** "CURRENT_DATE kullanılmaz" testi yorumları atlıyor ama `RAISE` mesajı bu kelimeyi içeriyordu; test yanlış biçimde başarısız olacaktı. Test gevşetilmedi, mesaj değiştirildi (test çalıştırılmadan önce, kod incelemesinde bulundu).
- **Fikstür üretimi:** Ilk deneme çok sayıda komut ikamesi içerdiği için güvenlik kontrolü tarafından engellendi; komut çalışmadı. Dosyalar ikame içermeyen bir üreteç betiğiyle (geçici klasörde) oluşturuldu.

### Mevcut testlerde değişiklik

Beklenen nesne listeleri yeni nesnelerle güncellendi; beklenen değerler değişmedi.

- `test_schema_fresh_db`: yeni view'ler, `mv_category_sales`, `report_refresh_runs`, `monthly_summary`.
- `test_pipeline`: hata kontrolleri listesine `080` eklendi.

### Test sonuçları

pytest: **64 passed** (önceki 46 + 18 yeni). Kapsanan senaryolar:

- **Analizler:**
  - Elle hesaplanan KPI'lar.
  - Aylık seri: satışsız Şubat ve Haziran; sıfır paydalı Mart.
  - Çoklu ödeme.
  - Kategori eşitliği ve `ROWS` kümülatifi (350 / 500).
  - ROLLUP ve sıfır paydalı Mayıs.
  - `EXISTS` ile tekrar alım.
- **RFM:**
  - Gözlem tarihinde (2017-05-11) değerler.
  - Tarih filtresi: 2017-03-04 / 2017-03-03 / 2016-12-31.
  - `as_of` NULL hata veriyor.
  - Kodda `CURRENT_DATE` yok.
- **Rutinler:**
  - `sp_load_monthly_summary` hem ayrı hem aynı işlemde iki kez çağrılınca çoğaltmıyor; tarih boyutunda olmayan yıl reddediliyor.
  - MV önkoşulları sağlanıyor.
  - Boş veritabanında `initial_population` → `concurrently`.
  - Tekrar `sp_refresh_reports` çağrıları sonucu değiştirmiyor.
  - Açık işlem içinden çağrı reddediliyor.
  - Kilit zaman aşımında `failed` kaydı ve `55P03` kodu kalıcı, `monthly_summary` değişmemiş.

Gerçek veri:

- **ETL (`d899f00e…`):** 100–150 dosyaları uygulandı; succeeded, 81,2 s; 9/9 hata kontrolü geçti (`080` dahil). dw içerik özeti çalışmadan önceki ile birebir aynı.
- **`refresh-reports` ×2:** `refresh_id` 1 ve 2, ikisi de succeeded; iki MV `concurrently` yenilendi; `monthly_summary` 2016, 2017, 2018 yılları için yüklendi (27 ay); ~1,4 s.
- **Gözlenen sonuçlar:**
  - 2016-11 satışsız. 2016-12 `previous_month_zero`.
  - 2018-09/10/11 sıfır satışla görünüyor: tarih boyutu tahmini teslim tarihleri yüzünden uzuyor.
  - 74 kategori; satışın %80'ine 18. kategoride ulaşılıyor.
  - Geç teslim oranı 2016 0,0112 / 2017 0,0565 / 2018 0,0773.
  - Tekrar alım oranı 0,0300.
  - RFM (as_of 2018-08-30): 93.358 müşteri; R ve M dilimleri ~18,2–19,0 bin; F=1 olan 90.557 müşteri.
- `.\scripts\etl.ps1 verify` 8/8 geçti; dashboard yeni imajla healthy.

### Yapılmayan / açık noktalar

- **Dashboard:** bu nesneleri henüz göstermiyor (sonraki aşama).
- **Performans:** ölçülmedi. `fn_customer_rfm` tek bir çağrıda ~0,92 s sürdü; bu bir benchmark değil.
- **Tarihsel durum:** Geçmiş bir `as_of` için o tarihteki sipariş durumu bilinmiyor; filtre yalnızca satın alma zamanına uygulanıyor.
- **Kısmi aylar:** Veri setinin kısmi ve veri sonrası aylarının analizden dışlanıp dışlanmayacağına analiz/dashboard aşamasında karar verilmeli.
- **Git:** depoda henüz commit yok.

## Aşama 6 — Performans deneyleri (tamamlandı, 2026-10-24)

Rapor: `docs/performance.md`. Ham ölçümler: `docs/perf/results/` (B çalışması), `docs/perf/run_A_results/` (A çalışması), planlar `docs/perf/plans/`, otomatik özet `docs/perf/summary.md`.

### Oluşturulanlar

- **Deney paketi** `perf/`:
  - `harness.py`: ölçüm, sonuç MD5, EXPLAIN, zaman aşımı.
  - `experiments.py`: E1–E6, katalog, MV maliyetleri.
  - `load_compare.py`: L1.
  - `partition.py`: P1.
  - `summary.py`: özet üretimi.
  - `__main__.py`.
- **Komut:** `scripts/perf.ps1` (`.\scripts\perf.ps1 --rebuild`). Ayrı `olist_perf` veritabanı gerçek `data/raw` dosyalarından yükleme hattıyla kurulur; ana `olist` veritabanına dokunulmaz.
- **Testler:** `tests/test_perf_harness.py` (3 test).
- **Düzenleme:** `compose.yaml` ve `Dockerfile` içine `perf/` eklendi.

### Yöntem (özet)

- Gerçek veri; PostgreSQL 16.15; Docker VM'i 16 CPU / 7.786.148 kB.
- Başlangıç: PK/UNIQUE (13) korunur, 6 ek dw indeksi kaldırılır (yalnızca `olist_perf`); bir kez `VACUUM (ANALYZE)`.
- Ölçüm: 2 ısınma + 7 ölçüm; medyan / min / max. EXPLAIN ayrı çalıştırılır.
- Önbellek temizlenmedi: tüm ölçümler sıcak önbellek.
- Her değişiklik başlangıçtan uygulanır ve geri alınır; sonuç MD5 ile karşılaştırılır.
- `statement_timeout` 60 s; aşan ölçüm "zaman aşımı" olarak kaydedilir.

### Sonuçlar (B çalışması, medyan ms)

| Deney | Başlangıç | En iyi değişiklik | Not |
|---|---:|---:|---|
| E1 kişi sipariş geçmişi | 12,918 | B-tree 0,955 (13,53×) | Yazma maliyeti 51,4 → 428,0 ms |
| E2 satıcı + tarih | 16,813 | INCLUDE 0,824 (20,40×) | Tek kolon 5,96×, birleşik 13,36× |
| E3 açık siparişler | 15,281 | partial 0,524 (29,16×) | `order_status` indeksi **kullanılmadı** (1,01×), yazma 84,6 → 200,8 ms |
| E4 tekrar alım | **zaman aşımı > 60 s** | tek geçiş 405,891 | İndeksli EXISTS 1.517,952; mevcut view indekse bağımlı |
| E5 kategori MV | 568,796 | MV okuma 0,607 (937×) | Yenileme ~549–564 ms, 40.960 bayt, güncellik yenilemeye bağlı |
| E6 RFM `work_mem` 64 MB | 1.571,508 | 1.627,023 (**0,97×**) | Diske taşma 7.292 → 0 blok, hızlanma yok |
| L1 yükleme (112.650 satır) | COPY 1.262,6 | — | `to_sql` (None/10000) 3.715,595; `multi`/1000 15.460,695 |
| P1 partitioning | ay 12,361 / tüm 29,803 | ay 8,026 (1,54×) | Tüm satırlar 36,808 (**0,81×**); ana modele eklenmedi |

Tekrarlanabilirlik:

- İki bağımsız tam çalışmada (A, B) sonuç MD5'leri birebir aynı; deneylerin yönü ve sıralaması aynı.
- 1 ms altındaki medyanlarda ~%32'ye kadar fark var (gürültü).
- E6'nın yönü değişti (A 1,04×, B 0,97×); bu yüzden "etki yok" olarak raporlandı.

### Bulunan ve düzeltilen sorunlar

1. **Boş veritabanına ilk yüklemede istatistik eksikliği (F1, tek seferlik tanı):**
   - **Belirti:** `080` kalite kontrolü 8 dk 59 s'den uzun çalıştı ve iptal edildi; çalışma 639,748 s sonunda `failed` kaydedildi, veri korundu.
   - **Neden:** İşlem içinde dw tabloları hiç ANALYZE görmemişti; planlayıcı satır sayısını yanlış tahmin ediyordu.
   - **Düzeltme:** `sql/transform/load_dw.sql` içine, işlem içinde `ANALYZE` (q_* ve dw tabloları).
   - **Doğrulama:** Düzeltmeden sonra boş veritabanına ilk yükleme iki kez başarılı: 93,135 s ve 94,952 s. `reset.ps1` sonrasındaki ilk ETL de aynı hatadan etkilenirdi.
2. **`v_repeat_purchase` indeksiz kalınca kullanılamaz hale geliyor:** başlangıçta zaman aşımı, tahmini maliyet 252.438.047,44. İlk perf çalışması bu sorguda 8+ dakika takıldı ve durduruldu.
   - **Düzenekteki düzeltme:** sorgu başına 60 s zaman sınırı; zaman aşımı süre uydurulmadan kaydediliyor.
   - **E4'e eklenen ölçüm:** ana modeldeki indeks durumu da ölçüldü.
3. **Başlangıç kaydının eksik kalması:** `--rebuild` olmadan yapılan A çalışması, kaldırılan indeksleri listelemiyordu. Tam kayıt için `--rebuild` ile B çalışması yapıldı; rapor B'ye dayanıyor.

### Doğrulamalar

- pytest: **67 passed** (önceki 64 + 3 perf düzeneği testi). Testler ölçümler bittikten sonra çalıştırıldı.
- Düzeltilmiş ETL, asıl `olist` veritabanında başarılı oldu (run_id `1b2cff1f…`): 9/9 kontrol geçti, dw içerik özeti öncekiyle aynı.
- Dashboard yeni imajla healthy.

### Kararlar

- **Ana model değiştirilmedi** (indeksler ve view'ler aynı). Ölçüme dayalı öneriler `docs/performance.md` "Öneriler" bölümünde:
  - `dim_customer_unique_id_idx` korunmalı.
  - `v_repeat_purchase` tek geçişli toplamayla değiştirilmeli.
  - `fact_orders_status_idx` kaldırılmalı.
  - `fact_sales_seller_idx` birleşik indeksle değiştirilmeli (dashboard kullanımına göre).
  - Partitioning ve `work_mem` değişikliği eklenmemeli.
- Bu öneriler kullanıcı onayı ve dashboard sorgu desenleri bilindikten sonra uygulanmalı.

### Açık noktalar

- **Ölçülmeyen indeksler:** `fact_sales_product_idx`, `fact_sales_purchase_date_idx`, `fact_orders_purchase_date_idx`.
- **Kapsam dışı ölçümler:** Soğuk önbellek, eşzamanlı yük ve büyütülmüş sentetik veri ölçülmedi.
- **ETL süresi:** Asıl veritabanında düzeltilmiş ETL tek çalışmada 118,148 s sürdü (5. aşamadaki tek çalışma 81,2 s). Fark ölçülmedi ve nedeni belirlenmedi.
- **Git:** depoda henüz commit yok.

## Aşama 7 — Dashboard (tamamlandı) — 2026-10-24 / 2026-10-25

Ayrıntılı belge: `docs/dashboard.md`.

### Tamamlananlar (gerçekten çalıştırıldı)

- **Yeni migration'lar** (önceden uygulanmış dosyalar değiştirilmedi):
  - `sql/160_report_dashboard_functions.sql`: parametreli dashboard fonksiyonları (`fn_overview_kpis`, `fn_monthly_sales`, `fn_category_sales`, `fn_delivery_by_region`, `fn_delivery_monthly`, `fn_repeat_purchase`, `fn_rfm_segments`); dashboard view'leri; `v_data_coverage`, `v_data_freshness`; `reporting.state_region` (IBGE bölgeleri).
  - `sql/170_report_repeat_purchase_single_pass.sql`: `v_repeat_purchase` tek geçişli sürüm. Gerçek veride eski ve yeni sürüm iki yönlü `EXCEPT ALL` ile karşılaştırıldı: 0 / 0 fark, 24 / 24 satır.
  - `sql/180_dashboard_reader_role.sql`: `olist_reporting_reader` (NOLOGIN), en az yetki; reporting rutinlerinden PUBLIC EXECUTE kaldırıldı.
- **Kalite kontrolü:** `sql/tests/090_dashboard_functions_consistent.sql`. Gerçek veride ETL `1feee717…` succeeded (137,1 s, tek ölçüm), 10/10 kontrol geçti.
- **Dashboard rolü:**
  - `etl/dashboard_role.py` ve `python -m etl setup-dashboard-role`: rol `.env`'deki `DASHBOARD_DB_USER/PASSWORD` ile oluşturuluyor; salt okunur oturum ve 30 s sorgu sınırı.
  - `new-env.ps1` eksik anahtarları ekliyor; mevcut parola değişmedi.
  - Dashboard servisi `olist_dashboard` ile bağlanıyor.
- **Uygulama:** `dashboard/` (`app.py`, `data.py`, `ui.py`, `filters.py`, `views.py`, `page_*.py`, `verify.py`).
  - Önbellek 600 s; tazelik 60 s; önbellek anahtarına `run_id` giriyor.
  - Durum mesajları: boş sonuç, yüklenmemiş veri, bağlantı hatası.
  - BRL etiketi; tema `STREAMLIT_THEME_*` ile.
- **Testler:** 83/83 geçti (`tests/test_dashboard.py`: 17 test). Kapsam:
  - Sayfaların çizilmesi.
  - 4 filtre senaryosunda KPI = elle hesap = doğrudan SQL.
  - Kategori filtresinde çoğalmama.
  - Boş sonuç, yüklenmemiş veri ve bağlantı hatası (parola görünmüyor).
  - Parametreli sorgu.
  - Rol yetkileri: dw/meta/staging 42501; rutinler 42501; salt okunur.
- **Sayfalar (AppTest):** Gerçek veride ve salt okunur rolle dört sayfa AppTest ile hatasız çizildi.
- **Kabul ölçütü:** `docs/dashboard_verification.json`: gerçek veride 7 örnek filtrede uygulama KPI'ları, reporting fonksiyonlarını kullanmayan doğrudan SQL ile 7/7 eşleşti.
- **Performans:**
  - D1 (`docs/perf/results/D1_dashboard_queries.json`): dashboard sorguları yalnızca iki tarih indeksini, dar aralıklarda kullanıyor.
  - F2 (`F2_etl_delete_fk_checks.json`, n=1): `fact_sales_product_idx` olmadan ETL'deki `DELETE dim_product` 120 s sınırını aştı, indeksle 592,7 ms; `fact_sales_seller_idx` olmadan 13.223 ms, indeksle 164,4 ms.
  - Karar: hiçbir indeks eklenmedi veya kaldırılmadı (`docs/performance.md`, Öneriler).
- **Grafik kuralı:** Aylık grafik veri kapsamında bitiyor (tahmini teslim tarihlerinden gelen 2018-09..11 yok); kısmi aylar işaretli.
- **Düzeltilen hatalar:**
  - **AppTest sayfa geçişi:** AppTest çağrılabilir sayfalarda `switch_page` desteklemiyordu; sayfalar ince dosyalara (`page_*.py`) bağlandı.
  - **README bozulması:** Python düzenlemesinde `\v` kaçışı README'de bir dosya adını bozmuştu; düzeltildi ve proje genelinde kontrol karakteri taraması temiz çıktı.

### Ara kayıttaki eksikler (2026-10-25 sabahı; aşağıdaki bölümle kapatıldı)

- **Görsel kontrol yapılmadı.** Bu oturumda tarayıcı aracı yok.
  - Başsız Chromium için `tools/screenshots.py` ve `scripts/screenshots.ps1` hazır, ama hiç çalıştırılmadı.
  - Resmî `mcr.microsoft.com/playwright/python:v1.64.1-noble` imajının ilk indirmesi ağ hatasıyla kesildi; ikinci deneme oturum kapanınca sonuç kaydı bırakmadan durdu.
- **Arayüz etkileşimleri:** Gerçek tarayıcıda yapılmadı. Filtrelerle sınama yalnızca AppTest ile yapıldı.
- **Belge:** `docs/dashboard.md` "Görsel kontrol" bölümü boş.
- **Docker:** Docker motoru 2026-10-25'te kapalı bulundu.

### Görsel kontrol ve arayüz etkileşimleri (2026-10-25)

- **Ortam:** Docker Desktop başlatıldı (motor kapalıydı). `up.ps1` ve `dashboard.ps1` başarılı. Volume `olist-sales-intelligence_pgdata` ve `.env` korundu.
- **Docker imajı:** Playwright Docker imajı yerelde yoktu. Önceki indirme görevinin durduğu sanıldı ve tekrar başlatılmadı. *Düzeltme (Aşama 8):* Bu kayıt yanlıştı; görev 2.516 s sonra başarıyla bitmişti (`attempt 1 exit=0`).
- **Yedek yol:** Bilgisayarda kurulu ve imzası geçerli Google Chrome 156.0.8078.47 kullanıldı.
  - Araç: Playwright 1.64.0 (PyPI), git dışı sanal ortamda; ayrı tarayıcı indirilmedi.
  - Komut: `.\scripts\screenshots.ps1 -LocalChrome`.
- **Ekran görüntüleri:** Dört sayfa, masaüstü (1440 px) ve dar ekran (390 px) için alındı ve **tek tek incelendi**. Çıktılar `docs/screenshots/` altında: 13 PNG, `report.json`, `interactions.json`.
- **Arayüz etkileşimleri** (gerçek tıklama/yazma):
  - Eyalet RJ ve kategori `health_beauty` filtreleri.
  - Tarih aralığı 2018-Q1.
  - Kenar çubuğundan sayfa gezinme.
  - Teslimat sayfasında eyalet BA.
  - Boş sonuç (AC + `arts_and_craftmanship`).
  - Her filtrede KPI'lar ve tarayıcıda çizilmiş grafik verisi değişti. Aylık çubuk toplamı KPI ürün satış tutarına eşit.
  - RJ ve 2018-Q1 değerleri ayrıca doğrudan SQL ile eşleşti.
- **Bulunan ve düzeltilen 10 sorun** (ayrıntı `docs/dashboard.md`, "Bulunan ve düzeltilen…"):
  - Varsayılan sayfa adresinde "Page not found".
  - Uygulama adının konumu (logo).
  - Yanlış ikincil eksen başlıkları.
  - Yüzde biçimi ve düzensiz eksen değerleri.
  - Az siparişli ayların eğilimi okunmaz kılması.
  - "k"/"M" kısaltmaları.
  - Eksik eksen başlığı.
  - Dar ekranda üst üste binen etiketler: yatay çubuğa geçildi.
  - Gösterge ile eksen başlığının çakışması.
  - Düzeltme sırasında çıkan yakalanmamış `TypeError`: beklenmeyen hatalar artık Türkçe mesajla gösteriliyor; test eklendi.
- **Hatanın kaynağı:** Etkileşim ilk denemelerde iki kez başarısız oldu. İkisi de otomasyon kaynaklıydı (iletişim kutusu, tarih penceresinin açık kalması); kontrol başarılı sayılmadan önce düzeltildi ve tekrarlandı.

### Düzeltmelerden sonra gerçek sonuçlar

| Kontrol | Sonuç |
|---|---|
| `.\scripts\screenshots.ps1 -LocalChrome` | 13/13 görüntü taşmasız ve hatasız; 6 etkileşim kontrolü geçti |
| `.\scripts\test.ps1` | **84 passed** |
| `.\scripts\verify-dashboard.ps1` | Gerçek veride **7/7** eşleşti |

### Kalan eksikler / sınırlar

- **Docker yolu:** `screenshots.ps1`'in Docker yolu Aşama 7'de çalıştırılmadı. Aşama 8'de çalıştırıldı ve düzeltildi (aşağıda).
- **Tarayıcı ve ekran kapsamı:** Yalnızca Chrome (Chromium) ve 1440 / 390 px genişlik denendi. Firefox, Safari ve tablet genişliği denenmedi.
- **Görüntülerde görünmeyenler:** Hover bilgi kutuları ve "Tümü" (74 kategori) görünümü ekranda incelenmedi.
- **Erişilebilirlik:** Ekran okuyucu ve klavye erişimi sınanmadı.
- **İndeksler:** `fact_orders_status_idx` ve `dim_customer_unique_id_idx` konusunda karar verilmedi (`docs/performance.md`).
- **Git:** Depoda henüz commit yok.

## Aşama 8: Denetim ve temiz kurulum doğrulaması (2026-10-25)

Ayrıntılı sonuçlar `docs/validation_report.md` dosyasında (K-1..K-31); ham çıktılar `docs/validation/` altında.

### Yapılanlar

- **Bağımsız gerçek veri kontrolleri:** `validation/checks.py` eklendi. Modlar: `snapshot`, `invariants`, `routines`, `controlled-failure`.
  - Beklenen değerler reporting nesnelerinden bağımsız olarak dw/staging'den hesaplanıyor.
  - Kapsanan alanlar: join çoğalması, ödeme/ürün ayrımı, sipariş/kalem, `customer_unique_id`, teslimat paydaları, RFM `as_of` sonrası dışlama, tekrar satın alma, tek durum kuralı (katalog taraması), rutin tekrarı, başarısız yüklemede kısmi veri.
- **Temiz kurulum:** `scripts/validate-clean-install.ps1` eklendi.
  - Ayrı Compose projesi `olist-validation`, ayrı volume, port 8502.
  - Akış: şema → ETL ×2 → kontroller → rutinler → kontrollü hata → pytest → dashboard → KPI → tarayıcı.
  - Sonunda yalnızca kendi kaynaklarını siler. Ana volume'a dokunulmadı.

### Bulunan ve düzeltilen sorunlar

- **H-1, `fn_monthly_sales` tarih kapsamı (gerçek hata).**
  - Aylık değerler seçili aralık yerine tam aylardan geliyordu. Ay ortası aralıklarda grafik ile KPI tutmuyordu: 15.01–10.03.2018 için grafik 2.704.438,38, KPI 1.657.285,69.
  - Düzeltme: `sql/190_report_monthly_sales_date_scope_fix.sql`. Gösterilen değerler seçili aralıkla hesaplanıyor; büyüme yalnızca tam aylardan, kısmi aylarda `partial_month`.
  - Kalıcı kontroller: `sql/tests/090` içine ay ortası değişmezi ve `test_monthly_series_uses_same_date_scope_as_kpis`.
- **H-2, README:** "İlk kurulum" adımlarına veri indirme ve dashboard eklendi.
- **H-3, `screenshots.ps1` Docker yolu.**
  - İlk çalıştırmada `ModuleNotFoundError: playwright` verdi; resmî imajda Python paketi yok.
  - Düzeltme: `playwright==1.64.1` konteynerde kuruluyor, imaj digest ile sabitlendi, `-OutDir` parametresi eklendi.
- **Belge bozulmaları:** `\v`/`\t` kaçışından kaynaklanan kontrol karakterleri README ve bu dosyada düzeltildi.
- **Aşama 7 kaydı:** İmaj indirmesinin "durduğu" bilgisi yanlıştı; düzeltildi.

### Gerçek sonuçlar

| Kontrol | Sonuç |
|---|---|
| Temiz kurulum (`validate-clean-install.ps1`) | 18/18 adım çıkış 0; ilk ETL 76,2 s, ikinci 102,9 s; iki yükleme sonrası içerik özetleri aynı |
| Değişmezler (gerçek veri) | 10/10 geçti |
| Rutin tekrarı | 3/3 geçti; `monthly_summary` 27 satır, MD5 değişmedi |
| Kontrollü başarısızlık | Geçti; veri değişmedi, run `failed` |
| pytest (temiz küme / ana proje) | 85 passed / 85 passed |
| `etl.ps1 verify` (ana) | 9/9 |
| `verify-dashboard` (temiz / ana) | 7/7 / 7/7 |
| Tarayıcı: Chrome (8502) / Docker imajı (8501) | 13/13 temiz, 6/6 etkileşim / 13/13 temiz, 6/6 etkileşim |
| Sırlar | `.env`, ham CSV ve `tools/.venv` git dışı; 253 dosyada parola değeri yok |

### Kalan eksikler

- Kaggle'dan veri indirme adımı yeniden sınanmadı.
- Firefox, Safari, tablet genişliği ve erişilebilirlik sınanmadı.
- Soğuk önbellek ve eşzamanlı yük ölçülmedi.
- `v_monthly_sales_growth` ve `monthly_summary` hâlâ 2018-09..11'i 0 satışla içeriyor; dashboard etkilenmiyor. *(Aşağıdaki düzeltmeyle giderildi.)*
- İki indeks kararı bekliyor.
- Ana ETL bir çalıştırmada 118 s sürdü (önceden 81 s); neden ölçülmedi.
- Git deposunda commit yok.

## Aşama 9 öncesi düzeltme: aylık raporların gözlem aralığı (2026-10-25)

### Karar

- **Satış gözlem aralığı:** Satış kapsamındaki ilk satın alma ile son satın alma arası (2016-09-15 … 2018-08-29). RFM ile aynı tanımdır; tek kaynak `reporting.v_rfm_observation`.
- Tüm siparişlerin aralığı (2018-10-17'ye kadar) **kullanılmadı**. 2018-09/10'daki 20 siparişin hiçbiri `delivered` değil; o ayların satışı anlık görüntüde gözlenemiyor, sıfır değil.
- Tarih boyutu değiştirilmedi; teslimat için 2018-11-12'ye kadar uzanmaya devam ediyor.

### Yapılanlar

- **`sql/200_report_monthly_observation_window.sql` (yeni migration).** Uygulanmış dosyalar değiştirilmedi.
  - Yeni view `reporting.v_sales_observation_months`: her `dim_date` ayı için `observed` / `partial` / `not_observed`, `observed_from`, `observed_to`.
  - `v_monthly_sales_growth` yalnızca gözlem aralığındaki ayları içeriyor. Yeni kolonlar sona eklendi: `is_partial_month`, `observed_from`, `observed_to`.
  - Büyüme yalnızca iki tam ay arasında hesaplanıyor; yeni durumlar `partial_month` ve `previous_month_partial`.
  - `monthly_summary`: yeni kolonlar, güncellenmiş `growth_status` CHECK kuralı, `observed_from/observed_to` ay içi kontrolü. Mevcut satırlar migration içinde yeniden yüklendi. `sp_load_monthly_summary` yeni kolonları yazıyor.
  - `fn_monthly_sales`: önceki ay veri kapsamı tarafından kesiliyorsa `previous_month_partial`. Bu, Aşama 8 denetiminde gözden kaçan bir tutarsızlıktı: 2016-10'un büyümesi 16 günlük Eylül'e göre hesaplanıyordu.
- **`dashboard/ui.py`:** `previous_month_partial` için "hesaplanmaz (önceki ay kısmi)" metni.
- **Kalıcı kontroller:**
  - `sql/tests/080` içine üç yeni kontrol: ay sayısı = gözlem aralığı ay sayısı; gözlem dışı satır yok; kısmi aylarda oran yok.
  - `validation/checks.py` içine `monthly_reports_observation_window`. Beklenen değerler doğrudan `dw.fact_orders` ve `dw.dim_date`'ten hesaplanıyor.
  - Rutin kontrolünde beklenen satır sayısı artık gözlem aralığındaki ay sayısı.
- **Testler (sentetik veri, beklenen değerler elle):**
  - `EXPECTED_MONTHS` güncellendi: Ocak/Mayıs kısmi, Şubat gerçek sıfır, Haziran (yalnızca tahmini teslim) yok.
  - Yeni test `test_observation_months_separate_real_zero_from_unobserved` (dim_date'in 2017-06-15'e kadar korunduğu dahil).
  - Yeni test `test_monthly_growth_uses_full_previous_month_when_cut_only_by_filter`: 10.03–05.05.2017 aralığında KPI 50,00 = aylık toplam; Nisan büyümesi −0,7500.
  - Etkilenen dashboard testleri güncellendi.

### Gerçek sonuçlar

| Kontrol | Sonuç |
|---|---|
| `.\scripts\test.ps1` | **87 passed** (85 + 2 yeni) |
| `.\scripts\etl.ps1 migrate` (ana) | `200` uygulandı |
| `.\scripts\etl.ps1 refresh-reports` (ana) | succeeded (refresh_id=3); `monthly_summary` 2016–2018 |
| `.\scripts\etl.ps1 verify` (ana) | 9/9 geçti (yeni 080 kontrolleri dahil) |
| `validation.checks invariants` (ana, `docs/validation/main_invariants_observation_window.json`) | 11/11 geçti |
| `validation.checks routines` (ana, `main_routines_observation_window.json`) | 3/3 geçti |
| `.\scripts\verify-dashboard.ps1` (ana) | `all_match: true` (7 örnek) |

Gerçek veride:

- Aylık raporlar 24 ay içeriyor (2016-09 … 2018-08); `monthly_summary` toplamı 13.221.498,11 = KPI.
- Gerçek sıfır ay: 2016-11. Kısmi aylar: 2016-09, 2018-08. Gözlem dışı aylar: 2018-09 (16 sipariş, hiçbiri `delivered` değil), 2018-10 (4), 2018-11 (0).
- Kısmi tarih filtresi 10.06–29.08.2018: aylık toplam 2.299.774,16 = KPI; Haziran ve Ağustos `partial_month`, Temmuz `computed` 0,0139. *(Bu satır eksikti; düzeltme aşağıda.)*

### Düzeltme: kısmi ay türleri ve Temmuz 2018 büyümesi (2026-10-25)

- **Tutarsızlık:** Yukarıdaki özet, Haziran'ı kısmi gösterirken Temmuz için oran veriyordu ve nedenini söylemiyordu. Kullanıcı bunu "önceki ay kısmi, oran hesaplanmamalı" kuralıyla çelişki olarak gördü.
- **Gerçek fonksiyon çıktısı:** `fn_monthly_sales('2018-06-10', '2018-08-29')`.

  | Ay | Tutar | Kısmi | Neden kısmi | `prev_product_sales` | Oran / durum |
  |---|---:|---|---|---:|---|
  | 2018-06 | 593.244,06 | evet | kullanıcı filtresi (10.06'dan başlıyor); ay **tamamen gözlenmiş** | 977.544,69 | NULL, `partial_month` |
  | 2018-07 | 867.953,46 | hayır | — | 856.077,86 | 0,0139, `computed` |
  | 2018-08 | 838.576,64 | evet | gözlem aralığı (29.08'de bitiyor) ve filtre | 867.953,46 | NULL, `partial_month` |

- **Doğrudan SQL:** Tam Haziran 856.077,86, filtreli Haziran 593.244,06. Temmuz oranı tam Haziran'dan hesaplanıyor: (867.953,46 − 856.077,86) / 856.077,86 = 0,0139. Filtreli Haziran'dan hesaplansaydı 0,4631 olurdu.
- **Sonuç: Kod tanımlı kurala uyuyor** (`sql/190`, `sql/200`): yalnızca *veri kapsamının* kestiği önceki ay oranı engeller. Özet ve arayüz açıklaması eksikti. Migration gerekmedi.
- **Düzeltilenler:**
  - Bilgi kutusu artık "Önceki aya göre (tam aylar)" diyor. Grafiğin altına, oranın kısmi çubukla karşılaştırılamayacağını söyleyen açıklama eklendi (`dashboard/views.py`, `GROWTH_NOTE`).
  - Yeni testin bulduğu ikinci hata: negatif yüzdeler `%-75,0` yazılıyordu. Türkçe biçim `-%75,0`; `ui.fmt_pct` düzeltildi.
  - Testler: `test_overview_explains_growth_base_when_previous_month_cut_by_filter` (arayüzde Nisan "-%75,0", Mart "hesaplanmaz (kısmi ay)", açıklama metni) ve `test_percent_format_puts_sign_before_percent`.
- **Sonuçlar:**
  - `.\scripts\test.ps1`: **89 passed**.
  - `.\scripts\verify-dashboard.ps1`: 7/7, `all_match: true`.
  - Gerçek veride, salt okunur rolle, aynı filtre AppTest ile çizildi: hata yok; Temmuz "Önceki aya göre (tam aylar): %1,4"; Haziran ve Ağustos "hesaplanmaz (kısmi ay)"; açıklama metni görünüyor.
  - SQL değişmediği için `etl.ps1 verify` yeniden çalıştırılmadı. Tarayıcıda ekran görüntüsü alınmadı.

### Yapılmayanlar

- Temiz kurulum betiği (`validate-clean-install.ps1`) bu düzeltmeden sonra yeniden çalıştırılmadı. Boş veritabanına kurulum pytest'teki `test_schema_installs_on_empty_database` ve test veritabanlarındaki sıfırdan kurulumlarla sınandı.
- Dashboard ekranı tarayıcıda yeniden incelenmedi. Değişen metin yalnızca 2016-10 çubuğunun bilgi kutusunda görünüyor; çubuk değerleri değişmedi.
- Performans deneyi yapılmadı (istenmedi).

## Aşama 9: Belgeler, yedekleme ve teslim (2026-10-25)

### Başlangıç durumu (ölçülen)

- Docker motoru çalışıyordu; `db` ve `dashboard` healthy; tek volume `olist-sales-intelligence_pgdata`.
- Ana veritabanı: son migration `200`; son başarılı ETL `1feee717…`; `v_sales_kpis` önceki kayıtlarla aynı (96.478 sipariş, 110.197 kalem, 93.358 müşteri, 13.221.498,11 BRL).
- Projede yedekleme/geri yükleme aracı **yoktu** (kod ve belgelerde arama boş döndü).
- Önceki "89 passed" sonucu Aşama 9 öncesi düzeltmeye aitti; bu aşamada yeniden çalıştırıldı (aşağıda).

### Yeni dosyalar

- **Yedekleme:**
  - `scripts/backup.ps1`: `pg_dump -Fc` konteynerin içinde yazar, `docker compose cp` ile `backups/` klasörüne kopyalar; iki taraftaki SHA-256 karşılaştırılır ve `.sha256` dosyası yazılır. PowerShell yönlendirmesi kullanılmaz, parola gerekmez.
  - `scripts/restore.ps1`: hedef yoksa oluşturur, varsa boş olmasını şart koşar; tek işlemde `pg_restore`; `olist_reporting_reader` yoksa oluşturur; `CONNECT` yetkisini yeniden verir.
  - `scripts/verify-restore.ps1`: `sql/maintenance/database_snapshot.sql` sorgusunu kaynak ve hedefte çalıştırır; iş verisi, nesneler, yetkiler ve `meta` kayıtlarını ayrı karşılaştırır; hedefte `etl verify` çalıştırır; `-DropAfter` yalnızca `_restore_test` ile biten hedefi ve yalnızca başarıda siler.
  - `sql/maintenance/database_snapshot.sql`: migration değildir (`sql_runner` yalnızca üst düzey `NNN_*.sql` dosyalarını uygular).
  - `_common.ps1` içine `Get-EnvValue`: parola anahtarlarını okumayı reddeder.
  - `.gitignore` ve `.dockerignore` içine `backups/`.
- **Portföy belgeleri:** `docs/cv_bullets_tr.md`, `docs/interview_guide_tr.md`, `docs/demo_script_tr.md`.
- **Kanıtlar:** `docs/validation/backup_restore_check.json`, `docs/validation/backup_restore_fresh_cluster.json`, yeni görüntü `docs/screenshots/filter_overview_dates_2018-06-10_2018-08-29_hover_july.png`.

### Değişen dosyalar

- **`README.md`** son uygulamaya göre baştan yazıldı (istenen 16 bölüm sırası).
- **`docs/metric_definitions.md`:** bölüm 11 eklendi (gözlem aralığı / tarih boyutu, gerçek sıfır / gözlem dışı ay, tam/kısmi ay büyümesi, 10.06–29.08.2018 örneği). Bölüm 8'deki "kısmi aylar sonra kararlaştırılmalı" cümlesi verilen kararla değiştirildi.
- **`docs/reporting.md`:** "Bilinen sınırlar"daki eskimiş "dashboard henüz göstermiyor" ve "performans sonra ölçülecek" satırları düzeltildi.
- **`docs/etl_pipeline.md`:** kalite kontrol listesine `080` ve `090` eklendi; ETL süresi yalnızca 71–83 s olarak yazıyordu, sonraki tek ölçümler (118,1 / 137,1 / 76,2 / 102,9 s) eklendi.
- **`docs/performance.md`:** "Ölçümlerin ait olduğu şema sürümü" tablosu eklendi. Kayıtlardan doğrulandı: B çalışması 17:03 UTC'de `olist_perf`'te son migration `150` iken; D1 17:54 UTC'de `180` iken ölçüldü.
- **`docs/dashboard.md`:** görsel kontrol bölümü Aşama 9 güncellemesiyle; Docker yolu ve dar ekran sınırlamaları.
- **`docs/validation_report.md`:** sonuçların zaman notu ve G bölümü (K-32..K-42).
- **`tools/screenshots.py`, `scripts/screenshots.ps1`:** `-OverviewOnly` (yalnızca Genel Bakış; rapor dosyalarına ad bazında birleştirir, kayıtlara `captured_at_utc` ekler) ve 10.06–29.08.2018 büyüme örneği (Temmuz bilgi kutusu).
- **`scripts/dashboard.ps1`:** port mesajı ortam değişkenini de dikkate alıyor.

### Metrik kurallarının tutarlılığı

Belgeler ve kod karşılaştırıldı. Kodda çelişki bulunmadı; aylık büyüme davranışı değiştirilmedi. Belge düzeyindeki eksikler ve eskimiş cümleler yukarıda düzeltildi. Yeni metrik tanımı veya performans optimizasyonu yapılmadı.

### Bu aşamada gerçekten çalıştırılan kontroller

| Kontrol | Sonuç |
|---|---|
| `backup.ps1` | `backups/olist_20261025_174001.dump`, 74.432.354 bayt, 201 arşiv girdisi, SHA-256 eşleşti, 9,5 s |
| `restore.ps1` → `olist_restore_test` | 11,4 s |
| `verify-restore.ps1` | 26 tablo/MV (20 iş verisi + 6 meta) satır sayısı ve içerik MD5'i aynı; nesneler, finansal toplamlar, MV durumu, yetkiler aynı; meta aynı; hedefte 9/9 kontrol geçti. Ardından `-DropAfter` ile silindi |
| Var olan boş hedefe geri yükleme (`olist_restore_empty_test`) | Aynı sonuç; deneme veritabanı silindi |
| Yeni ve boş kümeye geri yükleme (ayrı Compose projesi `olist-restore-check`, port 8503) | Önce yalnızca `olist` rolü vardı. Geri yükleme + `setup-dashboard-role` + `etl verify` 9/9 + `migrate` (yeni dosya yok) + dashboard healthy + `dashboard.verify` 7/7 `all_match: true`; içerik ana veritabanıyla aynı. Proje ve volume'u silindi; ana volume duruyor |
| Korumalar | `-TargetDatabase olist` ve `olist_test` "boş değil" ile reddedildi; yanlış `.sha256` reddedildi |
| Ana veritabanının değişmediği | İki ayrı `verify-restore` çalıştırmasında kaynak özetleri (iş verisi ve meta) aynı |
| `screenshots.ps1 -LocalChrome -OverviewOnly` | İlk deneme `hover` zaman aşımıyla düştü (Plotly sürükleme katmanı; otomasyon hatası). Düzeltmeden sonra 6/6 görüntü taşmasız, hatasız. Temmuz bilgi kutusu "Önceki aya göre (tam aylar): %1,4"; çubuklar 593.244,06 / 867.953,46 / 838.576,64; toplam = KPI 2.299.774,16. Görüntüler tek tek incelendi |
| `docker compose build app` + `pytest -q` | **89 passed** (15,8 s) |
| `dashboard.ps1` | Başarılı; healthy |
| Git'e girecek dosyalar | 301 dosya; `.env`, `backups/*`, `data/raw/*.csv`, `tools/.venv` hariç; `.env` parola değerleri hiçbir dosyada yok |
| Belge bağlantıları ve kontrol karakterleri | Aşağıda |

### Bulunan ve düzeltilen

- `verify-restore.ps1` kontrol satırlarını JSON'a bozuk Türkçe karakterle yazıyordu. Dil bağımsız biçime geçildi ve yeniden çalıştırıldı.
- `dashboard.ps1` port mesajı (yukarıda).
- Kanıt JSON'unu üreten geçici Python komutunda ters eğik çizgi kaçışı sözdizimi hatası verdi (önceki aşamalardaki hata türü). Dosya yazılmadan durdu; yollar düz eğik çizgiyle yazıldı. Belgeler Write/Edit araçlarıyla, kaçış işlenmeden yazıldı.
- Dar ekranda aylık grafiğin ay etiketleri üst üste biniyordu. Bu yeni bir değişiklik değildi ama önceki kayıtlarda yoktu; teslimde sınırlama olarak belgelendi, ardından düzeltildi (aşağıda).

### Yapılmayanlar

- Temiz kurulum betiği, performans deneyleri, Docker ekran görüntüsü yolu ve Genel Bakış dışındaki görüntüler yeniden çalıştırılmadı (değişen kod onları etkilemiyor; ağır deneyler yalnızca belge değişikliği için tekrarlanmadı).
- Ana veritabanında `etl.ps1 verify` ve `verify-dashboard.ps1` yeniden çalıştırılmadı (SQL ve veri değişmedi). Aynı kontroller geri yüklenen kopyalarda çalıştı.
- `reset.ps1` hiç çalıştırılmadı.
- Kod lisansı seçilmedi (kullanıcı kararı).
- **Git:** depoda hâlâ commit yok; bu aşamada da commit yapılmadı.

### Teslim durumu

Proje yerel portföy demosu olarak kullanılabilir durumda: kurulum, günlük kullanım, yedekleme/geri yükleme ve demo akışı belgelendi ve bu aşamada çalıştırılan kontrollerle doğrulandı. Kalan sınırlamalar README bölüm 16'da.

### Teslim sonrası düzeltme: aylık grafikte ay etiketleri (2026-10-25)

- **Neden:** `dashboard/views.py` aylık grafikte `dtick="M1"` ile her ayı etiketlemeye zorluyordu. 390 px'te 24 etiket -45° açıyla sığmıyordu.
- **Düzeltme (yalnızca eksen):** Ay etiketleri kategori ekseninde gösteriliyor. Sabit `dtick` kaldırıldı, `autotickangles=[0, 90]` eklendi. Plotly etiket sıklığını tarayıcıdaki genişliğe göre seçiyor. Veri noktaları, filtreler, metrikler, büyüme kuralları ve bilgi kutuları değişmedi. SQL, ETL ve performans deneyleri çalıştırılmadı.
- **Ara denemeler:**
  - 45° açı 390 px'te hâlâ 2,2 px çakışma verdi (ölçüm ve görüntü).
  - `tickangle="auto"` Plotly'de geçersiz çıktı; sayfa hata verdi ve o anki görüntüler hata ekranıydı.
  - Her ikisi bırakıldı; görüntüler son sürümle yeniden alındı.
- **Araç:** `tools/screenshots.py` her grafikte `x_tick_labels` kaydediyor (sayı, açı, çakışan komşu çift, en küçük aralık).
- **Gerçek sonuçlar (Chrome 156):**

  | Genişlik | Önce (negatif kontrol) | Sonra |
  |---|---|---|
  | 1440 px | 24 etiket, 0 çakışma | 24 etiket, dik, 0 çakışma, en küçük aralık 20,4 px |
  | 390 px | 24 etiket, 23 çakışma | 12 etiket, dik, 0 çakışma, en küçük aralık 4,9 px |

  - 24 çubuk ve toplam 13.221.498,11 BRL değişmedi. RJ, `health_beauty`, 2018-Q1 ve 10.06–29.08.2018 değerleri öncekiyle aynı; Temmuz "Önceki aya göre (tam aylar): %1,4".
  - Masaüstü ve büyütülmüş dar ekran görüntüleri gözle incelendi.
- **Testler:** `pytest tests/test_dashboard.py` 22 passed (ara sürümlerde); son kodla tam paket **89 passed**.
- **Yenilenen görüntüler:** Genel Bakış'ın 6 görüntüsü, `docs/screenshots/report.json`, `docs/screenshots/interactions.json`.
- **Ölçülmeyenler:** ara genişlikler (ör. 768 px) ve Docker ekran görüntüsü yolu.

## GitHub yayın hazırlığı (2026-10-26)

- **Git durumu:** `main` dalında commit yok, uzak depo yok, takip edilen dosya yok. Bu hazırlıkta da commit, `git add`, uzak depo veya push yapılmadı.
- **`.gitignore` genişletildi:**
  - anahtar ve kimlik dosyaları (`*.pem`, `*.key`, `kaggle.json`…);
  - döküm ve yerel veritabanı dosyaları (`*.dump`, `*.sqlite`, `*.db`…);
  - arşivler (`*.zip`, `*.7z`…);
  - Python önbellekleri, `*.exe`/`*.msi`, editör ve yerel araç ayarları.
  - Gerekli dosyaların hiçbiri gizlenmedi (örnek yollarla doğrulandı).
- **Yayın listesi:** 305 dosya, 6.927.390 bayt; en büyük dosya 202.792 bayt. GitHub sınırları (50 MiB uyarı, 100 MiB engel, tarayıcıdan 25 MiB) resmî belgeden okundu.
- **Gizli bilgi taraması:** yayımlanacak 305 dosyada şunlar arandı:
  - `.env` parola değerleri;
  - özel anahtar, GitHub/AWS/Slack/Google/API anahtarı biçimleri;
  - Kaggle kimliği, parolalı bağlantı adresi;
  - 48 haneli hex değerler ve parola atamaları.
- **Tarama sonucu:** gerçek gizli bilgi bulunmadı. Eşleşmeler kod ifadeleri, `.gitignore` kuralı ve testteki kasıtlı sahte değerdi.
- **Kişisel ağ bilgileri:** bu dosyadaki yerel ağ DNS/ağ geçidi IP adresleri ve Windows kullanıcı klasörü yolu genel ifadelerle değiştirildi.
- **Test verisi:** `tests/fixtures` altındaki 230 kimliğin hiçbiri gerçek veride yok.
- **Belgeler:**
  - `README.md`'ye dil bağlantısı, klonlama adımı ve yedek dosya adı kalıbı eklendi; test sonucu tarihiyle yazıldı.
  - Bu hazırlıkta ayrı bir `README.en.md` de eklendi. Sonradan kullanıcı kararıyla GitHub'daki tek giriş belgesi iki dilli `README.md` oldu (İngilizce bölüm: `README.md#english`). `README.en.md` silinmedi; yalnızca kök dizine özgü `/README.en.md` kuralıyla Git dışında tutuluyor.
- **Bağlantı ve karakter kontrolü:** 18 belgede bağlantı, Git dışı dosyaya bağlantı ve kontrol karakteri taraması yapıldı; sorun yok.
- **Kod:** kod değişmedi; testler, ETL ve performans deneyleri yeniden çalıştırılmadı.
