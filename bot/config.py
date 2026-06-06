from pydantic import field_validator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_VALID_ENVS = {"test", "prod"}


class Settings(BaseSettings):
    telegram_bot_token: str
    elevenlabs_api_key: str = ""
    tempolor_api_key: str = ""
    openai_api_key: str = ""
    typecast_api_key: str = ""
    azure_speech_key: str = ""
    azure_speech_endpoint: str = ""
    google_application_credentials: str = ""
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    bot_env: str = "prod"
    pricing_config_path: str = Field(default="", description="Override path to pricing.json. Default: config/pricing.json (or config/pricing.test.json under BOT_ENV=test).")

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
