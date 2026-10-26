"""Olist CSV dosyalarının profilini çıkarır ve Markdown rapor üretir.

Tüm değerler metin olarak okunur (tip dönüşümü yapılmaz); boş hücre boş metin
olarak sayılır. Rapor yalnızca ölçülen değerleri içerir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pandas as pd

INT_RE = re.compile(r"^-?\d+$")
DECIMAL_RE = re.compile(r"^-?\d+\.\d+$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
HEX32_RE = re.compile(r"^[0-9a-f]{32}$")

FILES = {
    "customers": "olist_customers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}

# Aday anahtarlar: (tablo, kolonlar)
CANDIDATE_KEYS = [
    ("customers", ["customer_id"]),
    ("customers", ["customer_unique_id"]),
    ("orders", ["order_id"]),
    ("orders", ["customer_id"]),
    ("order_items", ["order_id", "order_item_id"]),
    ("order_payments", ["order_id", "payment_sequential"]),
    ("order_reviews", ["review_id"]),
    ("order_reviews", ["order_id"]),
    ("order_reviews", ["review_id", "order_id"]),
    ("products", ["product_id"]),
    ("sellers", ["seller_id"]),
    ("category_translation", ["product_category_name"]),
    ("geolocation", ["geolocation_zip_code_prefix"]),
]

# İlişkiler: (alt tablo, alt kolon, üst tablo, üst kolon)
RELATIONSHIPS = [
    ("orders", "customer_id", "customers", "customer_id"),
    ("order_items", "order_id", "orders", "order_id"),
    ("order_items", "product_id", "products", "product_id"),
    ("order_items", "seller_id", "sellers", "seller_id"),
    ("order_payments", "order_id", "orders", "order_id"),
    ("order_reviews", "order_id", "orders", "order_id"),
    ("products", "product_category_name", "category_translation", "product_category_name"),
    ("customers", "customer_zip_code_prefix", "geolocation", "geolocation_zip_code_prefix"),
    ("sellers", "seller_zip_code_prefix", "geolocation", "geolocation_zip_code_prefix"),
]


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    empty: int
    distinct: int
    inferred_type: str
    min_value: str
    max_value: str
    max_length: int
    padded: int  # baş/son boşluk içeren değer sayısı


def read_csv_as_text(path: Path) -> pd.DataFrame:
    # utf-8-sig: dosya başında BOM varsa kolon adına karışmaz.
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False, encoding="utf-8-sig")


def has_bom(path: Path) -> bool:
    with path.open("rb") as fh:
        return fh.read(3) == b"\xef\xbb\xbf"


def infer_type(values: pd.Series) -> str:
    if values.empty:
        return "boş"
    if values.str.match(r"^\d+$").all() and values.str.match(r"^0\d").any():
        return "text (yalnız rakam; baştaki sıfırlar anlamlı)"
    if values.str.match(INT_RE).all():
        return "integer"
    if values.str.match(r"^-?\d+(\.\d+)?$").all():
        scale = values.str.extract(r"\.(\d+)$")[0].dropna().str.len()
        precision = values.str.replace("-", "", regex=False).str.split(".").str[0].str.len().max()
        return f"decimal (tam kısım ≤{precision} hane, ondalık ≤{int(scale.max()) if not scale.empty else 0})"
    if values.str.match(TIMESTAMP_RE).all():
        return "timestamp (YYYY-MM-DD HH:MM:SS, saat dilimi yok)"
    if values.str.match(HEX32_RE).all():
        return "text (32 hane küçük harf hex)"
    return "text"


def profile_column(series: pd.Series) -> ColumnProfile:
    non_empty = series[series != ""]
    inferred = infer_type(non_empty)
    if non_empty.empty:
        min_v = max_v = ""
    elif inferred.startswith(("integer", "decimal")):
        # Decimal: kayan nokta yuvarlaması ve "6735.0" gibi biçim değişikliği olmaz.
        numeric = non_empty.map(Decimal)
        min_v, max_v = str(numeric.min()), str(numeric.max())
    else:
        min_v, max_v = str(non_empty.min()), str(non_empty.max())
    return ColumnProfile(
        name=str(series.name),
        empty=int((series == "").sum()),
        distinct=int(non_empty.nunique()),
        inferred_type=inferred,
        min_value=min_v,
        max_value=max_v,
        max_length=int(series.str.len().max()) if len(series) else 0,
        padded=int((series != series.str.strip()).sum()),
    )


def load_all(source_dir: Path) -> dict[str, pd.DataFrame]:
    missing = [name for name in FILES.values() if not (source_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Eksik kaynak dosyalar: {', '.join(missing)}")
    return {key: read_csv_as_text(source_dir / name) for key, name in FILES.items()}


def _fmt(value: str, limit: int = 40) -> str:
    value = value.replace("|", "\\|").replace("\n", " ")
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _distribution(counts: pd.Series) -> str:
    """Üst başına alt kayıt sayısı dağılımı: 1, 2, 3+ ."""
    if counts.empty:
        return "-"
    one = int((counts == 1).sum())
    two = int((counts == 2).sum())
    more = int((counts >= 3).sum())
    return f"1: {one:,} · 2: {two:,} · 3+: {more:,} · en çok: {int(counts.max())}"


def section_files(frames: dict[str, pd.DataFrame], source_dir: Path) -> list[str]:
    lines = ["## Dosyalar", "", "| Tablo | Dosya | Satır | Kolon | BOM |", "|---|---|---:|---:|---|"]
    for key, name in FILES.items():
        df = frames[key]
        lines.append(f"| {key} | `{name}` | {len(df):,} | {len(df.columns)} | {'var' if has_bom(source_dir / name) else 'yok'} |")
    return lines + [""]


def section_columns(frames: dict[str, pd.DataFrame]) -> list[str]:
    lines = ["## Kolonlar", ""]
    for key, df in frames.items():
        lines += [
            f"### {key}",
            "",
            "| Kolon | Boş | Farklı | Çıkarılan tip | En küçük | En büyük | En uzun | Baş/son boşluk |",
            "|---|---:|---:|---|---|---|---:|---:|",
        ]
        for col in df.columns:
            p = profile_column(df[col])
            lines.append(
                f"| `{p.name}` | {p.empty:,} | {p.distinct:,} | {p.inferred_type} | {_fmt(p.min_value)} | "
                f"{_fmt(p.max_value)} | {p.max_length} | {p.padded:,} |"
            )
        lines.append("")
    return lines


def section_keys(frames: dict[str, pd.DataFrame]) -> list[str]:
    lines = ["## Aday anahtarlar", "", "| Tablo | Kolonlar | Satır | Tekrarlanan anahtar değeri | Benzersiz mi |", "|---|---|---:|---:|---|"]
    for table, cols in CANDIDATE_KEYS:
        df = frames[table]
        dup = int(df.groupby(cols).size().gt(1).sum())
        lines.append(f"| {table} | `{', '.join(cols)}` | {len(df):,} | {dup:,} | {'evet' if dup == 0 else 'hayır'} |")
    return lines + [""]


def section_relationships(frames: dict[str, pd.DataFrame]) -> list[str]:
    lines = [
        "## İlişkiler ve çokluklar",
        "",
        "Yetim: alt tablodaki boş olmayan değerlerden üst tabloda karşılığı olmayanlar. "
        "Altsız üst: alt tabloda hiç kaydı olmayan üst değerler. Dağılım: alt tabloda görünen her üst değer için alt satır sayısı.",
        "",
        "| Alt → Üst | Alt boş | Yetim değer | Yetim satır | Altsız üst | Üst başına alt satır dağılımı |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for child, ccol, parent, pcol in RELATIONSHIPS:
        c = frames[child][ccol]
        p = frames[parent][pcol]
        parent_values = set(p[p != ""])
        non_empty = c[c != ""]
        orphan_mask = ~non_empty.isin(parent_values)
        counts = non_empty[~orphan_mask].value_counts()
        childless = len(parent_values - set(non_empty))
        lines.append(
            f"| `{child}.{ccol}` → `{parent}.{pcol}` | {int((c == '').sum()):,} | {non_empty[orphan_mask].nunique():,} | "
            f"{int(orphan_mask.sum()):,} | {childless:,} | {_distribution(counts)} |"
        )
    return lines + [""]


def _ts(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.where(series != ""), format="%Y-%m-%d %H:%M:%S")


def section_domain_checks(frames: dict[str, pd.DataFrame]) -> list[str]:
    orders, items, payments = frames["orders"], frames["order_items"], frames["order_payments"]
    reviews, products, translation = frames["order_reviews"], frames["products"], frames["category_translation"]
    customers = frames["customers"]
    lines = ["## Alana özgü kontroller", ""]

    status = orders["order_status"].value_counts()
    lines += ["### Sipariş durumları", "", "| order_status | Sipariş |", "|---|---:|"]
    lines += [f"| {s} | {n:,} |" for s, n in status.items()] + [""]

    ts_cols = [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]
    lines += ["### Sipariş zamanlarının duruma göre boş sayısı", "", "| order_status | " + " | ".join(ts_cols) + " |", "|---|" + "---:|" * len(ts_cols)]
    for s in status.index:
        sub = orders[orders["order_status"] == s]
        lines.append(f"| {s} | " + " | ".join(f"{int((sub[c] == '').sum()):,}" for c in ts_cols) + " |")
    lines.append("")

    t = {c: _ts(orders[c]) for c in ts_cols}
    est = orders["order_estimated_delivery_date"]
    est_non_midnight = int(((est != "") & ~est.str.endswith(" 00:00:00")).sum())
    delivered_ts = t["order_delivered_customer_date"]
    late = (delivered_ts.dt.normalize() > t["order_estimated_delivery_date"].dt.normalize()) & delivered_ts.notna()
    lines += [
        "### Zaman tutarlılığı",
        "",
        "| Kontrol | Sipariş |",
        "|---|---:|",
        f"| approved_at < purchase_timestamp | {int((t['order_approved_at'] < t['order_purchase_timestamp']).sum()):,} |",
        f"| delivered_carrier_date < purchase_timestamp | {int((t['order_delivered_carrier_date'] < t['order_purchase_timestamp']).sum()):,} |",
        f"| delivered_carrier_date < approved_at | {int((t['order_delivered_carrier_date'] < t['order_approved_at']).sum()):,} |",
        f"| delivered_customer_date < purchase_timestamp | {int((delivered_ts < t['order_purchase_timestamp']).sum()):,} |",
        f"| delivered_customer_date < delivered_carrier_date | {int((delivered_ts < t['order_delivered_carrier_date']).sum()):,} |",
        f"| estimated_delivery_date saati 00:00:00 değil | {est_non_midnight:,} |",
        f"| teslim tarihi (gün) > tahmini teslim tarihi (gün) | {int(late.sum()):,} |",
        "",
        "| Zaman kolonu | En erken | En geç |",
        "|---|---|---|",
    ]
    lines += [f"| `{c}` | {t[c].min()} | {t[c].max()} |" for c in ts_cols]
    for name, frame, col in [
        ("order_items", items, "shipping_limit_date"),
        ("order_reviews", reviews, "review_creation_date"),
        ("order_reviews", reviews, "review_answer_timestamp"),
    ]:
        s = _ts(frame[col])
        lines.append(f"| `{name}.{col}` | {s.min()} | {s.max()} |")
    lines.append("")

    # Kalemler
    per_order = items.groupby("order_id")
    item_ids = items["order_item_id"].astype(int)
    seq_ok = per_order["order_item_id"].apply(lambda s: sorted(s.astype(int)) == list(range(1, len(s) + 1)))
    same_product = items.groupby(["order_id", "product_id"]).size()
    price_var = items.groupby(["order_id", "product_id"])["price"].nunique()
    orders_without_items = orders[~orders["order_id"].isin(items["order_id"])]
    lines += [
        "### Sipariş kalemleri",
        "",
        "| Kontrol | Değer |",
        "|---|---:|",
        f"| order_item_id en küçük / en büyük | {item_ids.min()} / {item_ids.max()} |",
        f"| order_item_id 1..n kesintisiz olan sipariş | {int(seq_ok.sum()):,} / {len(seq_ok):,} |",
        f"| aynı ürün aynı siparişte birden fazla satır (sipariş-ürün çifti) | {int((same_product > 1).sum()):,} |",
        f"| aynı sipariş-ürün çiftinde birden fazla farklı fiyat | {int((price_var > 1).sum()):,} |",
        f"| price = 0 olan kalem | {int((pd.to_numeric(items['price']) == 0).sum()):,} |",
        f"| freight_value = 0 olan kalem | {int((pd.to_numeric(items['freight_value']) == 0).sum()):,} |",
        f"| kalemi olmayan sipariş | {len(orders_without_items):,} |",
        "",
        "Kalemi olmayan siparişlerin durumları: "
        + ", ".join(f"{s}={n:,}" for s, n in orders_without_items["order_status"].value_counts().items()),
        "",
    ]

    # Ödemeler
    pv = pd.to_numeric(payments["payment_value"])
    inst = pd.to_numeric(payments["payment_installments"])
    pay_total = pv.groupby(payments["order_id"]).sum()
    item_total = (pd.to_numeric(items["price"]) + pd.to_numeric(items["freight_value"])).groupby(items["order_id"]).sum()
    both = pd.concat([pay_total.rename("pay"), item_total.rename("items")], axis=1, join="inner")
    diff = (both["pay"] - both["items"]).round(2)
    seq = payments.groupby("order_id")["payment_sequential"].apply(lambda s: sorted(s.astype(int)) == list(range(1, len(s) + 1)))
    lines += [
        "### Ödemeler",
        "",
        "| Kontrol | Değer |",
        "|---|---:|",
        "| payment_type değerleri | " + ", ".join(f"{k}={v:,}" for k, v in payments["payment_type"].value_counts().items()) + " |",
        f"| payment_installments en küçük / en büyük | {inst.min()} / {inst.max()} |",
        f"| payment_installments = 0 | {int((inst == 0).sum()):,} |",
        f"| payment_value = 0 | {int((pv == 0).sum()):,} |",
        f"| payment_sequential 1..n kesintisiz olan sipariş | {int(seq.sum()):,} / {len(seq):,} |",
        f"| ödemesi olmayan sipariş | {int((~orders['order_id'].isin(payments['order_id'])).sum()):,} |",
        f"| ödeme toplamı = kalem fiyatı + kargo (±0,01) olan sipariş | {int((diff.abs() <= 0.01).sum()):,} / {len(diff):,} |",
        f"| ödeme toplamı > kalem + kargo (0,01'den fazla) | {int((diff > 0.01).sum()):,} |",
        f"| ödeme toplamı < kalem + kargo (0,01'den fazla) | {int((diff < -0.01).sum()):,} |",
        "",
    ]

    # Yorumlar
    rev_per_order = reviews.groupby("order_id").size()
    lines += [
        "### Yorumlar",
        "",
        "| Kontrol | Değer |",
        "|---|---:|",
        "| review_score değerleri | " + ", ".join(f"{k}={v:,}" for k, v in reviews["review_score"].value_counts().sort_index().items()) + " |",
        f"| birden fazla siparişte görünen review_id | {int((reviews.groupby('review_id')['order_id'].nunique() > 1).sum()):,} |",
        f"| birden fazla yorumu olan sipariş | {int((rev_per_order > 1).sum()):,} |",
        f"| yorumu olmayan sipariş | {int((~orders['order_id'].isin(reviews['order_id'])).sum()):,} |",
        "",
    ]

    # Ürünler, müşteriler, posta kodları
    cats = set(products["product_category_name"]) - {""}
    untranslated = sorted(cats - set(translation["product_category_name"]))
    unique_per_customer = customers.groupby("customer_unique_id")["customer_id"].nunique()
    zip_lengths = {
        f"{name}.{col}": frame[col].str.len().value_counts().sort_index().to_dict()
        for name, frame, col in [
            ("customers", customers, "customer_zip_code_prefix"),
            ("sellers", frames["sellers"], "seller_zip_code_prefix"),
            ("geolocation", frames["geolocation"], "geolocation_zip_code_prefix"),
        ]
    }
    lines += [
        "### Ürün, müşteri ve posta kodu",
        "",
        "| Kontrol | Değer |",
        "|---|---:|",
        f"| kategorisi boş ürün | {int((products['product_category_name'] == '').sum()):,} |",
        f"| çevirisi olmayan kategori | {len(untranslated)}: {', '.join(untranslated) or '-'} |",
        f"| birden fazla customer_id'si olan customer_unique_id | {int((unique_per_customer > 1).sum()):,} |",
        f"| customer_unique_id başına customer_id en çok | {int(unique_per_customer.max())} |",
    ]
    lines += [f"| `{k}` uzunluk dağılımı | {', '.join(f'{l} hane: {n:,}' for l, n in v.items())} |" for k, v in zip_lengths.items()]
    state_cols = [("customers", customers, "customer_state"), ("sellers", frames["sellers"], "seller_state")]
    lines += [f"| `{n}.{c}` 2 büyük harf olmayan | {int((~f[c].str.match(r'^[A-Z]{2}$')).sum()):,} |" for n, f, c in state_cols]
    lines.append("")
    return lines


def build_report(source_dir: Path) -> str:
    frames = load_all(source_dir)
    lines = [
        "# Kaynak Veri Profili",
        "",
        f"Kaynak klasör: `{source_dir}`. Bu rapor `python -m etl profile` ile dosyalardan üretilir; elle düzenlenmez.",
        "Tüm değerler metin olarak okunmuştur. 'Boş' = boş hücre.",
        "",
    ]
    lines += section_files(frames, source_dir)
    lines += section_keys(frames)
    lines += section_relationships(frames)
    lines += section_domain_checks(frames)
    lines += section_columns(frames)
    return "\n".join(lines) + "\n"
