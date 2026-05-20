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
        return []
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


def is_dev_auth_bypass_enabled() -> bool:
    """Local-only fake login when Microsoft Entra is not configured. Never active in production."""
    if is_production():
        return False
    flag = os.getenv("DEV_AUTH_BYPASS", "").strip().lower()
    return flag in ("1", "true", "yes", "on")


def get_dev_auth_email() -> str:
    raw = os.getenv("DEV_AUTH_EMAIL", "dev@localhost")
    email = (raw or "dev@localhost").strip()
    return email or "dev@localhost"


DEV_AUTH_AZURE_OID = "local-dev-bypass"


def get_allowed_email_domain() -> Optional[str]:
    raw = os.getenv("ALLOWED_EMAIL_DOMAIN")
    return raw.strip().lower() if raw else None


def get_inventory_mode() -> str:
    """
    Inventory source when the ``cars`` table is empty.

    - ``auto`` (default): eBay if configured, else in-memory demo when allowed
    - ``ebay_only``: never show in-memory demo (empty list if eBay fails)
    - ``demo_only``: always in-memory demo (ignore eBay)
    """
    return os.getenv("INVENTORY_MODE", "auto").strip().lower()


def in_memory_demo_enabled() -> bool:
    """Whether the generated demo catalog may be used for listing or filter UI."""
    mode = get_inventory_mode()
    if mode in ("ebay_only", "ebay"):
        return False
    if mode in ("demo_only", "demo"):
        return True
    raw = os.getenv("DEMO_IN_MEMORY_WHEN_EMPTY", "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def require_auth_env_at_startup() -> None:
    """Fail fast in production if SSO secrets are missing."""
    if is_production() and is_dev_auth_bypass_enabled():
        raise RuntimeError("DEV_AUTH_BYPASS must not be enabled when APP_ENV is production.")
    if not is_production():
        return
    missing = []
    for name, val in (
        ("AZURE_AD_TENANT_ID", get_azure_ad_tenant_id()),
        ("AZURE_AD_CLIENT_ID", get_azure_ad_client_id()),
        ("AZURE_AD_CLIENT_SECRET", get_azure_ad_client_secret()),
        ("AZURE_AD_REDIRECT_URI", get_azure_ad_redirect_uri()),
        ("AUTH_SESSION_SECRET", get_auth_session_secret()),
        ("CORS_ORIGINS", os.getenv("CORS_ORIGINS", "").strip()),
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

    raise RuntimeError("Missing database configuration. Provide DATABASE_URL or DB_* variables.")
