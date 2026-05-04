import os


def get_app_env() -> str:
    return os.getenv("APP_ENV", "development").lower()


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
