from __future__ import annotations

import json
from typing import Dict

from app.config import get_settings


class UnsupportedChainError(ValueError):
    pass


def _load_rpc_urls() -> Dict[int, str]:
    """
    Load RPC URLs from settings.

    Expected env format (recommended):
      RPC_URLS='{"1":"https://eth.llamarpc.com","137":"https://polygon.llamarpc.com"}'
    """
    settings = get_settings()

    raw = getattr(settings, "RPC_URLS", None)
    if not raw:
        return {}

    try:
        data = json.loads(raw)
    except Exception as e:
        raise ValueError("RPC_URLS must be valid JSON") from e

    # normalize keys to int
    rpc_urls: Dict[int, str] = {}
    for k, v in data.items():
        try:
            chain_id = int(k)
        except ValueError:
            raise ValueError(f"Invalid chain_id key in RPC_URLS: {k}")

        if not isinstance(v, str) or not v:
            raise ValueError(f"Invalid RPC URL for chain {chain_id}")

        rpc_urls[chain_id] = v.rstrip("/")

    return rpc_urls


_RPC_URLS: Dict[int, str] | None = None


def get_rpc_url(chain_id: int) -> str:
    """
    Return RPC URL for a given chain_id.
    Raises UnsupportedChainError if not configured.
    """
    global _RPC_URLS

    if _RPC_URLS is None:
        _RPC_URLS = _load_rpc_urls()

    rpc_url = _RPC_URLS.get(chain_id)
    if not rpc_url:
        raise UnsupportedChainError(f"Unsupported chain_id: {chain_id}")

    return rpc_url


def list_supported_chains() -> list[int]:
    """
    List configured chain IDs.
    """
    global _RPC_URLS

    if _RPC_URLS is None:
        _RPC_URLS = _load_rpc_urls()

    return sorted(_RPC_URLS.keys())
