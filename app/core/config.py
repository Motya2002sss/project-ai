from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Life Planner"
    app_env: str = "local"
    app_debug: bool = True

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "ai_life_planner"
    postgres_user: str = "ai_life_planner"
    postgres_password: str = "ai_life_planner_password"

    database_url: str = (
        "postgresql+psycopg://ai_life_planner:"
        "ai_life_planner_password@localhost:5432/ai_life_planner"
    )

    telegram_bot_token: str | None = None

    plan_start_buffer_minutes: int = 30
    default_plan_start_time: str = "18:30"

    llm_enabled: bool = False
    llm_provider: str = "mock"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = 15.0
    llm_max_input_chars: int = 4000
    llm_max_output_tokens: int = 800

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
