"""Veritabanı bağlantı ayarlarını ortam değişkenlerinden okur."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from sqlalchemy.engine import URL

REQUIRED_VARIABLES = (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
)


class SettingsError(RuntimeError):
    """Zorunlu bir ayar eksik veya geçersiz."""


@dataclass(frozen=True)
class DatabaseSettings:
    host: str
    port: int
    database: str
    user: str
    # Parola repr/log çıktılarında görünmez.
    password: str = field(repr=False)

    def url(self, database: str | None = None) -> URL:
        return URL.create(
            drivername="postgresql+psycopg2",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=database or self.database,
        )


def load_settings(env: Mapping[str, str] | None = None) -> DatabaseSettings:
    env = os.environ if env is None else env
    missing = [name for name in REQUIRED_VARIABLES if not env.get(name)]
    if missing:
        raise SettingsError(f"Eksik ortam değişkenleri: {', '.join(missing)}")
    try:
        port = int(env["POSTGRES_PORT"])
    except ValueError as exc:
        raise SettingsError("POSTGRES_PORT bir tam sayı olmalı") from exc
    return DatabaseSettings(
        host=env["POSTGRES_HOST"],
        port=port,
        database=env["POSTGRES_DB"],
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )
