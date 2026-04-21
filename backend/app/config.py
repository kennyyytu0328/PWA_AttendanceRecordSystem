from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/attendance"
    test_database_url: str = "sqlite+aiosqlite://"

    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "GoGoFresh Attendance"
    webauthn_origin: str = "http://localhost:3000"

    cors_origins: list[str] = ["http://localhost:3000"]
    # Default None for production safety. Set CORS_ORIGIN_REGEX in .env for LAN dev access.
    cors_origin_regex: str | None = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
