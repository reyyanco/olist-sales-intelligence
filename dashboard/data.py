"""Dashboard veri katmanı: yalnızca reporting fonksiyon ve view'lerini parametreli sorgularla okur.

- İş mantığı PostgreSQL'dedir (sql/160_report_dashboard_functions.sql); burada yeniden hesaplama yapılmaz.
- Kullanıcı girdileri her zaman bağlama parametresi olarak geçer (SQL metnine eklenmez).
- Önbellek: veri sorguları DATA_TTL_SECONDS, tazelik bilgisi FRESHNESS_TTL_SECONDS. Son başarılı yüklemenin
  run_id'si önbellek anahtarına girer; yeni bir ETL yüklemesinden sonra en geç FRESHNESS_TTL_SECONDS içinde
  yeni veri okunur. "Verileri yenile" düğmesi tüm önbelleği temizler.
- Teknik hata ayrıntıları yalnızca sunucu günlüğüne yazılır; arayüze DataError.user_message gider.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

import pandas as pd
import streamlit as st
from sqlalchemy import Engine, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.types import Date, Text

from etl.db import create_db_engine
from etl.settings import SettingsError, load_settings

DATA_TTL_SECONDS = 600
FRESHNESS_TTL_SECONDS = 60

log = logging.getLogger("dashboard")


class DataError(RuntimeError):
    """Arayüzde gösterilebilir, teknik ayrıntı içermeyen veri hatası."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


@dataclass(frozen=True)
class Filters:
    date_from: dt.date
    date_to: dt.date
    states: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()


@st.cache_resource
def get_engine() -> Engine:
    return create_db_engine(load_settings())


def _query(sql: str, params: dict, array_params: tuple[str, ...] = ()) -> pd.DataFrame:
    stmt = text(sql)
    binds = [bindparam(name, type_=ARRAY(Text)) for name in array_params]
    binds += [bindparam(name, type_=Date) for name, value in params.items() if isinstance(value, dt.date)]
    if binds:
        stmt = stmt.bindparams(*binds)
    try:
        with get_engine().connect() as conn:
            return pd.read_sql(stmt, conn, params=params)
    except SettingsError:
        log.exception("Dashboard ayar hatası")
        raise DataError("Dashboard yapılandırması eksik. Yöneticiye başvurun (.env).")
    except OperationalError:
        log.exception("Veritabanı bağlantı hatası")
        raise DataError("Veritabanına bağlanılamadı. Veritabanının çalıştığından emin olun ve sayfayı yenileyin.")
    except ProgrammingError:
        log.exception("Raporlama nesnesi okunamadı")
        raise DataError("Raporlama nesneleri bulunamadı veya erişim yetkisi yok. Şema güncel olmayabilir "
                        "(.\\scripts\\dashboard.ps1 şemayı ve rolü hazırlar).")
    except SQLAlchemyError:
        log.exception("Beklenmeyen veritabanı hatası")
        raise DataError("Veriler okunurken beklenmeyen bir hata oluştu. Ayrıntı sunucu günlüğündedir.")


def _arr(values: tuple[str, ...]) -> list[str] | None:
    return list(values) if values else None


@st.cache_data(ttl=FRESHNESS_TTL_SECONDS, show_spinner=False)
def freshness() -> dict:
    df = _query("SELECT last_successful_load_at, last_successful_run_id::text AS run_id, last_report_refresh_at "
                "FROM reporting.v_data_freshness", {})
    return df.iloc[0].to_dict()


@st.cache_data(ttl=DATA_TTL_SECONDS, show_spinner=False)
def coverage(run_id: str | None) -> dict:
    df = _query("SELECT first_purchase_date, last_purchase_date, first_month, last_month, order_count "
                "FROM reporting.v_data_coverage", {})
    return df.iloc[0].to_dict()


@st.cache_data(ttl=DATA_TTL_SECONDS, show_spinner=False)
def filter_options(run_id: str | None) -> tuple[list[str], pd.DataFrame]:
    cats = _query("SELECT category_label FROM reporting.v_dashboard_categories ORDER BY category_label", {})
    states = _query("SELECT state, region FROM reporting.v_dashboard_states ORDER BY state", {})
    return cats["category_label"].tolist(), states


@st.cache_data(ttl=DATA_TTL_SECONDS, show_spinner=False)
def overview_kpis(run_id: str | None, f: Filters) -> dict:
    df = _query("SELECT * FROM reporting.fn_overview_kpis(:d_from, :d_to, :states, :categories)",
                {"d_from": f.date_from, "d_to": f.date_to, "states": _arr(f.states), "categories": _arr(f.categories)},
                ("states", "categories"))
    return df.iloc[0].to_dict()


@st.cache_data(ttl=DATA_TTL_SECONDS, show_spinner=False)
def monthly_sales(run_id: str | None, f: Filters) -> pd.DataFrame:
    return _query("SELECT * FROM reporting.fn_monthly_sales(:d_from, :d_to, :states, :categories)",
                  {"d_from": f.date_from, "d_to": f.date_to, "states": _arr(f.states), "categories": _arr(f.categories)},
                  ("states", "categories"))


@st.cache_data(ttl=DATA_TTL_SECONDS, show_spinner=False)
def category_sales(run_id: str | None, f: Filters) -> pd.DataFrame:
    return _query("SELECT * FROM reporting.fn_category_sales(:d_from, :d_to, :states)",
                  {"d_from": f.date_from, "d_to": f.date_to, "states": _arr(f.states)}, ("states",))


@st.cache_data(ttl=DATA_TTL_SECONDS, show_spinner=False)
def delivery_by_region(run_id: str | None, f: Filters) -> pd.DataFrame:
    return _query("SELECT * FROM reporting.fn_delivery_by_region(:d_from, :d_to, :states)",
                  {"d_from": f.date_from, "d_to": f.date_to, "states": _arr(f.states)}, ("states",))


@st.cache_data(ttl=DATA_TTL_SECONDS, show_spinner=False)
def delivery_monthly(run_id: str | None, f: Filters) -> pd.DataFrame:
    return _query("SELECT * FROM reporting.fn_delivery_monthly(:d_from, :d_to, :states)",
                  {"d_from": f.date_from, "d_to": f.date_to, "states": _arr(f.states)}, ("states",))


@st.cache_data(ttl=DATA_TTL_SECONDS, show_spinner=False)
def repeat_purchase(run_id: str | None, f: Filters) -> dict:
    df = _query("SELECT * FROM reporting.fn_repeat_purchase(:d_from, :d_to)", {"d_from": f.date_from, "d_to": f.date_to})
    return df.iloc[0].to_dict()


@st.cache_data(ttl=DATA_TTL_SECONDS, show_spinner=False)
def rfm_segments(run_id: str | None, as_of: dt.date) -> pd.DataFrame:
    return _query("SELECT * FROM reporting.fn_rfm_segments(:as_of)", {"as_of": as_of})


def clear_cache() -> None:
    st.cache_data.clear()
