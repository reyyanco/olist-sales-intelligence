"""staging -> dw dönüşümü ile sql/tests (hata) ve sql/reports (bilgi) sorguları."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection, Engine, text

from etl.db import execute_script
from etl.load_staging import connection_scope

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRANSFORM_SQL = PROJECT_ROOT / "sql" / "transform" / "load_dw.sql"
SQL_TESTS_DIR = PROJECT_ROOT / "sql" / "tests"
SQL_REPORTS_DIR = PROJECT_ROOT / "sql" / "reports"


@dataclass(frozen=True)
class SqlCheckResult:
    name: str
    failing_rows: list[dict]

    @property
    def passed(self) -> bool:
        return not self.failing_rows


def run_transform(target: Engine | Connection, sql_path: Path = TRANSFORM_SQL) -> None:
    """Dönüşümü çalıştırır. etl.run_id ayarlı olmalıdır (etl/pipeline.py)."""
    with connection_scope(target) as conn:
        execute_script(conn, sql_path.read_text(encoding="utf-8"))


def run_sql_queries(target: Engine | Connection, directory: Path) -> list[tuple[str, list[dict]]]:
    results = []
    with connection_scope(target) as conn:
        for path in sorted(directory.glob("*.sql")):
            rows = conn.execute(text(path.read_text(encoding="utf-8"))).mappings().all()
            results.append((path.name, [dict(r) for r in rows]))
    return results


def run_sql_checks(target: Engine | Connection, directory: Path = SQL_TESTS_DIR) -> list[SqlCheckResult]:
    """Her .sql dosyası uyumsuzlukları döndüren bir sorgudur; boş sonuç = geçti."""
    return [SqlCheckResult(name, rows) for name, rows in run_sql_queries(target, directory)]
