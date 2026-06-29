from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str
    secret_key: str
    openrouter_api_key: str
    fast_model: str = "anthropic/claude-haiku-4-5"
    main_model: str = "anthropic/claude-sonnet-4-6"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    cognee_api_key: str = ""
    cognee_llm_api_key: str = ""
    cors_origins: list[str] = ["http://localhost:3000"]
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7


settings = Settings()
