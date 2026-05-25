"""Protocols and Pydantic models for LLM-as-judge.

The LLM client surface is a Protocol — callers provide whatever client they
already use (Anthropic SDK, OpenAI SDK, LiteLLM, a custom HTTP wrapper, a
mock for tests). The judge only needs a ``complete(prompt: str) -> str``
contract; everything else is the judge's responsibility.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


JudgmentVerdict = Literal["pass", "fail", "uncertain"]


class LLMClient(Protocol):
    """Caller-supplied LLM client surface.

    Implementations return a plain-text completion for the supplied prompt.
    The judge does the prompt construction and response parsing; the client
    is just a thin transport. This Protocol intentionally does NOT include
    streaming, tool-calling, or system-prompt overrides — the judge is
    stateless and stringly-typed by design.
    """

    def complete(self, prompt: str) -> str:
        ...


class Rubric(BaseModel):
    """Scoring rubric for one judgment.

    A rubric names the criteria the judge should score against, the
    integer scale to use, and a normalised pass threshold. The rubric
    description is read by both the judge (when constructing the prompt)
    and any human reviewer (when interpreting the result).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1)
    criteria: list[str] = Field(..., min_length=1)
    scale_min: int = Field(..., ge=0)
    scale_max: int = Field(..., gt=0)
    pass_threshold: float = Field(..., ge=0.0, le=1.0)

    @field_validator("scale_max")
    @classmethod
    def _scale_max_greater_than_min(cls, v: int, info) -> int:
        scale_min = info.data.get("scale_min")
        if scale_min is not None and v <= scale_min:
            raise ValueError(
                f"scale_max ({v}) must be strictly greater than scale_min ({scale_min})"
            )
        return v

    @field_validator("criteria")
    @classmethod
    def _criteria_unique_and_nonempty(cls, v: list[str]) -> list[str]:
        if any(not c.strip() for c in v):
            raise ValueError("criteria entries must be non-empty strings")
        if len(set(v)) != len(v):
            raise ValueError("criteria must be unique")
        return list(v)


class JudgmentScore(BaseModel):
    """One criterion-level score within a Judgment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    criterion: str = Field(..., min_length=1)
    score: int = Field(...)
    rationale: str = Field(default="", description="Per-criterion rationale; may be empty.")


class Judgment(BaseModel):
    """Output of one LLM-as-judge call.

    The judgment commits to:
        - which rubric it was scored against (by name)
        - the per-criterion scores
        - an aggregate normalised score in [0, 1]
        - a verdict (pass / fail / uncertain) derived from
          aggregate_score vs the rubric's pass_threshold
        - the judge's free-text overall rationale
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    rubric_name: str = Field(..., min_length=1)
    scores: list[JudgmentScore] = Field(..., min_length=1)
    aggregate_score: float = Field(..., ge=0.0, le=1.0)
    verdict: JudgmentVerdict
    rationale: str = Field(default="", description="Free-text overall rationale.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Open object for caller-supplied metadata.")
