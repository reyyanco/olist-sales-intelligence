"""COPY ile pandas DataFrame.to_sql karşılaştırması.

Eşit koşullar:
- Aynı kaynak dosya (data/raw), aynı hedef tablo tanımı (perf.load_target, tüm kolonlar text),
  hedefte indeks yok.
- Her çalışma tek işlem: TRUNCATE + yükleme + COMMIT.
- Süre uçtan uca ölçülür: dosyayı okumak dahil. to_sql için pandas.read_csv ayrıca ölçülür.
- Sonuç doğrulaması: satır sayısı ve tüm satırların sıralı MD5 özeti her yöntemde aynı olmalı.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import sqlalchemy
from sqlalchemy import Engine, text

from perf.harness import Measurement

SOURCE_FILE = "olist_order_items_dataset.csv"
COLUMNS = ["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"]
WARMUP, RUNS = 1, 5

METHODS = [
    {"name": "copy_from_stdin", "kind": "copy"},
    {"name": "to_sql_default_chunk10000", "kind": "to_sql", "method": None, "chunksize": 10000},
    {"name": "to_sql_multi_chunk1000", "kind": "to_sql", "method": "multi", "chunksize": 1000},
]


def _prepare(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS perf"))
        conn.execute(text("DROP TABLE IF EXISTS perf.load_target"))
        conn.execute(text("CREATE TABLE perf.load_target (" + ", ".join(f"{c} text" for c in COLUMNS) + ")"))


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)


def _load_once(engine: Engine, path: Path, method: dict) -> float:
    started = time.perf_counter()
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE perf.load_target"))
        if method["kind"] == "copy":
            cursor = conn.connection.cursor()
            with path.open("rb") as fh:
                cursor.copy_expert(
                    f"COPY perf.load_target ({', '.join(COLUMNS)}) FROM STDIN WITH (FORMAT csv, HEADER true)", fh
                )
            cursor.close()
        else:
            _read(path).to_sql(
                "load_target", conn, schema="perf", if_exists="append", index=False,
                method=method["method"], chunksize=method["chunksize"],
            )
    return round((time.perf_counter() - started) * 1000, 3)


def _verify(engine: Engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT count(*), md5(string_agg(t::text, '|' ORDER BY t::text)) FROM perf.load_target t"
        )).one()
    return {"rows": row[0], "content_md5": row[1]}


def run(engine: Engine, raw_dir: Path) -> dict:
    path = raw_dir / SOURCE_FILE
    _prepare(engine)
    read_timings = []
    for i in range(WARMUP + RUNS):
        started = time.perf_counter()
        _read(path)
        if i >= WARMUP:
            read_timings.append(round((time.perf_counter() - started) * 1000, 3))

    results = []
    for method in METHODS:
        timings = []
        for i in range(WARMUP + RUNS):
            elapsed = _load_once(engine, path, method)
            if i >= WARMUP:
                timings.append(elapsed)
        results.append({**method, **Measurement(timings, 0, "", WARMUP).to_dict(), "verify": _verify(engine)})

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE perf.load_target"))
    digests = {r["verify"]["content_md5"] for r in results}
    return {
        "source_file": SOURCE_FILE,
        "source_bytes": path.stat().st_size,
        "target_table": "perf.load_target (" + ", ".join(f"{c} text" for c in COLUMNS) + "), indeks yok",
        "transaction": "her çalışma: BEGIN; TRUNCATE; yükleme; COMMIT",
        "pandas_read_csv": {"kwargs": "dtype=str, keep_default_na=False, na_filter=False",
                            **Measurement(read_timings, 0, "", WARMUP).to_dict()},
        "versions": {"pandas": pd.__version__, "sqlalchemy": sqlalchemy.__version__},
        "to_sql_common_kwargs": "schema='perf', if_exists='append', index=False",
        "methods": results,
        "all_results_identical": len(digests) == 1,
    }
