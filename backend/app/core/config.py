from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Jerry AI Stock Analyst Pro"
    environment: str = "development"

    database_url: str = "postgresql+asyncpg://stock:stock@localhost:5432/stock"
    redis_url: str = "redis://localhost:6379/0"

    cors_origins: list[str] = ["http://localhost:3000"]

    finmind_token: str = ""

    # 共用密鑰保護 API —— 未設定時（本機開發）不擋任何請求，設定後（Cloud Run 正式環境）
    # 所有非 /api/v1/health 的請求都需要帶正確的 X-API-Key header，見 main.py。
    backend_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
