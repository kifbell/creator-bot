from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_VALID_ENVS = {"test", "prod"}


class Settings(BaseSettings):
    telegram_bot_token: str
    elevenlabs_api_key: str = ""
    tempolor_api_key: str = ""
    bot_env: str = "prod"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("bot_env")
    @classmethod
    def validate_bot_env(cls, v: str) -> str:
        if v not in _VALID_ENVS:
            raise ValueError(
                f"BOT_ENV must be 'test' or 'prod', got '{v}'. "
                "Set BOT_ENV in your .env file or environment."
            )
        return v


settings = Settings()
