"""SQLAlchemy engine oluşturma ve temel sunucu sorguları."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection, Engine, create_engine, text

from etl.settings import DatabaseSettings


@dataclass(frozen=True)
class ServerInfo:
    server_version: str
    server_version_num: int
    database: str
    user: str


def create_db_engine(settings: DatabaseSettings, database: str | None = None) -> Engine:
    return create_engine(
        settings.url(database),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10, "application_name": "olist-sales-intelligence"},
    )


def execute_script(conn: Connection, sql_text: str) -> None:
    """Çok ifadeli SQL metnini bağlantının mevcut işleminde, parametresiz çalıştırır.

    exec_driver_sql boş parametre sözlüğü geçirir ve psycopg2 bu durumda SQL içindeki
    % karakterlerini biçim işareti sayar. Ham imleçte parametre verilmediğinde SQL
    olduğu gibi gönderilir.
    """
    cursor = conn.connection.cursor()
    try:
        cursor.execute(sql_text)
    finally:
        cursor.close()


def fetch_server_info(engine: Engine) -> ServerInfo:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT current_setting('server_version') AS server_version, "
                "current_setting('server_version_num')::int AS server_version_num, "
                "current_database() AS database, current_user AS user"
            )
        ).one()
    return ServerInfo(
        server_version=row.server_version,
        server_version_num=row.server_version_num,
        database=row.database,
        user=row.user,
    )
