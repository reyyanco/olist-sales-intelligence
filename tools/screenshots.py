"""Çalışan dashboard'dan gerçek ekran görüntüleri ve görsel kontrol ölçümleri (Playwright, başsız Chromium).

Kullanım: .\\scripts\\screenshots.ps1  (resmî mcr.microsoft.com/playwright/python imajında çalışır)
Çıktı: docs/screenshots/*.png ve docs/screenshots/report.json
Her görüntüde ayrıca ölçülür: yatay taşma (sayfa genişliği > pencere), görünen Streamlit hata/istisna
öğeleri ve sayfadaki KPI değerleri.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://dashboard:8501"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "/out")
# "overview": yalnızca Genel Bakış görüntüleri ve etkileşimleri yeniden alınır; report.json ve
# interactions.json içindeki diğer kayıtlar korunur, aynı adlı kayıtlar değiştirilir.
ONLY = sys.argv[3] if len(sys.argv) > 3 else "all"
# Streamlit içeriği kendi kaydırma alanında gösterir; full_page pencerenin ötesini yakalamaz. Sayfanın tamamı
# görünsün diye pencere yüksek tutulur (genişlik, yani duyarlı yerleşim, değişmez).
VIEWPORTS = {"desktop": {"width": 1440, "height": 2400}, "narrow": {"width": 390, "height": 3200}}
# Genel Bakış varsayılan sayfadır ve kök adreste sunulur.
PAGES = {"": "Genel Bakış", "kategori": "Kategori Analizi", "musteri": "Müşteri Analizi",
         "teslimat": "Teslimat Performansı"}


def wait_ready(page: Page, timeout_s: float = 90) -> None:
    """Streamlit çalışmasının bitmesini ve grafiklerin çizilmesini bekler."""
    page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=timeout_s * 1000)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        running = page.locator('[data-testid="stStatusWidget"]').count()
        if running == 0 and page.locator("h1").count() > 0:
            break
        time.sleep(0.5)
    time.sleep(2.5)  # Plotly çizimi


def inspect(page: Page) -> dict:
    return page.evaluate("""() => ({
        scroll_width: document.documentElement.scrollWidth,
        client_width: document.documentElement.clientWidth,
        horizontal_overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
        title: (document.querySelector('h1') || {}).innerText || null,
        errors: [...document.querySelectorAll('[data-testid="stException"], [data-testid="stAlertContentError"]')].map(e => e.innerText.slice(0, 200)),
        infos: [...document.querySelectorAll('[data-testid="stAlertContentInfo"], [data-testid="stAlertContentWarning"]')].map(e => e.innerText.slice(0, 200)),
        metrics: [...document.querySelectorAll('[data-testid="stMetric"]')].map(m => m.innerText.replace(/\\n+/g, ' | ')),
        plotly_charts: document.querySelectorAll('.js-plotly-plot').length,
        // Tarayıcıda ÇİZİLMİŞ grafik verisi (_fullData: Plotly'nin çözülmüş verisi): ilk izin nokta sayısı ve y toplamı
        chart_first_trace: [...document.querySelectorAll('.js-plotly-plot')].map(g => {
            const t = (g._fullData || [])[0] || {}; const ys = Array.from(t.y || [], Number);
            return {points: ys.length, y_sum: Math.round(ys.reduce((a, b) => a + b, 0) * 100) / 100};
        }),
        // Her grafikte görünen x ekseni etiketleri ve üst üste binen komşu çiftler. Döndürülmüş (eğik) paralel
        // etiketler, aralarındaki dik mesafe (yatay aralık × |sin açı|) yazı yüksekliğinden küçükse çakışır.
        x_tick_labels: [...document.querySelectorAll('.js-plotly-plot')].map(g => {
            const ts = [...g.querySelectorAll('.xaxislayer-above .xtick text')].map(t => {
                const b = t.getBoundingClientRect(), local = t.getBBox();
                const m = /rotate\\((-?[0-9.]+)/.exec(t.getAttribute('transform') || '');
                return {cx: b.left + b.width / 2, w: local.width, h: local.height, angle: m ? Number(m[1]) : 0};
            }).filter(t => t.w > 0).sort((a, b) => a.cx - b.cx);
            let overlaps = 0, minGap = null;
            for (let i = 1; i < ts.length; i++) {
                const a = ts[i - 1], b = ts[i], dx = b.cx - a.cx;
                const gap = a.angle ? dx * Math.abs(Math.sin(a.angle * Math.PI / 180)) - Math.max(a.h, b.h)
                                    : dx - (a.w + b.w) / 2;
                minGap = minGap === null ? gap : Math.min(minGap, gap);
                if (gap < 0) overlaps++;
            }
            return {count: ts.length, angle: ts.length ? ts[0].angle : null, overlapping_pairs: overlaps,
                    min_gap_px: minGap === null ? null : Math.round(minGap * 10) / 10};
        }),
        scope: (document.querySelector('.scope') || {}).innerText || null,
    })""")


def shot(page: Page, name: str, results: list) -> None:
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    info = inspect(page)
    info["file"] = path.name
    info["captured_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    results.append({"name": name, **info})
    print(f"{name}: overflow={info['horizontal_overflow']} errors={len(info['errors'])} charts={info['plotly_charts']}")


def pick(page: Page, label: str, value: str) -> None:
    """Kenar çubuğundaki multiselect'e (etiketine göre) değer yazıp seçer — gerçek kullanıcı etkileşimi."""
    box = page.locator('[data-testid="stSidebar"] [data-testid="stMultiSelect"]').filter(has_text=label)
    box.locator("input").click()
    page.keyboard.type(value)
    page.wait_for_timeout(600)
    page.keyboard.press("Enter")
    page.keyboard.press("Escape")
    wait_ready(page)


def set_dates(page: Page, start_ddmmyyyy: str, end_ddmmyyyy: str) -> None:
    """Tarih alanı gün/ay/yıl parçalarından (role=spinbutton) oluşur; kullanıcı gibi tıklayıp rakam yazılır."""
    segments = page.locator('[data-testid="stSidebar"] [data-testid="stDateInput"] [role="spinbutton"]')
    segments.nth(0).click(); page.keyboard.type(start_ddmmyyyy, delay=60)
    segments.nth(3).click(); page.keyboard.type(end_ddmmyyyy, delay=60)
    # Streamlit aralığı takvim penceresi kapanınca uygular: kullanıcı gibi pencereyi kapatıp dışarı tıkla.
    page.keyboard.press("Escape")
    page.locator("h1").first.click()
    wait_ready(page)


def merge(path: Path, new: list, key: str) -> list:
    """Kısmi çalıştırmada eski kayıtları korur; aynı anahtarlı kayıtları yenisiyle değiştirir."""
    old = json.loads(path.read_text(encoding="utf-8")) if ONLY != "all" and path.exists() else []
    names = {x[key] for x in new}
    return [x for x in old if x[key] not in names] + new


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    results: list = []
    checks: list = []
    with sync_playwright() as p:
        # PW_CHANNEL=chrome: bilgisayarda kurulu Chrome kullanılır (ayrı tarayıcı indirilmez).
        channel = os.environ.get("PW_CHANNEL") or None
        browser = p.chromium.launch(channel=channel)
        print(f"tarayıcı: {channel or 'playwright chromium'} {browser.version}")
        for vp_name, vp in VIEWPORTS.items():
            ctx = browser.new_context(viewport=vp, locale="tr-TR", device_scale_factor=1)
            page = ctx.new_page()
            for slug in (PAGES if ONLY == "all" else [""]):
                page.goto(f"{BASE}/{slug}")
                wait_ready(page)
                shot(page, f"{vp_name}_{slug or 'genel-bakis'}", results)
            ctx.close()

        # Arayüz etkileşimleri (masaüstü). Her sayfa yüklemesi yeni oturumdur; filtreler varsayılandan başlar.
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"], locale="tr-TR")
        page = ctx.new_page()
        page.goto(f"{BASE}/"); wait_ready(page)
        default = inspect(page)
        checks.append({"check": "default_overview", "metrics": default["metrics"], "chart": default["chart_first_trace"]})

        pick(page, "Müşteri eyaleti", "RJ")
        shot(page, "filter_overview_state_RJ", results)
        checks.append({"check": "overview_state_RJ", "metrics_changed": results[-1]["metrics"] != default["metrics"],
                       "chart_changed": results[-1]["chart_first_trace"] != default["chart_first_trace"],
                       "scope": results[-1]["scope"], "metrics": results[-1]["metrics"], "chart": results[-1]["chart_first_trace"]})

        page.goto(f"{BASE}/"); wait_ready(page)
        pick(page, "Ürün kategorisi", "health_beauty")
        shot(page, "filter_overview_category_health_beauty", results)
        checks.append({"check": "overview_category_health_beauty", "metrics_changed": results[-1]["metrics"] != default["metrics"],
                       "chart_changed": results[-1]["chart_first_trace"] != default["chart_first_trace"],
                       "scope": results[-1]["scope"], "metrics": results[-1]["metrics"], "chart": results[-1]["chart_first_trace"]})

        # Tarih aralığını arayüzden değiştirme (yazarak)
        page.goto(f"{BASE}/"); wait_ready(page)
        set_dates(page, "01012018", "31032018")
        shot(page, "filter_overview_dates_2018Q1", results)
        checks.append({"check": "overview_dates_2018Q1", "metrics_changed": results[-1]["metrics"] != default["metrics"],
                       "chart_changed": results[-1]["chart_first_trace"] != default["chart_first_trace"],
                       "scope": results[-1]["scope"], "metrics": results[-1]["metrics"], "chart": results[-1]["chart_first_trace"]})

        # Büyüme örneği: 10.06–29.08.2018. Haziran filtreyle, Ağustos veri kapsamıyla kısmi; Temmuz tam ay.
        # Temmuz çubuğunun bilgi kutusu (hover) okunur: oran tam Haziran'a göre olmalı.
        page.goto(f"{BASE}/"); wait_ready(page)
        set_dates(page, "10062018", "29082018")
        # Plotly'nin sürükleme katmanı çubukların üstündedir; fare, kullanıcı gibi çubuğun ortasına taşınır.
        box = page.locator(".js-plotly-plot .barlayer .point").nth(1).bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_timeout(1000)
        hover_text = page.locator(".js-plotly-plot .hoverlayer").first.text_content()
        shot(page, "filter_overview_dates_2018-06-10_2018-08-29_hover_july", results)
        bar_values = page.evaluate("""() => {
            const g = document.querySelector('.js-plotly-plot'); const t = (g._fullData || [])[0] || {};
            return {x: Array.from(t.x || [], String), y: Array.from(t.y || [], Number)};
        }""")
        checks.append({"check": "overview_growth_full_month_base", "scope": results[-1]["scope"],
                       "metrics": results[-1]["metrics"], "bars": bar_values, "july_hover_text": hover_text,
                       "captions": page.locator('[data-testid="stCaptionContainer"]').all_inner_texts()})

        if ONLY != "all":
            ctx.close()
            browser.close()
            for c in checks:
                print(json.dumps(c, ensure_ascii=False))
            (OUT / "interactions.json").write_text(json.dumps(merge(OUT / "interactions.json", checks, "check"),
                                                              indent=2, ensure_ascii=False), encoding="utf-8")
            (OUT / "report.json").write_text(json.dumps(merge(OUT / "report.json", results, "name"),
                                                        indent=2, ensure_ascii=False), encoding="utf-8")
            return 0

        # Gezinme: kenar çubuğundaki bağlantıya tıklama
        page.goto(f"{BASE}/"); wait_ready(page)
        page.locator('[data-testid="stSidebarNav"] a', has_text="Teslimat Performansı").click()
        wait_ready(page)
        before_ba = inspect(page)
        checks.append({"check": "nav_click_to_delivery", "title": before_ba["title"], "url": page.url})
        pick(page, "Müşteri eyaleti", "BA")
        shot(page, "filter_delivery_state_BA", results)
        checks.append({"check": "delivery_state_BA", "metrics_changed": results[-1]["metrics"] != before_ba["metrics"],
                       "chart_changed": results[-1]["chart_first_trace"] != before_ba["chart_first_trace"],
                       "scope": results[-1]["scope"], "metrics": results[-1]["metrics"]})

        # Boş sonuç: AC eyaletinde arts_and_craftmanship satışı yok (SQL ile doğrulandı)
        page.goto(f"{BASE}/"); wait_ready(page)
        pick(page, "Müşteri eyaleti", "AC")
        pick(page, "Ürün kategorisi", "arts_and_craftmanship")
        shot(page, "empty_result_overview", results)
        checks.append({"check": "empty_result", "infos": results[-1]["infos"], "metrics": results[-1]["metrics"],
                       "errors": results[-1]["errors"], "charts": results[-1]["plotly_charts"]})
        ctx.close()
        browser.close()
    (OUT / "interactions.json").write_text(json.dumps(checks, indent=2, ensure_ascii=False), encoding="utf-8")
    for c in checks:
        print(json.dumps(c, ensure_ascii=False))
    (OUT / "report.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
