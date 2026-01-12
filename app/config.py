from functools import lru_cache
import json
from typing import Any, Set
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # required config for MVP
    database_url: str = ""
    web3_service_url: str = ""
    llm_model: str = "gpt-4o-mini"  # safe default- override via env
    llm_enabled: bool = False
    llm_provider: str = "openai"
    openai_api_key: str | None = None
    llm_temperature: float = 0.0
    llm_chat_temperature: float = 0.5
    llm_chat_responses: bool = True
    llm_timeout_s: int = 30
    rpc_urls: str = "" 
    allowlist_to: str = Field(default="[]", alias="ALLOWLIST_TO")
    allowlisted_tokens: dict[str, dict[str, dict[str, Any]]] = Field(
        default_factory=lambda: {
            "1": {
                "USDC": {
                    "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                    "decimals": 6,
                },
                "WETH": {
                    "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                    "decimals": 18,
                },
                "ETH": {
                    "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                    "decimals": 18,
                    "is_native": True,
                },
            }
        },
        alias="ALLOWLISTED_TOKENS",
    )
    allowlisted_routers: dict[str, dict[str, Any]] = Field(
        default_factory=lambda: {
            "1": {
                "UNISWAP_V2_ROUTER": {
                    "address": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
                }
            }
        },
        alias="ALLOWLISTED_ROUTERS",
    )
    dex_kind: str = Field(default="uniswap_v2", alias="DEX_KIND")
    default_slippage_bps: int = Field(default=50, alias="DEFAULT_SLIPPAGE_BPS")
    default_deadline_seconds: int = Field(default=1200, alias="DEFAULT_DEADLINE_SECONDS")
    min_slippage_bps: int = Field(default=10, alias="MIN_SLIPPAGE_BPS")
    max_slippage_bps: int = Field(default=200, alias="MAX_SLIPPAGE_BPS")
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
    def allowlisted_to_set(self) -> Set[str]:
        try:
            data = json.loads(self.allowlist_to or "[]")
            if not isinstance(data, list):
                return set()
            return {str(x).lower() for x in data}
        except Exception:
            # If env is invalid, fail closed? For MVP I recommend "safe default": empty set.
            # (Empty allowlist will only matter once you have non-noop txs.)
            return set()


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
    def LLM_ENABLED(self) -> bool:
        return self.llm_enabled

    @property
    def LLM_PROVIDER(self) -> str:
        return self.llm_provider

    @property
    def OPENAI_API_KEY(self) -> str | None:
        return self.openai_api_key

    @property
    def LLM_TEMPERATURE(self) -> float:
        return self.llm_temperature

    @property
    def LLM_CHAT_TEMPERATURE(self) -> float:
        return self.llm_chat_temperature

    @property
    def LLM_CHAT_RESPONSES(self) -> bool:
        return self.llm_chat_responses

    @property
    def LLM_TIMEOUT_S(self) -> int:
        return self.llm_timeout_s
    @property
    def RPC_URLS(self) -> str:
        return self.rpc_urls

    def allowlisted_tokens_for_chain(self, chain_id: int | None) -> dict[str, dict[str, Any]]:
        if chain_id is None:
            return {}
        data = self.allowlisted_tokens or {}
        return data.get(str(chain_id)) or data.get(chain_id) or {}

    def allowlisted_routers_for_chain(self, chain_id: int | None) -> dict[str, Any]:
        if chain_id is None:
            return {}
        data = self.allowlisted_routers or {}
        return data.get(str(chain_id)) or data.get(chain_id) or {}



@lru_cache
def get_settings() -> Settings:
    """
    Cached settings loader (process-level).
    """
    return Settings()
