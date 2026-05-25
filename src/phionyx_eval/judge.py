"""LLM-as-judge: ask an LLM to score a (claim, evidence) pair under a rubric.

The judge constructs a structured prompt instructing the model to return
JSON with per-criterion integer scores plus an overall rationale, then
parses the response into a ``Judgment``. The verdict is derived
deterministically from the aggregate score vs the rubric's pass threshold
— the judge does NOT trust the model to grade its own pass/fail.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from .protocols import (
    Judgment,
    JudgmentScore,
    JudgmentVerdict,
    LLMClient,
    Rubric,
)


def _build_prompt(*, claim: str, evidence: str, rubric: Rubric) -> str:
    """Construct the judge prompt for one (claim, evidence, rubric) triple."""
    criteria_block = "\n".join(
        f"  - {c}: integer in [{rubric.scale_min}, {rubric.scale_max}]"
        for c in rubric.criteria
    )
    return (
        f"You are scoring a claim against the supplied evidence. "
        f"Use the rubric below. Return JSON ONLY — no prose, no markdown.\n\n"
        f"## Rubric: {rubric.name}\n"
        f"{rubric.description}\n\n"
        f"## Criteria\n"
        f"{criteria_block}\n\n"
        f"## Claim\n"
        f"{claim}\n\n"
        f"## Evidence\n"
        f"{evidence}\n\n"
        f"## Required response shape\n"
        f"{{\n"
        f'  "scores": [\n'
        f'    {{"criterion": "<one of the criteria above>", "score": <int>, "rationale": "<short>"}}\n'
        f"  ],\n"
        f'  "rationale": "<overall rationale, 1-3 sentences>"\n'
        f"}}\n\n"
        f"Return JSON only."
    )


def _aggregate(scores: list[JudgmentScore], rubric: Rubric) -> float:
    """Average per-criterion scores then normalise to [0, 1]."""
    if not scores:
        return 0.0
    total = sum(s.score for s in scores)
    avg = total / len(scores)
    span = rubric.scale_max - rubric.scale_min
    if span <= 0:
        return 0.0
    normalised = (avg - rubric.scale_min) / span
    # Clamp into [0, 1] in case the model returned out-of-range values.
    return max(0.0, min(1.0, normalised))


def _derive_verdict(aggregate: float, rubric: Rubric) -> JudgmentVerdict:
    """Deterministic verdict derivation from aggregate score vs threshold."""
    if aggregate >= rubric.pass_threshold:
        return "pass"
    # An "uncertain" band 5% below the threshold lets the caller spot
    # near-misses without committing them as failures.
    if aggregate >= rubric.pass_threshold - 0.05:
        return "uncertain"
    return "fail"


def parse_judgment_response(
    *,
    response_text: str,
    rubric: Rubric,
    metadata: dict[str, Any] | None = None,
) -> Judgment:
    """Parse a judge model response into a :class:`Judgment`.

    The response is expected to be a JSON object with keys ``scores`` (list
    of per-criterion entries) and ``rationale`` (overall rationale string).
    The function is forgiving about leading / trailing whitespace and
    accidental markdown code fences; anything else is a parse error.
    """
    cleaned = response_text.strip()

    # Tolerate the common "```json ... ```" wrapping.
    fence_match = re.search(
        r"```(?:json)?\s*(\{.*\})\s*```", cleaned, flags=re.DOTALL
    )
    if fence_match:
        cleaned = fence_match.group(1)

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"judge response was not valid JSON: {exc.msg}; got {cleaned[:200]!r}"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError(
            f"judge response must be a JSON object, got {type(payload).__name__}"
        )

    raw_scores = payload.get("scores", [])
    if not isinstance(raw_scores, list) or not raw_scores:
        raise ValueError("judge response missing non-empty 'scores' list")

    valid_criteria = set(rubric.criteria)
    scores: list[JudgmentScore] = []
    for entry in raw_scores:
        if not isinstance(entry, dict):
            raise ValueError(f"score entry must be an object, got {type(entry).__name__}")
        criterion = entry.get("criterion")
        if criterion not in valid_criteria:
            raise ValueError(
                f"score for unknown criterion {criterion!r}; rubric criteria are {sorted(valid_criteria)}"
            )
        try:
            score_value = int(entry["score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"score entry missing integer 'score' field: {entry!r}") from exc
        if score_value < rubric.scale_min or score_value > rubric.scale_max:
            raise ValueError(
                f"score {score_value} for criterion {criterion!r} outside rubric "
                f"scale [{rubric.scale_min}, {rubric.scale_max}]"
            )
        scores.append(
            JudgmentScore(
                criterion=criterion,
                score=score_value,
                rationale=str(entry.get("rationale", "")),
            )
        )

    aggregate = _aggregate(scores, rubric)
    verdict = _derive_verdict(aggregate, rubric)
    rationale = str(payload.get("rationale", ""))

    try:
        return Judgment(
            rubric_name=rubric.name,
            scores=scores,
            aggregate_score=aggregate,
            verdict=verdict,
            rationale=rationale,
            metadata=metadata or {},
        )
    except ValidationError as exc:
        # Re-raise as ValueError to keep the public API single-typed.
        raise ValueError(f"judgment validation failed: {exc}") from exc


class LLMAsJudge:
    """Score a (claim, evidence) pair against a rubric using an LLM.

    Parameters
    ----------
    client:
        Caller-supplied LLM client implementing the :class:`LLMClient`
        protocol — a single ``complete(prompt: str) -> str`` method.
    """

    def __init__(self, client: LLMClient) -> None:
        self._client = client

    def judge(
        self,
        *,
        claim: str,
        evidence: str,
        rubric: Rubric,
        metadata: dict[str, Any] | None = None,
    ) -> Judgment:
        """Run one judgment.

        Raises:
            ValueError: if the LLM response cannot be parsed against the rubric.
        """
        if not claim or not claim.strip():
            raise ValueError("claim must be non-empty")
        if not evidence or not evidence.strip():
            raise ValueError("evidence must be non-empty")

        prompt = _build_prompt(claim=claim, evidence=evidence, rubric=rubric)
        response_text = self._client.complete(prompt)
        return parse_judgment_response(
            response_text=response_text,
            rubric=rubric,
            metadata=metadata,
        )
