"""Phionyx-eval quickstart — LLM-as-judge against a canned response.

This example uses a fake LLM client that returns a pre-baked JSON
response so you can run it without a real API key. Replace ``FakeClient``
with your own client (Anthropic SDK, OpenAI SDK, LiteLLM, etc.) in real
use — anything with ``.complete(prompt: str) -> str`` works.

Run:

    python examples/quickstart.py
"""

from __future__ import annotations

import json

from phionyx_eval import (
    EVIDENCE_COVERAGE_RUBRIC,
    GENESIS_HASH,
    LLMAsJudge,
    build_judgment_envelope,
    canonical_json,
    __version__,
)


class FakeClient:
    """Demo LLM client. In production, replace with your real client."""

    def complete(self, prompt: str) -> str:  # noqa: ARG002
        return json.dumps(
            {
                "scores": [
                    {
                        "criterion": "evidence_addresses_claim_scope",
                        "score": 5,
                        "rationale": "test name names the claim's scope",
                    },
                    {
                        "criterion": "evidence_exercises_claimed_paths",
                        "score": 4,
                        "rationale": "pytest -k filter exercises paginate()",
                    },
                    {
                        "criterion": "evidence_independent_of_claim_text",
                        "score": 5,
                        "rationale": "test output is independent of agent narration",
                    },
                ],
                "rationale": "Evidence is reproducible and exercises the claimed scope.",
            }
        )


def main() -> None:
    judge = LLMAsJudge(FakeClient())
    judgment = judge.judge(
        claim="Fixed the off-by-one in paginate() for the empty-input case",
        evidence=(
            "pytest tests/unit/test_paginate.py -k off_by_one — 1/1 pass; "
            "diff shows the fix at src/paginate.py:42; expected empty-list "
            "input now returns Page(items=[], total=0)."
        ),
        rubric=EVIDENCE_COVERAGE_RUBRIC,
    )
    print(f"verdict:         {judgment.verdict}")
    print(f"aggregate_score: {judgment.aggregate_score:.2f}")
    print(f"rubric:          {judgment.rubric_name}")
    print(f"rationale:       {judgment.rationale}")
    print()
    print("Per-criterion scores:")
    for s in judgment.scores:
        print(f"  - {s.criterion}: {s.score}/{EVIDENCE_COVERAGE_RUBRIC.scale_max}  ({s.rationale})")

    envelope = build_judgment_envelope(
        judgment=judgment,
        package_version=__version__,
        previous_hash=GENESIS_HASH,
        turn_index=0,
    )
    print()
    print("Signed envelope:")
    print(canonical_json(envelope))


if __name__ == "__main__":
    main()
