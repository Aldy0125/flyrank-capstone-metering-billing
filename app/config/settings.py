from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized application configuration.
    Values are loaded from environment variables or .env.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True,
    )

    # Application configuration
    app_name: str = "usage-metering-billing"
    app_env: str = "development"
    log_level: str = "INFO"

    # Database configuration
    database_url: str

    # Stripe configuration
    stripe_secret_key: SecretStr | None = None
    stripe_webhook_secret: SecretStr | None = None
    stripe_pro_price_id: str | None = None

    # Inngest configuration
    inngest_app_id: str = "usage-metering-billing"
    inngest_event_key: SecretStr | None = None
    inngest_signing_key: SecretStr | None = None


# Application-wide settings instance
settings = Settings()
