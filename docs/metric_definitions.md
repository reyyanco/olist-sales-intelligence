# Metrik Tanımları

Bu belge raporlama katmanındaki (`reporting` şeması) metriklerin kesin tanımlarını verir. SQL karşılıkları `sql/050_reporting_views.sql` ve `sql/090_reporting_payment_differences.sql` dosyalarındadır.

Örnek değerler gerçek Olist verisinden, `run_id=77ff75fa-b2b4-4778-90df-2e17b50692b7` çalışmasıyla ölçülmüştür. Para birimi kaynakta belirtilmemiştir; veri seti Brezilya'ya ait olduğu için BRL olduğu **varsayılır (doğrulanmadı)**.

## 1. Satış kapsamı

| Kural | Değer |
|---|---|
| Varsayılan satış kapsamı | `order_status = 'delivered'` (`in_sales_scope = true`) |
| Diğer durumlar | `shipped`, `canceled`, `unavailable`, `invoiced`, `processing`, `created`, `approved`: dw'de korunur, satış metriklerine girmez |
| Zaman ekseni | Satın alma zamanı (`purchase_ts`); aylık özetlerde `date_trunc('month', purchase_ts)` |

Gerçek veri: 99.441 siparişin 96.478'i kapsamda. Kapsam dışı: shipped 1.107, canceled 625, unavailable 609, invoiced 314, processing 301, created 5, approved 2 (`sql/reports/020_out_of_scope_orders.sql`).

Kenar durumlar:

- `delivered` durumunda olup teslim zamanı boş olan 8 sipariş satış kapsamındadır. Bunlar hata sayılmaz; yalnızca teslimat süresi ve geç teslim metriklerinin dışında kalır.
- Teslim zamanı dolu olan 6 iptal (`canceled`) sipariş, durumları nedeniyle kapsam dışıdır.

## 2. Tutarlar

| Metrik | Tanım | Kaynak kolon | Gerçek veri (kapsam) |
|---|---|---|---|
| **Ürün satış tutarı** (`product_sales`) | Kapsamdaki siparişlerin kalem fiyatlarının toplamı: `SUM(fact_sales.price)` (sipariş düzeyinde `fact_orders.product_value`) | `order_items.price` | 13.221.498,11 |
| **Kargo tutarı** (`freight_amount`) | `SUM(fact_sales.freight_value)` | `order_items.freight_value` | 2.198.275,64 |
| **Ödeme tutarı** (`payment_amount`) | `SUM(fact_payments.payment_value)` (sipariş düzeyinde `fact_orders.payment_value`) | `order_payments.payment_value` | 15.422.461,77 |

Bu tutarlar şöyle **adlandırılmaz**:

- **Net kâr:** maliyet bilgisi yok.
- **İade sonrası net gelir:** iade bilgisi yok.
- **Vergi hariç tutar:** vergi bilgisi yok.

"Ürün satış tutarı", kalem fiyatlarının brüt toplamıdır.

### Ödeme ile kalem + kargo farkı

Ödeme tutarı ile kalem + kargo toplamı her siparişte eşit değildir. Fark **raporlanır, zorla eşitlenmez**. Kaynak, farkın nedenini (ör. taksit faizi, kupon) belirtmez.

Rapor kaynakları: `reporting.v_order_payment_differences` ve `sql/reports/030_payment_vs_items_difference.sql`.

| Kapsam | Fark türü | Sipariş | Toplam fark |
|---|---|---:|---:|
| delivered | payment_higher | 362 | 3.032,24 |
| delivered | payment_lower | 207 | −200,76 |
| delivered | no_payment | 1 | −143,46 |
| kapsam dışı | no_items (kalemsiz, ödemesi var) | 772 | 162.591,95 |
| kapsam dışı | payment_higher / payment_lower | 5 / 2 | 38,93 / −0,02 |

Karşılaştırma birebirdir (tolerans yok). Profil raporundaki ±0,01 toleranslı sayım bu yüzden farklıdır: orada 303 sipariş farklı görünür.

## 3. Sayımlar

| Metrik | Tanım | Gerçek veri |
|---|---|---:|
| **Sipariş sayısı** | Kapsamdaki farklı `order_id` sayısı (`fact_orders` satırı = sipariş) | 96.478 |
| **Müşteri sayısı** | Kapsamda en az bir siparişi olan farklı **`customer_unique_id`** sayısı | 93.358 |
| **Kalem sayısı** | Kapsamdaki `fact_sales` satırı sayısı | 110.197 |

`customer_id` müşteri sayımında **kullanılmaz**. Bu kimlik siparişe özgüdür; kapsamda 96.478 farklı `customer_id` vardır ve bu sayı sipariş sayısına eşittir.

### Kalem sayısının anlamı

- Kaynakta `quantity` (adet) kolonu yoktur. Kalem sayısı, `olist_order_items_dataset.csv` satır sayısıdır: `(order_id, order_item_id)` başına bir satır.
- Aynı ürün aynı siparişte birden fazla satır olarak görünebilir. Profilde 7.088 sipariş-ürün çiftinde böyledir ve bu çiftlerde fiyat hiç değişmez.
- Bu, "her satır bir adet" yorumuyla tutarlıdır, ancak kaynak belgesi bunu açıkça söylemez. Bu yüzden metrik **"adet" değil "kalem sayısı"** olarak adlandırılır. *Doğrulanmamış varsayım.*

## 4. Ortalama sepet tutarı

| | |
|---|---|
| Tanım | `ürün satış tutarı / sipariş sayısı` (kargo **hariç**), 2 ondalığa yuvarlanır |
| Pay | Kapsamdaki siparişlerin `product_value` toplamı |
| Payda | Kapsamdaki sipariş sayısı (kalemsiz siparişler dahil; kapsamdaki tüm siparişlerin kalemi var) |
| Gerçek veri | 137,04 |

Kargo dahil veya ödeme tabanlı ortalamalar ayrı metrik olarak adlandırılmalıdır.

## 5. Teslimat süresi

| | |
|---|---|
| Sipariş düzeyinde | `delivery_days = (delivered_customer_ts − purchase_ts)` gün cinsinden, ondalıklı, 2 haneye yuvarlanmış (`fact_orders` üretilmiş kolon) |
| Metrik | `avg(delivery_days)`: teslim zamanı **dolu** olan kapsamdaki siparişlerin ortalaması |
| Pay | Teslim zamanı dolu kapsam siparişlerinin `delivery_days` toplamı |
| Payda | Teslim zamanı dolu kapsam siparişi sayısı (`delivery_measured_orders`) |
| Hariç tutulan | Teslim zamanı boş kapsam siparişleri (`delivery_unmeasured_orders`). Ayrıca raporlanır, hata sayılmaz |
| Gerçek veri | 12,56 gün; ölçülen 96.470, ölçülemeyen 8 |

Zamanlar saat dilimi olmadan saklanır ve dönüştürülmez (bkz. 8).

## 6. Geç teslimat oranı

| | |
|---|---|
| Geç sipariş | `delivered_customer_ts::date > estimated_delivery_date` (tahmini günün kendisi geç sayılmaz) |
| Pay | Kapsamdaki geç sipariş sayısı (`late_orders`) |
| Payda | Teslim zamanı dolu kapsam siparişi sayısı (`delivery_measured_orders`); tahmini teslim tarihi gerçek veride her siparişte dolu |
| Hariç tutulan | Teslim zamanı boş siparişler (paydaya da paya da girmez) |
| Gerçek veri | 6.534 / 96.470 = 0,0677 |

Profilde, tüm durumlar dahil 6.535 sipariş geç görünür. Aradaki 1 sipariş kapsam dışı bir durumdadır.

## 7. Tekrar satın alma oranı

| | |
|---|---|
| Birim | `customer_unique_id` |
| Pay | Gözlem aralığında kapsamda **en az 2 farklı siparişi** olan kişi sayısı |
| Payda | Gözlem aralığında kapsamda en az 1 siparişi olan kişi sayısı |
| Not | Aynı gün verilen iki ayrı sipariş iki sipariş sayılır |
| Gerçek veri | 2.801 / 93.358 = 0,0300 |

## 8. RFM gözlem tarihi ve aralığı

| | |
|---|---|
| Birim | `customer_unique_id`, yalnızca kapsamdaki siparişler |
| Gözlem aralığı | Kapsamdaki ilk satın alma gününden son satın alma gününe kadar tüm geçmiş (`reporting.v_rfm_observation`) |
| Gözlem tarihi | Kapsamdaki **son satın alma günü + 1 gün**. Veriden hesaplanır, sabit yazılmaz |
| Recency | `gözlem tarihi − kişinin son satın alma günü` (gün) |
| Frequency | Kişinin kapsamdaki farklı sipariş sayısı |
| Monetary | Kişinin kapsamdaki ürün satış tutarı (kargo hariç) |
| Gerçek veri | Aralık 2016-09-15 … 2018-08-29; gözlem tarihi **2018-08-30** |

Parametreli hesap `reporting.fn_customer_rfm(as_of date)` ile yapılır:

| Kural | Açıklama |
|---|---|
| `as_of` | Zorunludur; `CURRENT_DATE` kullanılmaz. |
| Dahil edilen siparişler | `purchase_ts < as_of` olanlar. `as_of` günü ve sonrası dışlanır. |
| Gözlem tarihiyle ilişki | `as_of` = gözlem tarihi verildiğinde sonuç yukarıdaki tanımla aynıdır. |
| Gözlem aralığı | Kapsamdaki ilk satın almadan `as_of` gününün başına kadar. |

Aylık satış raporları da aynı gözlem aralığını kullanır (`reporting.v_sales_observation_months`):

- Aralık içindeki satışsız ay 0'dır.
- Aralık dışındaki ay (ör. tarih boyutuna yalnızca tahmini teslim tarihleri nedeniyle giren ay) raporda yer almaz.
- Ayrıntı: `docs/reporting.md`, bölüm 1.

Puanlama ve segmentler `docs/reporting.md` dosyasındadır:

- R ve M: eşitlik güvenli beşli dilim.
- F: sabit eşik (1, 2, 3, 4, 5+).

Veri setinin başı (2016-09 … 2016-12) çok az sipariş içerir. Bu aylar dışlanmaz; kısmi aylar işaretlenir ve büyüme oranı yalnızca tam aylar arasında hesaplanır (bölüm 11).

## 9. Zaman ve saat dilimi

- Kaynak zamanlar `YYYY-MM-DD HH:MM:SS` biçimindedir ve saat dilimi içermez.
- `timestamp without time zone` olarak saklanır; UTC'ye veya başka bir dilime **dönüştürülmez**.
- Zamanların Brezilya yerel saati olduğu varsayılır; *bu varsayım doğrulanmadı.*
- Tahmini teslim zamanı her satırda `00:00:00` olduğu için `date` olarak saklanır. ETL bunu her yüklemede doğrular; saat içeren satır reddedilir.

## 10. Çoğalmama kuralı

- Sipariş düzeyi ölçüler (ödeme, kargo toplamı, yorum) **kalem satırlarına tekrarlanmaz**.
- Kalem, ödeme ve yorum kayıtları birbirleriyle **doğrudan birleştirilmez**. Her biri sipariş başına ayrı toplanır ve `fact_orders` içine yazılır.

Örnek (sentetik test verisi): 3 kalem × 2 ödeme × 2 yorum içeren bir siparişte doğrudan birleştirme 12 satır üretir.

| | Ürün tutarı | Ödeme tutarı |
|---|---:|---:|
| Doğrudan birleştirme (yanlış) | 1.002,00 | 1.654,50 |
| Model (doğru) | 250,50 | 275,75 |

Bu davranışı `tests/test_dw_model.py::test_multi_item_multi_payment_order_is_not_duplicated` ve her yüklemede çalışan `sql/tests/030_reporting_totals_not_duplicated.sql` doğrular.

## 11. Aylık satış ve önceki aya göre büyüme

Kaynak: `sql/200_report_monthly_observation_window.sql` (raporlar) ve `sql/190` + `sql/200` içindeki `reporting.fn_monthly_sales` (dashboard). Ayrıntılı tablo: `docs/reporting.md`, bölüm 1.

| Kavram | Tanım | Gerçek veri |
|---|---|---|
| Satış gözlem aralığı | Satış kapsamındaki ilk ve son satın alma günü (RFM ile aynı kaynak: `v_rfm_observation`) | 15.09.2016 – 29.08.2018, 24 ay |
| Tarih boyutu kapsamı | Tahmini teslim tarihleri dahil tüm tarihler; teslimat metrikleri için gerekir | 2018-11-12'ye kadar |
| Gözlem dışı ay | Tarih boyutunda olup gözlem aralığında olmayan ay. Raporda **yer almaz**; sıfır satışlı ay gibi gösterilmez | 2018-09, 2018-10, 2018-11 |
| Gerçek sıfır ay | Gözlem aralığında olup teslim edilmiş siparişi olmayan ay. **0 olarak korunur** | 2016-11 |
| Kısmi ay (veri kapsamı) | Ayın bir kısmı gözlem aralığının dışında | 2016-09, 2018-08 |
| Kısmi ay (kullanıcı filtresi) | Seçili tarih aralığı ayın tamamını içermiyor; ay tamamen gözlenmiş | filtreye bağlı |

Kurallar:

- **Çubuk tutarı** yalnızca seçili tarih aralığındaki günleri içerir; çubukların toplamı KPI kartına eşittir.
- **Büyüme oranı** her zaman iki **tam takvim ayı** arasındadır ve tam ay tutarlarından hesaplanır: `(bu ay − önceki ay) / önceki ay`.
- Seçili aralıkta kısmi kalan ayın kendi oranı gösterilmez (`partial_month`).
- Önceki ay **yalnızca kullanıcı filtresiyle** kesiliyorsa oran yine hesaplanır; önceki ayın **tam** tutarı kullanılır.
- Önceki ay **veri kapsamı** nedeniyle eksikse oran hesaplanmaz (`previous_month_partial`; gerçek veride 2016-10).
- Önceki ay 0 ise oran hesaplanmaz (`previous_month_zero`; gerçek veride 2016-12). Sıfıra bölme yapılmaz.

Örnek, tarih filtresi 10.06–29.08.2018 (`fn_monthly_sales('2018-06-10', '2018-08-29')`, gerçek veri; tarayıcı kanıtı `docs/screenshots/interactions.json`, `overview_growth_full_month_base`):

| Ay | Çubuk (BRL) | Neden | Önceki aya göre |
|---|---:|---|---|
| 06.2018 | 593.244,06 | filtre 10.06'da başlıyor; tam Haziran 856.077,86 | hesaplanmaz (kısmi ay) |
| 07.2018 | 867.953,46 | tam ay | **%1,4** = (867.953,46 − 856.077,86) / 856.077,86 |
| 08.2018 | 838.576,64 | veri 29.08'de bitiyor | hesaplanmaz (kısmi ay) |

Temmuz oranı filtrelenmiş Haziran çubuğuna (593.244,06) göre hesaplansaydı %46,3 çıkardı; bu, Temmuz'un gerçek büyümesi değildir. Arayüz bu yüzden bilgi kutusunda "Önceki aya göre (tam aylar)" yazar ve grafiğin altında kuralı açıklar.
