"""SQL uygulayıcısı testleri. Sentetik SQL dosyaları geçici klasörde üretilir;
veritabanı testleri test veritabanında ayrı bir izleme şeması kullanır."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from etl.sql_runner import SqlRunnerError, apply_sql_files, discover_sql_files


def write(directory, name, body="SELECT 1;"):
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def test_discover_orders_by_numeric_version(tmp_path):
    write(tmp_path, "020_second.sql")
    write(tmp_path, "010_first.sql")
    write(tmp_path, "100_third.sql")
    assert [f.name for f in discover_sql_files(tmp_path)] == [
        "010_first.sql",
        "020_second.sql",
        "100_third.sql",
    ]


def test_discover_ignores_subdirectories(tmp_path):
    write(tmp_path, "010_first.sql")
    (tmp_path / "queries").mkdir()
    write(tmp_path / "queries", "revenue.sql")
    assert [f.name for f in discover_sql_files(tmp_path)] == ["010_first.sql"]


@pytest.mark.parametrize("bad_name", ["10_short.sql", "010-dash.sql", "010_Upper.sql", "create.sql"])
def test_discover_rejects_invalid_names(tmp_path, bad_name):
    write(tmp_path, bad_name)
    with pytest.raises(SqlRunnerError, match="Geçersiz SQL dosya adı"):
        discover_sql_files(tmp_path)


def test_discover_rejects_duplicate_versions(tmp_path):
    write(tmp_path, "010_a.sql")
    write(tmp_path, "010_b.sql")
    with pytest.raises(SqlRunnerError, match="Aynı sürüm numarası"):
        discover_sql_files(tmp_path)


def test_project_sql_files_are_valid():
    from tests.conftest import SQL_DIR

    files = discover_sql_files(SQL_DIR)
    assert files, "sql/ altında en az bir numaralı dosya olmalı"


@pytest.fixture
def isolated_schemas(test_engine):
    """Her test için benzersiz izleme ve hedef şeması; test sonunda silinir."""
    suffix = uuid.uuid4().hex[:8]
    tracking, target = f"test_runner_meta_{suffix}", f"test_runner_target_{suffix}"
    yield tracking, target
    with test_engine.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {tracking} CASCADE"))
        conn.execute(text(f"DROP SCHEMA IF EXISTS {target} CASCADE"))


def test_apply_runs_each_file_once(tmp_path, test_engine, isolated_schemas):
    tracking, target = isolated_schemas
    write(tmp_path, "010_schema.sql", f"CREATE SCHEMA {target};")
    write(
        tmp_path,
        "020_table.sql",
        # % karakteri parametre olarak yorumlanmamalı.
        f"CREATE TABLE {target}.t (label text); INSERT INTO {target}.t VALUES ('100% ok');",
    )

    first = apply_sql_files(test_engine, tmp_path, tracking_schema=tracking)
    second = apply_sql_files(test_engine, tmp_path, tracking_schema=tracking)

    assert [f.name for f in first] == ["010_schema.sql", "020_table.sql"]
    assert second == []
    with test_engine.connect() as conn:
        assert conn.execute(text(f"SELECT label FROM {target}.t")).scalar_one() == "100% ok"
        assert conn.execute(text(f"SELECT count(*) FROM {tracking}.schema_migrations")).scalar_one() == 2


def test_apply_detects_changed_file(tmp_path, test_engine, isolated_schemas):
    tracking, target = isolated_schemas
    path = write(tmp_path, "010_schema.sql", f"CREATE SCHEMA {target};")
    apply_sql_files(test_engine, tmp_path, tracking_schema=tracking)

    path.write_text(f"CREATE SCHEMA IF NOT EXISTS {target};", encoding="utf-8")
    with pytest.raises(SqlRunnerError, match="içeriği değişmiş"):
        apply_sql_files(test_engine, tmp_path, tracking_schema=tracking)


def test_failed_file_is_rolled_back_and_not_recorded(tmp_path, test_engine, isolated_schemas):
    tracking, target = isolated_schemas
    write(tmp_path, "010_schema.sql", f"CREATE SCHEMA {target};")
    write(tmp_path, "020_broken.sql", f"CREATE TABLE {target}.ok (id int); SELECT * FROM missing_table;")

    with pytest.raises(Exception):
        apply_sql_files(test_engine, tmp_path, tracking_schema=tracking)

    with test_engine.connect() as conn:
        recorded = conn.execute(text(f"SELECT filename FROM {tracking}.schema_migrations")).scalars().all()
        ok_table = conn.execute(text("SELECT to_regclass(:name)"), {"name": f"{target}.ok"}).scalar()
    assert recorded == ["010_schema.sql"]
    assert ok_table is None
