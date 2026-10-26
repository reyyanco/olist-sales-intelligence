# Yeniden Başlatma Sonrası Devam Adımları

Docker Desktop 4.96.3 kuruldu ve yeniden başlatmadan önce çalıştığı doğrulandı. Windows kurulumun ardından yeniden başlatma bekliyor; `docker-users` grup üyeliği de yeni oturumda geçerli olur.

## 1. Sizin yapacaklarınız

1. Bilgisayarı yeniden başlatın.
2. Docker Desktop'ı Başlat menüsünden açın.
3. Lisans sözleşmesi penceresi çıkarsa okuyup kabul edin. Giriş ekranını atlayabilirsiniz.
4. Sol alttaki durum göstergesi "Engine running" olana kadar bekleyin.

## 2. Doğrulama komutları

VS Code'da **yeni** bir terminal açın (eski terminallerde PATH güncel değildir) ve proje klasöründe çalıştırın:

```powershell
git --version
docker version
docker compose version
wsl -l -v
docker run --rm hello-world
docker rmi hello-world
```

Beklenen sonuçlar:

- `docker version` hem `Client` hem `Server` bölümünü gösterir.
- `wsl -l -v` çıktısında `docker-desktop` dağıtımı `Running`, sürüm `2` görünür.
- `docker run --rm hello-world` çıktısında "Hello from Docker!" yazar.

## 3. Sorun olursa

- `docker: command not found` / `docker-credential-desktop not found`: terminali kapatıp yeniden açın.
- `permission denied` / `docker-users`: oturumu kapatıp açın veya yeniden başlatın.
- `lookup registry-1.docker.io: no such host`: Bu ağın DNS sunucusu yavaş ve aralıklı çalışıyor (bkz. `docs/project_state.md`, Aşama 1.1). Önce komutu yeniden deneyin. Proxy veya Docker ayarı değiştirmeyin; kanıt olmadan kalıcı DNS değişikliği yapmayın.
- Motor başlamıyorsa: Docker Desktop > Troubleshoot > Restart; sonra `wsl --status` çıktısını kontrol edin.

Doğrulama sonuçları `docs/project_state.md` dosyasına işlenir.
