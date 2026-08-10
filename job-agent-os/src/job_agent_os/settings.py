"""Global configuration using pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Application configuration."""

    app_name: str = "Job Agent OS"
    env: Literal["dev", "test", "prod"] = "dev"
    debug: bool = True
    version: str = "0.1.0"


class DatabaseConfig(BaseSettings):
    """Database configuration."""

    url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/job_agent_os"
    pool_size: int = 10
    max_overflow: int = 20
    echo: bool = False


class RedisConfig(BaseSettings):
    """Redis configuration."""

    url: str = "redis://localhost:6379/0"
    max_connections: int = 20


class JWTConfig(BaseSettings):
    """JWT authentication configuration."""

    secret_key: SecretStr = SecretStr("your-super-secret-key-change-in-production")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7


class LLMConfig(BaseSettings):
    """LLM (Large Language Model) configuration."""

    provider: str = "openai"
    model: str = "deepseek-chat"
    model_fallback: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com"
    api_key: SecretStr = SecretStr("sk-your-deepseek-api-key")
    temperature: float = 0.1
    max_tokens: int = 4096
    timeout: int = 60


class LangfuseConfig(BaseSettings):
    """Langfuse observability configuration."""

    public_key: SecretStr = SecretStr("")
    secret_key: SecretStr = SecretStr("")
    base_url: str = "https://cloud.langfuse.com"
    enabled: bool = False


class HarnessConfig(BaseSettings):
    """Harness Runtime configuration."""

    max_steps: int = 50
    token_budget_per_session: int = 100000
    tool_timeout_seconds: int = 30
    max_retries: int = 3
    loop_detection_threshold: int = 3


class Settings(BaseSettings):
    """Main settings class aggregating all configurations."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "Job Agent OS"
    env: Literal["dev", "test", "prod"] = "dev"
    debug: bool = True
    version: str = "0.1.0"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/job_agent_os"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 20

    # JWT
    jwt_secret_key: SecretStr = SecretStr("your-super-secret-key-change-in-production")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # LLM (DeepSeek / OpenAI compatible)
    openai_api_key: SecretStr = SecretStr("sk-your-deepseek-api-key")
    openai_base_url: str = "https://api.deepseek.com"
    openai_model: str = "deepseek-chat"
    openai_model_fallback: str = "deepseek-chat"
    openai_temperature: float = 0.1
    openai_max_tokens: int = 4096
    openai_timeout: int = 60

    # Embedding (Alibaba DashScope / OpenAI compatible)
    embedding_api_key: SecretStr = SecretStr("")
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_model: str = "text-embedding-v3"
    embedding_dimension: int = 1024

    # Langfuse
    langfuse_public_key: SecretStr = SecretStr("")
    langfuse_secret_key: SecretStr = SecretStr("")
    langfuse_base_url: str = "https://cloud.langfuse.com"
    langfuse_enabled: bool = False

    # Harness
    harness_max_steps: int = 50
    harness_token_budget_per_session: int = 100000
    harness_tool_timeout_seconds: int = 30
    harness_max_retries: int = 3
    harness_loop_detection_threshold: int = 3

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        """Validate security settings in production."""
        if self.env == "prod" and (
            self.jwt_secret_key.get_secret_value()
            == "your-super-secret-key-change-in-production"
        ):
            raise ValueError(
                "jwt_secret_key must be changed from default value in production"
            )
        return self

    @property
    def app(self) -> AppConfig:
        """Get app configuration."""
        return AppConfig(
            app_name=self.app_name,
            env=self.env,
            debug=self.debug,
            version=self.version,
        )

    @property
    def database(self) -> DatabaseConfig:
        """Get database configuration."""
        return DatabaseConfig(
            url=self.database_url,
            pool_size=self.db_pool_size,
            max_overflow=self.db_max_overflow,
            echo=self.db_echo,
        )

    @property
    def redis(self) -> RedisConfig:
        """Get Redis configuration."""
        return RedisConfig(
            url=self.redis_url,
            max_connections=self.redis_max_connections,
        )

    @property
    def jwt(self) -> JWTConfig:
        """Get JWT configuration."""
        return JWTConfig(
            secret_key=self.jwt_secret_key,
            algorithm=self.jwt_algorithm,
            access_token_expire_minutes=self.jwt_access_token_expire_minutes,
            refresh_token_expire_days=self.jwt_refresh_token_expire_days,
        )

    @property
    def llm(self) -> LLMConfig:
        """Get LLM configuration."""
        return LLMConfig(
            model=self.openai_model,
            model_fallback=self.openai_model_fallback,
            base_url=self.openai_base_url,
            api_key=self.openai_api_key,
            temperature=self.openai_temperature,
            max_tokens=self.openai_max_tokens,
            timeout=self.openai_timeout,
        )

    @property
    def langfuse(self) -> LangfuseConfig:
        """Get Langfuse configuration."""
        return LangfuseConfig(
            public_key=self.langfuse_public_key,
            secret_key=self.langfuse_secret_key,
            base_url=self.langfuse_base_url,
            enabled=self.langfuse_enabled,
        )

    @property
    def harness(self) -> HarnessConfig:
        """Get Harness configuration."""
        return HarnessConfig(
            max_steps=self.harness_max_steps,
            token_budget_per_session=self.harness_token_budget_per_session,
            tool_timeout_seconds=self.harness_tool_timeout_seconds,
            max_retries=self.harness_max_retries,
            loop_detection_threshold=self.harness_loop_detection_threshold,
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Note: The result is cached by lru_cache. To force a refresh
    (e.g. after changing environment variables in tests), call
    get_settings.cache_clear() first.
    """
    return Settings()
