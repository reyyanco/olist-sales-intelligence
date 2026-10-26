"""Dashboard giriş rolünü .env değerleriyle oluşturur veya günceller.

Rol yalnızca olist_reporting_reader üyesidir (sql/180_dashboard_reader_role.sql): reporting okuma nesneleri
ve dashboard fonksiyonları. Oturumlar varsayılan olarak salt okunur ve sorgu başına zaman sınırlıdır.
Parola SQL'e psycopg2.sql.Literal ile alıntılanarak geçer; hiçbir çıktıya yazılmaz.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping

from psycopg2 import sql
from sqlalchemy import Engine

from etl.settings import SettingsError

READER_ROLE = "olist_reporting_reader"
ROLE_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
STATEMENT_TIMEOUT = "30s"


def dashboard_credentials(env: Mapping[str, str] | None = None) -> tuple[str, str]:
    env = os.environ if env is None else env
    user, password = env.get("DASHBOARD_DB_USER", ""), env.get("DASHBOARD_DB_PASSWORD", "")
    missing = [n for n, v in (("DASHBOARD_DB_USER", user), ("DASHBOARD_DB_PASSWORD", password)) if not v]
    if missing:
        raise SettingsError(f"Eksik ortam değişkenleri: {', '.join(missing)} (.\\scripts\\new-env.ps1 ekler)")
    if not ROLE_NAME_RE.match(user):
        raise SettingsError("DASHBOARD_DB_USER küçük harf, rakam ve alt çizgiden oluşmalı")
    if user == env.get("POSTGRES_USER"):
        raise SettingsError("DASHBOARD_DB_USER yönetici kullanıcıyla aynı olamaz")
    return user, password


def ensure_dashboard_role(engine: Engine, user: str, password: str) -> bool:
    """Rolü oluşturur (True) veya parolasını ve ayarlarını eşitler (False)."""
    with engine.begin() as conn:
        cur = conn.connection.cursor()
        try:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (READER_ROLE,))
            if cur.fetchone() is None:
                raise SettingsError(f"{READER_ROLE} rolü yok; önce 'migrate' çalıştırın")
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (user,))
            created = cur.fetchone() is None
            ident = sql.Identifier(user)
            verb = sql.SQL("CREATE ROLE") if created else sql.SQL("ALTER ROLE")
            cur.execute(sql.SQL("{} {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT PASSWORD {}").format(
                verb, ident, sql.Literal(password)))
            cur.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(READER_ROLE), ident))
            cur.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(ident))
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = {}").format(ident, sql.Literal(STATEMENT_TIMEOUT)))
        finally:
            cur.close()
    return created
