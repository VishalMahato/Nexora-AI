from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # required config for MVP
    database_url: str = ""
    web3_service_url: str = ""
    llm_model: str = "gpt-4o-mini"  # safe default- override via env

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",   # ✅ ignore APP_ENV, LOG_LEVEL, etc
    )


    @property
    def DATABASE_URL(self) -> str:
        return self.database_url

    @property
    def WEB3_SERVICE_URL(self) -> str:
        return self.web3_service_url

    @property
    def LLM_MODEL(self) -> str:
        return self.llm_model


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings loader (process-level).
    """
    return Settings()
