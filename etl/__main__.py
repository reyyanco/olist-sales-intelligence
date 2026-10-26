"""Komut satırı: python -m etl {check,migrate,load,verify,run,runs,refresh-reports,setup-dashboard-role,profile}"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from etl.dashboard_role import dashboard_credentials, ensure_dashboard_role
from etl.db import create_db_engine, fetch_server_info
from etl.load_staging import StagingLoadError
from etl.pipeline import QualityCheckError, SourceChangedError, run_pipeline
from etl.settings import SettingsError, load_settings
from etl.sql_runner import SqlRunnerError, apply_sql_files
from etl.transform import run_sql_checks

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = PROJECT_ROOT / "sql"
RAW_DIR = PROJECT_ROOT / "data" / "raw"

log = logging.getLogger("etl")


class VerificationError(RuntimeError):
    """En az bir SQL doğrulaması başarısız."""


def cmd_check(engine: Engine) -> None:
    info = fetch_server_info(engine)
    log.info(
        "Bağlantı başarılı: PostgreSQL %s, veritabanı=%s, kullanıcı=%s",
        info.server_version,
        info.database,
        info.user,
    )


def cmd_migrate(engine: Engine) -> None:
    applied = apply_sql_files(engine, SQL_DIR)
    if applied:
        for sql_file in applied:
            log.info("Uygulandı: %s", sql_file.name)
        log.info("Toplam %d SQL dosyası uygulandı.", len(applied))
    else:
        log.info("Uygulanacak yeni SQL dosyası yok.")


def cmd_load(engine: Engine, source: Path) -> None:
    result = run_pipeline(engine, source)
    log.info("%-22s %10s %10s %10s %10s %10s", "tablo", "kaynak", "staging", "kabul", "ret", "tekrar")
    for f in result.files:
        log.info(
            "%-22s %10d %10d %10d %10d %10d",
            f.source_table, f.source_rows, f.staged_rows, f.accepted_rows, f.rejected_rows, f.duplicate_rows,
        )
    for c in result.checks:
        if c.severity == "error":
            log.info("Kontrol geçti: %s", c.name)
        else:
            log.info("Rapor: %s (%d satır)", c.name, len(c.rows))
    log.info("run_id=%s, süre=%.3f s", result.run_id, result.duration_seconds)


def cmd_runs(engine: Engine, limit: int) -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT run_id, started_at, duration_seconds, status, error_message FROM meta.etl_runs "
                "ORDER BY started_at DESC LIMIT :n"
            ),
            {"n": limit},
        ).all()
    for r in rows:
        log.info("%s %s %8s s %-9s %s", r.run_id, r.started_at.strftime("%Y-%m-%d %H:%M:%S%z"),
                 r.duration_seconds, r.status, r.error_message or "")


def cmd_refresh_reports(engine: Engine) -> None:
    # Prosedür COMMIT içerir; PostgreSQL kuralı gereği üst düzeyden (autocommit) CALL edilmelidir.
    with engine.execution_options(isolation_level="AUTOCOMMIT").connect() as conn:
        try:
            conn.execute(text("CALL reporting.sp_refresh_reports()"))
        finally:
            row = conn.execute(
                text("SELECT refresh_id, status, finished_at - started_at AS duration, details, error_message "
                     "FROM meta.report_refresh_runs ORDER BY refresh_id DESC LIMIT 1")
            ).one()
            log.info("Rapor yenileme: refresh_id=%s, durum=%s, süre=%s", row.refresh_id, row.status, row.duration)
            for item in row.details or []:
                log.info("  %s", item)
            if row.error_message:
                log.error("  %s", row.error_message)


def cmd_setup_dashboard_role(engine: Engine) -> None:
    user, password = dashboard_credentials()
    created = ensure_dashboard_role(engine, user, password)
    log.info("Dashboard rolü %s: %s (parola .env'den, gösterilmiyor)", "oluşturuldu" if created else "güncellendi", user)


def cmd_verify(engine: Engine) -> None:
    failed = 0
    for result in run_sql_checks(engine):
        if result.passed:
            log.info("Doğrulama geçti: %s", result.name)
        else:
            failed += 1
            log.error("Doğrulama başarısız: %s (%d satır)", result.name, len(result.failing_rows))
            for row in result.failing_rows[:5]:
                log.error("  %s", row)
    if failed:
        raise VerificationError(f"{failed} doğrulama başarısız")


def cmd_profile(source: Path, output: Path) -> None:
    from etl.profile import build_report

    output.write_text(build_report(source), encoding="utf-8")
    log.info("Profil raporu yazıldı: %s", output)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="python -m etl")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Veritabanına bağlanıp sunucu bilgisini sorgular")
    sub.add_parser("migrate", help="sql/ altındaki numaralı SQL dosyalarını uygular")
    load = sub.add_parser("load", help="CSV -> staging -> dw tam yenileme + kalite kontrolleri (tek işlem)")
    load.add_argument("--source", type=Path, default=RAW_DIR)
    sub.add_parser("verify", help="sql/tests altındaki doğrulama sorgularını çalıştırır")
    sub.add_parser("setup-dashboard-role", help="Dashboard giriş rolünü .env değerleriyle oluşturur/günceller")
    sub.add_parser("refresh-reports", help="reporting.sp_refresh_reports() çağırır (rapor nesneleri + durum kaydı)")
    runs = sub.add_parser("runs", help="Son ETL çalışmalarını listeler")
    runs.add_argument("--limit", type=int, default=10)
    run = sub.add_parser("run", help="migrate + load (load kalite kontrollerini içerir)")
    run.add_argument("--source", type=Path, default=RAW_DIR)
    profile = sub.add_parser("profile", help="Kaynak CSV dosyalarının profilini Markdown olarak yazar")
    profile.add_argument("--source", type=Path, default=RAW_DIR)
    profile.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "profile":
            cmd_profile(args.source, args.output)
            return 0
        engine = create_db_engine(load_settings())
        try:
            if args.command == "check":
                cmd_check(engine)
            elif args.command == "migrate":
                cmd_migrate(engine)
            elif args.command == "load":
                cmd_load(engine, args.source)
            elif args.command == "verify":
                cmd_verify(engine)
            elif args.command == "run":
                cmd_migrate(engine)
                cmd_load(engine, args.source)
            elif args.command == "setup-dashboard-role":
                cmd_setup_dashboard_role(engine)
            elif args.command == "refresh-reports":
                cmd_refresh_reports(engine)
            elif args.command == "runs":
                cmd_runs(engine, args.limit)
        finally:
            engine.dispose()
    except (SettingsError, SqlRunnerError, StagingLoadError, VerificationError, QualityCheckError,
            SourceChangedError, FileNotFoundError) as exc:
        log.error("%s", exc)
        return 1
    except SQLAlchemyError as exc:
        # Yalnızca sürücü mesajının ilk satırı yazılır (SQL metni ve parametreler yazılmaz).
        detail = str(getattr(exc, "orig", None) or exc).splitlines()[0]
        log.error("Veritabanı hatası (%s): %s", type(exc).__name__, detail)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
