import pytest

from etl.settings import SettingsError, load_settings

VALID_ENV = {
    "POSTGRES_HOST": "db",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "example_db",
    "POSTGRES_USER": "example_user",
    "POSTGRES_PASSWORD": "example-secret-value",
}


def test_load_settings_reads_all_values():
    settings = load_settings(VALID_ENV)
    assert (settings.host, settings.port, settings.database, settings.user) == (
        "db",
        5432,
        "example_db",
        "example_user",
    )


def test_password_hidden_from_repr_and_url_string():
    settings = load_settings(VALID_ENV)
    assert "example-secret-value" not in repr(settings)
    assert "example-secret-value" not in str(settings.url())


def test_missing_variables_are_listed_without_values():
    env = {k: v for k, v in VALID_ENV.items() if k not in {"POSTGRES_PASSWORD", "POSTGRES_DB"}}
    with pytest.raises(SettingsError) as excinfo:
        load_settings(env)
    assert "POSTGRES_PASSWORD" in str(excinfo.value)
    assert "POSTGRES_DB" in str(excinfo.value)


def test_non_numeric_port_rejected():
    with pytest.raises(SettingsError):
        load_settings({**VALID_ENV, "POSTGRES_PORT": "abc"})
