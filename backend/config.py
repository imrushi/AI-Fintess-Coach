from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent / ".env",
        env_file_encoding="utf-8",
    )

    GARMIN_EMAIL: str
    GARMIN_PASSWORD: str
    DATABASE_URL: str = "sqlite:///./db/fitness.db"


settings = Settings()
