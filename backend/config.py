from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "risk-provider-integration"
    app_env: Literal["local", "dev", "staging", "prod"] = "local"
    log_level: str = "INFO"

    api_key: str = Field(min_length=8)
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "risk_platform"
    postgres_user: str = "risk_platform"
    postgres_password: str = "risk_platform"

    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_vhost: str = "/"

    outbox_poll_interval_sec: float = 1.0
    outbox_batch_size: int = 50
    rmq_max_attempts: int = 3

    provider_mock_min_delay_sec: float = 0.05
    provider_mock_max_delay_sec: float = 0.4
    provider_mock_transport_error_rate: float = 0.05
    provider_mock_ack_error_rate: float = 0.05
    provider_mock_accept_probability: float = 0.7
    provider_mock_recommendation_min_delay_sec: float = 0.2
    provider_mock_recommendation_max_delay_sec: float = 3.0
    reconciler_stuck_after_sec: int = 60
    reconciler_poll_interval_sec: float = 15.0
    reconciler_batch_size: int = 100
    ticket_recommendation_timeout_sec: int = 30

    monolith_mock_error_rate: float = 0.05
    monolith_mock_time_multiplier: float = 1

    probes_port: int = 8080
    metrics_enabled: bool = True

    @computed_field
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    @property
    def rabbitmq_url(self) -> str:
        vhost = self.rabbitmq_vhost.lstrip("/")
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/{vhost}"
        )


settings = Settings()
