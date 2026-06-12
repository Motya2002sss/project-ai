from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Life Planner"
    app_env: str = "local"
    app_debug: bool = True

    database_url: str = "postgresql+psycopg://ai_life_planner:ai_life_planner_password@localhost:5432/ai_life_planner"

    telegram_bot_token: str | None = None

    llm_provider: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
