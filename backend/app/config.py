import os
from typing import Optional


def get_app_env() -> str:
    return os.getenv("APP_ENV", "development").lower()


def is_production() -> bool:
    return get_app_env() in ("production", "prod")


def get_cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS")
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    if is_production():
        return ["https://css360.qeax.cloud"]
    return [
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]


def get_azure_ad_tenant_id() -> Optional[str]:
    return os.getenv("AZURE_AD_TENANT_ID")


def get_azure_ad_client_id() -> Optional[str]:
    return os.getenv("AZURE_AD_CLIENT_ID")


def get_azure_ad_client_secret() -> Optional[str]:
    return os.getenv("AZURE_AD_CLIENT_SECRET")


def get_azure_ad_redirect_uri() -> Optional[str]:
    return os.getenv("AZURE_AD_REDIRECT_URI")


def get_auth_session_secret() -> Optional[str]:
    return os.getenv("AUTH_SESSION_SECRET")


def get_allowed_email_domain() -> Optional[str]:
    raw = os.getenv("ALLOWED_EMAIL_DOMAIN")
    return raw.strip().lower() if raw else None


def require_auth_env_at_startup() -> None:
    """Fail fast in production if SSO secrets are missing."""
    if not is_production():
        return
    missing = []
    for name, val in (
        ("AZURE_AD_TENANT_ID", get_azure_ad_tenant_id()),
        ("AZURE_AD_CLIENT_ID", get_azure_ad_client_id()),
        ("AZURE_AD_CLIENT_SECRET", get_azure_ad_client_secret()),
        ("AZURE_AD_REDIRECT_URI", get_azure_ad_redirect_uri()),
        ("AUTH_SESSION_SECRET", get_auth_session_secret()),
    ):
        if not val:
            missing.append(name)
    if missing:
        raise RuntimeError(
            "Missing required authentication environment variables in production: "
            + ", ".join(missing)
        )


def build_database_url() -> str:
    explicit_url = os.getenv("DATABASE_URL")
    if explicit_url:
        return explicit_url

    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT", "3306")
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")

    has_discrete_db_config = all([db_host, db_name, db_user, db_password])
    if has_discrete_db_config:
        return f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    app_env = get_app_env()
    if app_env in ("development", "dev", "local"):
        return "sqlite:///./cars_dev.db"

    raise RuntimeError(
        "Missing database configuration. Provide DATABASE_URL or DB_* variables."
    )
