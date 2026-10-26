"""CSV -> staging -> dw tam yenileme hattı, run_id kaydı ve kalite kontrolleri.

İşlem sınırları:
- meta.etl_runs başlangıç ve bitiş kayıtları veri işleminden AYRI, kısa işlemlerde yazılır;
  yükleme geri alınsa bile 'failed' kaydı ve hata nedeni kalır.
- staging yüklemesi, dw dönüşümü, materialized view yenilemesi, ret kayıtları, dosya sayımları ve
  kontrol sonuçları TEK işlemdedir. 'error' düzeyindeki bir kontrol başarısızsa veya herhangi bir adım
  hata verirse hepsi geri alınır; önceki taahhüt edilmiş veri olduğu gibi kalır.
- dw tabloları DELETE ile yenilenir; işlem sürerken okuyanlar önceki veriyi görür (MVCC).
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Connection, Engine, text

from etl.load_staging import StagingLoadError, load_staging
from etl.profile import FILES
from etl.transform import SQL_REPORTS_DIR, SQL_TESTS_DIR, run_sql_queries, run_transform

log = logging.getLogger("etl.pipeline")

# Aynı anda iki yükleme çalışmasın (işlem sonunda otomatik bırakılır).
PIPELINE_LOCK_KEY = 4_820_017
# Yalnızca staging'de tutulan, dw'ye dönüştürülmeyen tablo.
STAGING_ONLY_TABLES = {"geolocation"}


class QualityCheckError(RuntimeError):
    """En az bir 'error' düzeyindeki kalite kontrolü başarısız."""


class SourceChangedError(RuntimeError):
    """Kaynak dosya yükleme sırasında değişti."""


@dataclass
class FileStat:
    source_table: str
    file_name: str
    file_sha256: str
    file_bytes: int
    source_rows: int
    staged_rows: int | None = None
    accepted_rows: int | None = None
    rejected_rows: int | None = None
    duplicate_rows: int | None = None
    load_seconds: float | None = None


@dataclass(frozen=True)
class CheckResult:
    name: str
    severity: str  # 'error' | 'info'
    passed: bool
    rows: list[dict]


@dataclass
class RunResult:
    run_id: uuid.UUID
    status: str
    duration_seconds: float
    files: list[FileStat] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    error: str | None = None


def inspect_source_file(path: Path) -> tuple[str, int, int]:
    """SHA-256, bayt sayısı ve veri kaydı sayısı (başlık hariç; tırnak içi satır sonları tek kayıt)."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    with path.open(encoding="utf-8-sig", newline="") as fh:
        records = sum(1 for _ in csv.reader(fh)) - 1
    return digest.hexdigest(), path.stat().st_size, max(records, 0)


def _json(rows: list[dict]) -> str:
    return json.dumps(rows, default=str, ensure_ascii=False)


def _short_error(exc: BaseException) -> str:
    detail = str(getattr(exc, "orig", None) or exc).strip().splitlines()
    return f"{type(exc).__name__}: {detail[0] if detail else ''}"[:2000]


def _start_run(engine: Engine, run_id: uuid.UUID, source_dir: Path) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO meta.etl_runs (run_id, status, source_dir) VALUES (:r, 'running', :s)"),
            {"r": str(run_id), "s": str(source_dir)},
        )


def _write_details(conn: Connection, run_id: uuid.UUID, files: list[FileStat], checks: list[CheckResult]) -> None:
    for f in files:
        conn.execute(
            text(
                "INSERT INTO meta.etl_run_files (run_id, source_table, file_name, file_sha256, file_bytes, "
                "source_rows, staged_rows, accepted_rows, rejected_rows, duplicate_rows, load_seconds) "
                "VALUES (:run_id, :source_table, :file_name, :file_sha256, :file_bytes, :source_rows, "
                ":staged_rows, :accepted_rows, :rejected_rows, :duplicate_rows, :load_seconds)"
            ),
            {**f.__dict__, "run_id": str(run_id)},
        )
    for c in checks:
        conn.execute(
            text(
                "INSERT INTO meta.etl_run_checks (run_id, check_name, severity, passed, row_count, details) "
                "VALUES (:r, :n, :s, :p, :c, CAST(:d AS jsonb))"
            ),
            {"r": str(run_id), "n": c.name, "s": c.severity, "p": c.passed, "c": len(c.rows), "d": _json(c.rows)},
        )


def _finish_run(engine: Engine, result: RunResult, details_committed: bool) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE meta.etl_runs SET status = :st, finished_at = now(), duration_seconds = :d, "
                "error_message = :e WHERE run_id = :r"
            ),
            {"st": result.status, "d": result.duration_seconds, "e": result.error, "r": str(result.run_id)},
        )
        if not details_committed:
            # Veri işlemi geri alındı; o ana kadar toplanan sayım ve kontroller burada saklanır.
            _write_details(conn, result.run_id, result.files, result.checks)


def _collect_dispositions(conn: Connection, files: list[FileStat]) -> None:
    counts = {
        (r.source_table, r.disposition): r.n
        for r in conn.execute(
            text(
                "SELECT source_table, disposition, count(*) AS n FROM meta.etl_rejected_rows "
                "WHERE run_id = meta.current_run_id() GROUP BY 1, 2"
            )
        )
    }
    for f in files:
        f.rejected_rows = counts.get((f.source_table, "rejected"), 0)
        f.duplicate_rows = counts.get((f.source_table, "duplicate_removed"), 0)
        f.accepted_rows = f.staged_rows - f.rejected_rows - f.duplicate_rows


def _source_reconciliation(files: list[FileStat]) -> CheckResult:
    mismatches = [
        {"source_table": f.source_table, "source_rows": f.source_rows, "staged_rows": f.staged_rows}
        for f in files
        if f.source_rows != f.staged_rows
    ]
    return CheckResult("000_source_rows_match_staging", "error", not mismatches, mismatches)


def run_pipeline(
    engine: Engine,
    source_dir: Path,
    tests_dir: Path = SQL_TESTS_DIR,
    reports_dir: Path = SQL_REPORTS_DIR,
) -> RunResult:
    run_id = uuid.uuid4()
    started = time.monotonic()
    result = RunResult(run_id=run_id, status="running", duration_seconds=0.0)
    _start_run(engine, run_id, source_dir)
    log.info("Çalışma başladı: run_id=%s, kaynak=%s", run_id, source_dir)

    details_committed = False
    try:
        missing = [name for name in FILES.values() if not (source_dir / name).is_file()]
        if missing:
            raise StagingLoadError(f"Eksik kaynak dosyalar ({source_dir}): {', '.join(missing)}")
        for table, file_name in FILES.items():
            sha, size, records = inspect_source_file(source_dir / file_name)
            result.files.append(FileStat(table, file_name, sha, size, records))

        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": PIPELINE_LOCK_KEY})
            conn.execute(text("SELECT set_config('etl.run_id', :r, true)"), {"r": str(run_id)})

            by_table = {f.source_table: f for f in result.files}
            for loaded in load_staging(conn, source_dir):
                by_table[loaded.table].staged_rows = loaded.rows
                by_table[loaded.table].load_seconds = loaded.seconds

            run_transform(conn)
            _collect_dispositions(conn, result.files)

            result.checks.append(_source_reconciliation(result.files))
            for name, rows in run_sql_queries(conn, tests_dir):
                result.checks.append(CheckResult(name, "error", not rows, rows))
            for name, rows in run_sql_queries(conn, reports_dir):
                result.checks.append(CheckResult(f"report/{name}", "info", True, rows))

            for f in result.files:
                if inspect_source_file(source_dir / f.file_name)[0] != f.file_sha256:
                    raise SourceChangedError(f"{f.file_name} yükleme sırasında değişti")

            failed = [c.name for c in result.checks if c.severity == "error" and not c.passed]
            if failed:
                raise QualityCheckError(f"Başarısız kalite kontrolleri: {', '.join(failed)}")

            _write_details(conn, run_id, result.files, result.checks)
        details_committed = True
        result.status = "succeeded"
    except BaseException as exc:
        result.status = "failed"
        result.error = _short_error(exc)
        raise
    finally:
        result.duration_seconds = round(time.monotonic() - started, 3)
        try:
            _finish_run(engine, result, details_committed)
        except Exception:  # Kayıt yazılamazsa asıl hatayı gizleme; ayrıca bildir.
            log.exception("Çalışma kaydı güncellenemedi: run_id=%s", run_id)
        log.info("Çalışma bitti: run_id=%s, durum=%s, süre=%.3f s", run_id, result.status, result.duration_seconds)
    return result
