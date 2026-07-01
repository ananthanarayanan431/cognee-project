from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str
    secret_key: str
    openrouter_api_key: str
    fast_model: str = "anthropic/claude-haiku-4-5"
    main_model: str = "anthropic/claude-sonnet-4-6"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    cognee_mode: str = "local"  # "local" (self-hosted via docker-compose) | "cloud"
    cognee_db_host: str = "localhost"
    cognee_db_port: str = "5433"
    cognee_db_name: str = "cognee"
    cognee_db_username: str = "cognee"
    cognee_db_password: str = "cognee"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "debatemind"
    minio_secret_key: str = "debatemind123"
    minio_bucket: str = "debatemind-sources"
    minio_secure: bool = False
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = ["http://localhost:3000"]
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7


settings = Settings()
