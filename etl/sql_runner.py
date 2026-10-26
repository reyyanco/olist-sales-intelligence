"""sql/ klasöründeki numaralı SQL dosyalarını sırayla ve bir kez uygular.

Kurallar:
- Yalnızca klasörün en üst düzeyindeki dosyalar uygulanır; sql/queries/ ve
  sql/tests/ bu sürece dahil değildir.
- Dosya adı biçimi: NNN_aciklama.sql (NNN üç haneli, benzersiz sürüm numarası).
- Uygulanan her dosya, sürüm numarası ve SHA-256 özetiyle izleme tablosuna yazılır.
- Uygulanmış bir dosyanın içeriği değişirse hata verilir; değişiklik yeni bir
  numaralı dosya ile yapılmalıdır.
- Her dosya kendi işleminde (transaction) çalışır; hata olursa o dosya geri alınır.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection, Engine, text

from etl.db import execute_script

FILENAME_PATTERN = re.compile(r"^(?P<version>\d{3})_[a-z0-9_]+\.sql$")
IDENTIFIER_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")
DEFAULT_TRACKING_SCHEMA = "meta"
# Aynı anda iki uygulayıcının çalışmasını önleyen advisory lock anahtarı.
ADVISORY_LOCK_KEY = 4_820_016


class SqlRunnerError(RuntimeError):
    """SQL dosyaları uygulanamadı."""


@dataclass(frozen=True)
class SqlFile:
    version: int
    name: str
    path: Path
    checksum: str


def discover_sql_files(directory: Path) -> list[SqlFile]:
    if not directory.is_dir():
        raise SqlRunnerError(f"SQL klasörü bulunamadı: {directory}")
    files: list[SqlFile] = []
    seen_versions: dict[int, str] = {}
    for path in sorted(p for p in directory.iterdir() if p.is_file() and p.suffix == ".sql"):
        match = FILENAME_PATTERN.match(path.name)
        if not match:
            raise SqlRunnerError(f"Geçersiz SQL dosya adı (beklenen NNN_aciklama.sql): {path.name}")
        version = int(match["version"])
        if version in seen_versions:
            raise SqlRunnerError(
                f"Aynı sürüm numarası iki dosyada: {seen_versions[version]}, {path.name}"
            )
        seen_versions[version] = path.name
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append(SqlFile(version=version, name=path.name, path=path, checksum=checksum))
    return sorted(files, key=lambda f: f.version)


def _ensure_tracking_table(conn: Connection, schema: str) -> None:
    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {schema}.schema_migrations (
                version     integer PRIMARY KEY,
                filename    text NOT NULL UNIQUE,
                checksum    char(64) NOT NULL,
                applied_at  timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )


def apply_sql_files(
    engine: Engine,
    directory: Path,
    tracking_schema: str = DEFAULT_TRACKING_SCHEMA,
) -> list[SqlFile]:
    """Henüz uygulanmamış dosyaları sırayla uygular ve uygulananları döndürür."""
    if not IDENTIFIER_PATTERN.match(tracking_schema):
        raise SqlRunnerError(f"Geçersiz şema adı: {tracking_schema}")
    files = discover_sql_files(directory)
    applied: list[SqlFile] = []

    with engine.connect() as conn:
        # Oturum düzeyindeki kilit, tüm dosyalar bitene kadar tutulur.
        conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": ADVISORY_LOCK_KEY})
        conn.commit()
        try:
            with conn.begin():
                _ensure_tracking_table(conn, tracking_schema)
            with conn.begin():
                recorded = {
                    row.version: row
                    for row in conn.execute(
                        text(f"SELECT version, filename, checksum FROM {tracking_schema}.schema_migrations")
                    )
                }

            for sql_file in files:
                previous = recorded.get(sql_file.version)
                if previous is not None:
                    if previous.filename != sql_file.name:
                        raise SqlRunnerError(
                            f"Sürüm {sql_file.version:03d} daha önce {previous.filename} olarak "
                            f"uygulanmış; şimdi {sql_file.name} adını taşıyor"
                        )
                    if previous.checksum != sql_file.checksum:
                        raise SqlRunnerError(
                            f"Uygulanmış dosyanın içeriği değişmiş: {sql_file.name}. "
                            "Değişikliği yeni numaralı bir dosya ile yapın."
                        )
                    continue

                with conn.begin():
                    execute_script(conn, sql_file.path.read_text(encoding="utf-8"))
                    conn.execute(
                        text(
                            f"INSERT INTO {tracking_schema}.schema_migrations (version, filename, checksum) "
                            "VALUES (:version, :filename, :checksum)"
                        ),
                        {"version": sql_file.version, "filename": sql_file.name, "checksum": sql_file.checksum},
                    )
                applied.append(sql_file)
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": ADVISORY_LOCK_KEY})
            conn.commit()

    return applied
