"""Tests for LLMAsJudge + parse_judgment_response.

Uses a deterministic FakeLLMClient — no real API calls. Each test
either returns a canned JSON response or a malformed response to
exercise the parser's error paths.
"""

from __future__ import annotations

import json
from typing import Iterator

import pytest

from phionyx_eval import (
    EVIDENCE_COVERAGE_RUBRIC,
    LLMAsJudge,
    LLMClient,
    parse_judgment_response,
)


class FakeLLMClient:
    """Returns the next pre-recorded response per call."""

    def __init__(self, responses: list[str]) -> None:
        self._iter: Iterator[str] = iter(responses)

    def complete(self, prompt: str) -> str:
        return next(self._iter)


def _good_response(scores: list[tuple[str, int, str]], rationale: str = "ok") -> str:
    return json.dumps(
        {
            "scores": [
                {"criterion": c, "score": s, "rationale": r}
                for c, s, r in scores
            ],
            "rationale": rationale,
        }
    )


# ---------------------------------------------------------------------------
# Happy-path judgment flow
# ---------------------------------------------------------------------------


class TestJudgeHappyPath:
    def test_passing_judgment_returns_pass_verdict(self):
        rubric = EVIDENCE_COVERAGE_RUBRIC
        client = FakeLLMClient(
            [
                _good_response(
                    [(c, rubric.scale_max, "ok") for c in rubric.criteria]
                )
            ]
        )
        judge = LLMAsJudge(client)
        verdict = judge.judge(
            claim="Fixed the off-by-one in paginate()",
            evidence="pytest tests/unit/test_paginate.py -k off_by_one passed 1/1",
            rubric=rubric,
        )
        assert verdict.rubric_name == "evidence_coverage"
        assert verdict.verdict == "pass"
        assert verdict.aggregate_score == 1.0
        assert len(verdict.scores) == len(rubric.criteria)

    def test_failing_judgment_returns_fail_verdict(self):
        rubric = EVIDENCE_COVERAGE_RUBRIC
        client = FakeLLMClient(
            [_good_response([(c, 0, "no evidence") for c in rubric.criteria])]
        )
        judge = LLMAsJudge(client)
        verdict = judge.judge(
            claim="Fixed bar.py::bar()",
            evidence="(none)",
            rubric=rubric,
        )
        assert verdict.verdict == "fail"
        assert verdict.aggregate_score == 0.0

    def test_uncertain_band_5pct_below_threshold(self):
        # Threshold 0.7; aggregate 0.67 → uncertain
        rubric = EVIDENCE_COVERAGE_RUBRIC
        # scores [3, 3, 4] avg=3.333 normalised=(3.333-0)/5 = 0.667
        client = FakeLLMClient(
            [
                _good_response(
                    [
                        (rubric.criteria[0], 3, "partial"),
                        (rubric.criteria[1], 3, "partial"),
                        (rubric.criteria[2], 4, "partial"),
                    ]
                )
            ]
        )
        judge = LLMAsJudge(client)
        verdict = judge.judge(
            claim="Fixed paginate()",
            evidence="manual repro on one input",
            rubric=rubric,
        )
        assert verdict.verdict == "uncertain"
        assert 0.65 <= verdict.aggregate_score <= 0.70

    def test_metadata_passthrough(self):
        rubric = EVIDENCE_COVERAGE_RUBRIC
        client = FakeLLMClient(
            [_good_response([(c, 5, "ok") for c in rubric.criteria])]
        )
        judge = LLMAsJudge(client)
        verdict = judge.judge(
            claim="x",
            evidence="y",
            rubric=rubric,
            metadata={"trace_id": "trace-abc", "model": "test-fake"},
        )
        assert verdict.metadata == {"trace_id": "trace-abc", "model": "test-fake"}


# ---------------------------------------------------------------------------
# Parser error paths
# ---------------------------------------------------------------------------


class TestParserErrorPaths:
    def test_non_json_response_rejected(self):
        with pytest.raises(ValueError, match="not valid JSON"):
            parse_judgment_response(
                response_text="this is not JSON at all",
                rubric=EVIDENCE_COVERAGE_RUBRIC,
            )

    def test_array_response_rejected(self):
        with pytest.raises(ValueError, match="must be a JSON object"):
            parse_judgment_response(
                response_text='["just", "an", "array"]',
                rubric=EVIDENCE_COVERAGE_RUBRIC,
            )

    def test_missing_scores_rejected(self):
        with pytest.raises(ValueError, match="'scores'"):
            parse_judgment_response(
                response_text='{"rationale": "ok"}',
                rubric=EVIDENCE_COVERAGE_RUBRIC,
            )

    def test_unknown_criterion_rejected(self):
        with pytest.raises(ValueError, match="unknown criterion"):
            parse_judgment_response(
                response_text=_good_response(
                    [("invented_criterion_name", 5, "ok")]
                ),
                rubric=EVIDENCE_COVERAGE_RUBRIC,
            )

    def test_out_of_range_score_rejected(self):
        rubric = EVIDENCE_COVERAGE_RUBRIC
        # scale_max is 5; supply 7 → out of range
        with pytest.raises(ValueError, match="outside rubric scale"):
            parse_judgment_response(
                response_text=_good_response([(rubric.criteria[0], 7, "over")]),
                rubric=rubric,
            )

    def test_negative_score_rejected(self):
        rubric = EVIDENCE_COVERAGE_RUBRIC
        with pytest.raises(ValueError, match="outside rubric scale"):
            parse_judgment_response(
                response_text=_good_response([(rubric.criteria[0], -1, "under")]),
                rubric=rubric,
            )

    def test_missing_score_field_rejected(self):
        rubric = EVIDENCE_COVERAGE_RUBRIC
        bad_response = json.dumps(
            {"scores": [{"criterion": rubric.criteria[0], "rationale": "no score"}]}
        )
        with pytest.raises(ValueError, match="integer 'score'"):
            parse_judgment_response(
                response_text=bad_response, rubric=rubric
            )

    def test_markdown_fenced_response_is_tolerated(self):
        rubric = EVIDENCE_COVERAGE_RUBRIC
        body = _good_response([(c, 5, "ok") for c in rubric.criteria])
        wrapped = f"```json\n{body}\n```"
        judgment = parse_judgment_response(response_text=wrapped, rubric=rubric)
        assert judgment.verdict == "pass"

    def test_empty_response_rejected(self):
        with pytest.raises(ValueError, match="not valid JSON"):
            parse_judgment_response(
                response_text="",
                rubric=EVIDENCE_COVERAGE_RUBRIC,
            )


# ---------------------------------------------------------------------------
# Judge input validation
# ---------------------------------------------------------------------------


class TestJudgeInputValidation:
    def test_empty_claim_rejected(self):
        client = FakeLLMClient([])  # never called
        judge = LLMAsJudge(client)
        with pytest.raises(ValueError, match="claim must be non-empty"):
            judge.judge(claim="", evidence="x", rubric=EVIDENCE_COVERAGE_RUBRIC)

    def test_whitespace_claim_rejected(self):
        client = FakeLLMClient([])
        judge = LLMAsJudge(client)
        with pytest.raises(ValueError, match="claim must be non-empty"):
            judge.judge(claim="   ", evidence="x", rubric=EVIDENCE_COVERAGE_RUBRIC)

    def test_empty_evidence_rejected(self):
        client = FakeLLMClient([])
        judge = LLMAsJudge(client)
        with pytest.raises(ValueError, match="evidence must be non-empty"):
            judge.judge(claim="Fixed x", evidence="", rubric=EVIDENCE_COVERAGE_RUBRIC)


# ---------------------------------------------------------------------------
# LLMClient protocol smoke (structural)
# ---------------------------------------------------------------------------


def test_fake_client_satisfies_llmclient_protocol():
    """Structural check: FakeLLMClient duck-types LLMClient."""
    client: LLMClient = FakeLLMClient(["{}"])
    assert hasattr(client, "complete")
    assert callable(client.complete)
