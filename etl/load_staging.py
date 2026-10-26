"""Kaynak CSV dosyalarını staging tablolarına olduğu gibi yükler (istemciden COPY FROM STDIN).

Dosyalar yalnızca okunur ("rb"); hiçbir kaynak dosya değiştirilmez. Başlıkta zorunlu kolonların
tamamı bulunmalı, bilinmeyen veya tekrarlanan kolon olmamalıdır; kolon sırası farklı olabilir
(COPY kolon listesi başlıktaki sırayla verilir).
"""

from __future__ import annotations

import csv
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection, Engine, text

from etl.profile import FILES


class StagingLoadError(RuntimeError):
    """Kaynak dosya staging tablosuna yüklenemedi."""


@dataclass(frozen=True)
class LoadedTable:
    table: str
    source_file: str
    rows: int
    seconds: float


@contextmanager
def connection_scope(target: Engine | Connection) -> Iterator[Connection]:
    """Engine verilirse kendi işlemini açar; Connection verilirse çağıranın işlemini kullanır."""
    if isinstance(target, Engine):
        with target.begin() as conn:
            yield conn
    else:
        yield target


def read_header(path: Path) -> list[str]:
    # utf-8-sig: category_translation dosyasının başında BOM var (profil).
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return next(csv.reader(fh), [])


def staging_columns(conn: Connection, table: str) -> list[str]:
    """Kaynak kolonlar; _ ile başlayan teknik kolonlar (_row_id) hariç."""
    return list(
        conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'staging' AND table_name = :table AND column_name NOT LIKE '\\_%' "
                "ORDER BY ordinal_position"
            ),
            {"table": table},
        ).scalars()
    )


def check_header(file_name: str, table: str, header: list[str], expected: list[str]) -> None:
    duplicated = sorted(c for c, n in Counter(header).items() if n > 1)
    missing = [c for c in expected if c not in header]
    unexpected = [c for c in header if c not in expected]
    if duplicated or missing or unexpected:
        raise StagingLoadError(
            f"{file_name} başlığı staging.{table} kolonlarıyla uyuşmuyor: "
            f"eksik={missing}, fazla={unexpected}, tekrarlanan={duplicated}"
        )


def load_staging(target: Engine | Connection, source_dir: Path) -> list[LoadedTable]:
    missing = [name for name in FILES.values() if not (source_dir / name).is_file()]
    if missing:
        raise StagingLoadError(f"Eksik kaynak dosyalar ({source_dir}): {', '.join(missing)}")

    loaded: list[LoadedTable] = []
    with connection_scope(target) as conn:
        # Önce tüm başlıklar kontrol edilir; bir dosya hatalıysa hiçbir tablo boşaltılmaz.
        plan = []
        for table, file_name in FILES.items():
            expected = staging_columns(conn, table)
            if not expected:
                raise StagingLoadError(f"staging.{table} tablosu yok; önce 'migrate' çalıştırın")
            header = read_header(source_dir / file_name)
            check_header(file_name, table, header, expected)
            plan.append((table, file_name, header))

        for table, file_name, header in plan:
            started = time.monotonic()
            # RESTART IDENTITY: _row_id her yüklemede 1'den başlar (kaynak kayıt sırası).
            conn.execute(text(f"TRUNCATE staging.{table} RESTART IDENTITY"))
            cursor = conn.connection.cursor()
            try:
                with (source_dir / file_name).open("rb") as fh:
                    cursor.copy_expert(
                        f"COPY staging.{table} ({', '.join(header)}) "
                        "FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')",
                        fh,
                    )
                rows = cursor.rowcount
            finally:
                cursor.close()
            loaded.append(LoadedTable(table, file_name, rows, round(time.monotonic() - started, 3)))
    return loaded
