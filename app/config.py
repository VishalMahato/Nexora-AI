from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # required config for MVP
    database_url: str = ""
    web3_service_url: str = ""
    llm_model: str = "gpt-4o-mini"  # safe default- override via env
    rpc_urls: str = "" 
    # --- observability ---
    log_level: str = "INFO"
    log_json: bool = False

    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "nexora-ai"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

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
    @property
    def RPC_URLS(self) -> str:
        return self.rpc_urls



@lru_cache
def get_settings() -> Settings:
    """
    Cached settings loader (process-level).
    """
    return Settings()
