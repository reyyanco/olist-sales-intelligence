from sqlalchemy import text

from etl.db import fetch_server_info


def test_select_returns_value(test_engine):
    with test_engine.connect() as conn:
        assert conn.execute(text("SELECT 1 + 1")).scalar_one() == 2


def test_connected_to_postgres_16_test_database(test_engine, test_settings):
    info = fetch_server_info(test_engine)
    assert 160000 <= info.server_version_num < 170000
    assert info.database == test_settings.database
    assert info.database.endswith("_test")


def test_warehouse_schemas_exist(test_engine):
    with test_engine.connect() as conn:
        schemas = set(
            conn.execute(
                text("SELECT schema_name FROM information_schema.schemata WHERE schema_name IN ('meta', 'staging', 'dw')")
            ).scalars()
        )
    assert schemas == {"meta", "staging", "dw"}
