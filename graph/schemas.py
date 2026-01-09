from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from web3 import Web3


def _validate_address(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("address must be a string")
    if not value.startswith("0x") or len(value) != 42:
        raise ValueError("invalid address format")
    if not Web3.is_address(value):
        raise ValueError("invalid address")
    return Web3.to_checksum_address(value)


class TxAction(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    action: Literal["APPROVE", "SWAP", "TRANSFER", "REVOKE"]
    token: str | None = None
    spender: str | None = None
    amount: str | None = None
    to: str | None = None
    chain_id: int | None = None
    meta: dict[str, Any] | None = None

    @field_validator("token")
    @classmethod
    def _validate_token(cls, value: str | None) -> str | None:
        return _validate_address(value)

    @field_validator("spender")
    @classmethod
    def _validate_spender(cls, value: str | None) -> str | None:
        return _validate_address(value)

    @field_validator("to")
    @classmethod
    def _validate_to(cls, value: str | None) -> str | None:
        return _validate_address(value)


class TxPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    plan_version: int = 1
    type: Literal["noop", "plan"]
    reason: str | None = None
    normalized_intent: str | None = None
    actions: list[TxAction] = Field(default_factory=list)
    candidates: list["TxCandidate"] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_plan(self) -> "TxPlan":
        if self.type == "noop" and (self.actions or self.candidates):
            raise ValueError("noop plan must not include actions")
        if self.type == "plan" and not (self.actions or self.candidates):
            raise ValueError("plan must include at least one action or candidate")
        return self


class TxCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    chain_id: int
    to: str
    data: str = "0x"
    value_wei: str = Field(alias="valueWei")
    meta: dict[str, Any] | None = None

    @field_validator("to")
    @classmethod
    def _validate_to(cls, value: str) -> str:
        checked = _validate_address(value)
        if checked is None:
            raise ValueError("to address is required")
        return checked

    @field_validator("data")
    @classmethod
    def _validate_data(cls, value: str) -> str:
        if not isinstance(value, str) or not value.startswith("0x"):
            raise ValueError("data must be hex string starting with 0x")
        return value

    @field_validator("value_wei")
    @classmethod
    def _validate_value_wei(cls, value: str) -> str:
        if not isinstance(value, str) or not value.isdigit():
            raise ValueError("value_wei must be a numeric string")
        return value
