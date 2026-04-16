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
    cors_origin_regex: str | None = r"http://192\.168\.\d+\.\d+:3000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
