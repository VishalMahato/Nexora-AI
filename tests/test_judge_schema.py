from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.judge_result import JudgeIssue, JudgeIssueSeverity, JudgeOutput, JudgeVerdict


def test_judge_output_schema_validates():
    output = JudgeOutput(
        verdict=JudgeVerdict.PASS,
        reasoning_summary="All checks consistent.",
        issues=[],
    )
    payload = output.model_dump()
    assert payload["verdict"] == JudgeVerdict.PASS.value


def test_judge_issue_schema_validates():
    issue = JudgeIssue(
        code="SIMULATION_FAILED",
        severity=JudgeIssueSeverity.HIGH,
        message="Simulation failed for candidate 0.",
        data={"index": 0},
    )
    payload = issue.model_dump()
    assert payload["severity"] == JudgeIssueSeverity.HIGH.value


def test_judge_output_invalid_verdict_rejected():
    with pytest.raises(ValidationError):
        JudgeOutput(
            verdict="BAD",
            reasoning_summary="bad",
            issues=[],
        )
