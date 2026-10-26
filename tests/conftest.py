"""Test altyapısı. Testler yalnızca ayrı test veritabanında (POSTGRES_TEST_DB) çalışır."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from etl.db import create_db_engine
from etl.settings import DatabaseSettings, load_settings
from etl.sql_runner import apply_sql_files

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = PROJECT_ROOT / "sql"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SAMPLE_DIR = FIXTURES_DIR / "olist_sample"
QUALITY_SAMPLE_DIR = FIXTURES_DIR / "olist_quality_sample"
REPORTING_SAMPLE_DIR = FIXTURES_DIR / "olist_reporting_sample"


@pytest.fixture(scope="session")
def test_settings() -> DatabaseSettings:
    settings = load_settings()
    test_db = os.environ.get("POSTGRES_TEST_DB", "")
    # Gerçek veritabanına yanlışlıkla yazmayı önleyen koruma.
    if not test_db.endswith("_test") or test_db == settings.database:
        pytest.exit(
            f"POSTGRES_TEST_DB '_test' ile bitmeli ve ana veritabanından farklı olmalı (değer: {test_db!r})",
            returncode=2,
        )
    return replace(settings, database=test_db)


@pytest.fixture(scope="session")
def test_engine(test_settings: DatabaseSettings) -> Iterator[Engine]:
    admin = create_db_engine(test_settings, database="postgres").execution_options(
        isolation_level="AUTOCOMMIT"
    )
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": test_settings.database}
        ).scalar()
        if not exists:
            quoted = conn.dialect.identifier_preparer.quote(test_settings.database)
            conn.execute(text(f"CREATE DATABASE {quoted}"))
    admin.dispose()

    engine = create_db_engine(test_settings)
    apply_sql_files(engine, SQL_DIR)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def admin_engine(test_settings: DatabaseSettings) -> Iterator[Engine]:
    """Veritabanı oluşturma/silme için bakım veritabanına AUTOCOMMIT bağlantı."""
    engine = create_db_engine(test_settings, database="postgres").execution_options(isolation_level="AUTOCOMMIT")
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def loaded_sample(test_engine: Engine) -> Engine:
    """Sentetik örnek veriyi (tests/fixtures/olist_sample) yükleme hattıyla test veritabanına yükler."""
    from etl.pipeline import run_pipeline

    run_pipeline(test_engine, SAMPLE_DIR)
    return test_engine


def _temporary_database(test_settings: DatabaseSettings, admin_engine: Engine, prefix: str) -> Iterator[Engine]:
    """Yeni, boş bir test veritabanı (adı _test ile biter); şema uygulanır, sonda silinir."""
    import uuid

    name = f"olist_{prefix}_{uuid.uuid4().hex[:8]}_test"
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_db_engine(replace(test_settings, database=name))
    try:
        apply_sql_files(engine, SQL_DIR)
        yield engine
    finally:
        engine.dispose()
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture(scope="module")
def pipeline_engine(test_settings: DatabaseSettings, admin_engine: Engine) -> Iterator[Engine]:
    """Modül başına yeni, boş bir test veritabanı."""
    yield from _temporary_database(test_settings, admin_engine, "pipeline")


@pytest.fixture
def empty_engine(test_settings: DatabaseSettings, admin_engine: Engine) -> Iterator[Engine]:
    """Test başına yeni, şeması kurulmuş ama hiç veri yüklenmemiş veritabanı."""
    yield from _temporary_database(test_settings, admin_engine, "empty")
