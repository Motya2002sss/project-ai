import pytest

from app.core.config import Settings
from app.core.runtime import RuntimeConfigError, validate_runtime_config
from app.main import create_app


def production_settings(**overrides) -> Settings:
    values = {
        "app_env": "production",
        "app_debug": False,
        "allow_dogfood_auth": False,
        "mobile_dogfood_token": None,
        "database_url": "postgresql+psycopg://service:secret@db.internal/life_planner",
        "public_api_url": "https://api.example.com",
        "apple_client_id": "com.example.lifeplanner",
        "privacy_policy_url": "https://example.com/privacy",
        "terms_url": "https://example.com/terms",
        "support_url": "https://example.com/support",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_rejects_debug_and_dogfood_auth() -> None:
    configured = production_settings(
        app_debug=True,
        allow_dogfood_auth=True,
        mobile_dogfood_token="local-secret",
    )

    with pytest.raises(RuntimeConfigError) as error:
        validate_runtime_config(configured)

    assert error.value.reasons == (
        "app_debug_must_be_false",
        "dogfood_auth_must_be_disabled",
    )


def test_production_accepts_explicit_external_configuration() -> None:
    validate_runtime_config(production_settings())


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_deployed_environment_rejects_local_database_and_api(app_env: str) -> None:
    configured = production_settings(
        app_env=app_env,
        database_url="postgresql+psycopg://local:local@localhost/life_planner",
        public_api_url="http://127.0.0.1:8000",
    )

    with pytest.raises(RuntimeConfigError) as error:
        validate_runtime_config(configured)

    assert error.value.reasons == (
        "database_must_be_external",
        "public_api_url_must_be_https",
    )


def test_local_environment_keeps_safe_development_defaults() -> None:
    validate_runtime_config(Settings(_env_file=None))


def test_application_factory_enforces_runtime_validation(monkeypatch) -> None:
    monkeypatch.setattr("app.main.settings.app_env", "production")
    monkeypatch.setattr("app.main.settings.app_debug", True)
    monkeypatch.setattr("app.main.settings.allow_dogfood_auth", True)

    with pytest.raises(RuntimeConfigError):
        create_app()
