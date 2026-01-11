from __future__ import annotations

import json
import logging
from typing import Any, Dict

from llm.prompts import build_plan_tx_prompt, build_judge_prompt, build_repair_plan_tx_prompt

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(
        self,
        *,
        model: str | None = None,
        provider: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.0,
        timeout_s: int = 30,
    ) -> None:
        self.model = model
        self.provider = provider
        self.api_key = api_key
        self.temperature = temperature
        self.timeout_s = timeout_s

    def plan_tx(self, *, planner_input: dict) -> dict:
        prompt = build_plan_tx_prompt(planner_input)
        raw_text = self._call_provider(prompt=prompt)
        return self._parse_json(raw_text)

    def judge(self, *, judge_input: dict) -> dict:
        prompt = build_judge_prompt(judge_input)
        raw_text = self._call_provider(prompt=prompt)
        return self._parse_json(raw_text)

    def repair_plan_tx(self, *, repair_input: dict) -> dict:
        prompt = build_repair_plan_tx_prompt(repair_input)
        raw_text = self._call_provider(prompt=prompt)
        return self._parse_json(raw_text)

    def _call_provider(self, *, prompt: dict) -> str:
        if self.provider == "openai":
            return self._call_openai(prompt=prompt)
        raise RuntimeError("LLM provider not configured")

    def _call_openai(self, *, prompt: dict) -> str:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            from langchain_openai import ChatOpenAI
        except Exception as e:
            raise RuntimeError(f"LangChain OpenAI client not available: {e}") from e

        messages = [
            SystemMessage(content=prompt["system"]),
            HumanMessage(content=prompt["user"]),
        ]

        def run_call(*, with_response_format: bool) -> str:
            logger.info(
                "LLM call start provider=openai model=%s response_format=%s",
                self.model or "gpt-4o-mini",
                with_response_format,
            )
            model_kwargs = {"response_format": {"type": "json_object"}} if with_response_format else None
            llm = ChatOpenAI(
                model=self.model or "gpt-4o-mini",
                temperature=self.temperature,
                timeout=self.timeout_s,
                api_key=self.api_key,
                model_kwargs=model_kwargs,
            )
            response = llm.invoke(messages)
            output_text = response.content
            if not output_text:
                raise RuntimeError("OpenAI returned empty content")
            if not isinstance(output_text, str):
                output_text = json.dumps(output_text)
            logger.info("LLM call success provider=openai output_len=%s", len(output_text))
            return output_text

        try:
            return run_call(with_response_format=True)
        except Exception as e:
            logger.warning("LLM call failed with response_format: %s", e)
            return run_call(with_response_format=False)

    def _parse_json(self, text: str) -> Dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("LLM returned empty response")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start : end + 1])
            raise
