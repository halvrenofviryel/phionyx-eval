"""Phionyx evaluation tooling — F9 LLM-as-judge primitive (eval-side).

The package surfaces three things:

1. ``LLMClient`` — a minimal Protocol for the caller-supplied LLM client.
2. ``Rubric`` / ``Judgment`` / ``JudgmentScore`` — Pydantic models for
   structured judging input + output.
3. ``LLMAsJudge`` — the judge itself; given a (claim, evidence, rubric)
   triple, produces a ``Judgment``. Optional envelope emission via the
   audit-chain helpers.

Standard rubrics for the four eval-side dimensions Phionyx ships (evidence
coverage, correctness, completeness, independent verifiability) live in
``phionyx_eval.rubrics``.

This is an eval-time tool, NOT a runtime cognitive component. Per Phionyx's
AGI invariants, LLM-as-judge is a measurement primitive — it does not enter
the mind-loop, does not update memory, does not affect determinism in core.
"""

from __future__ import annotations

__version__ = "0.1.0a1"

from .protocols import (
    LLMClient,
    Rubric,
    Judgment,
    JudgmentScore,
    JudgmentVerdict,
)
from .judge import LLMAsJudge, parse_judgment_response
from .rubrics import (
    EVIDENCE_COVERAGE_RUBRIC,
    CORRECTNESS_RUBRIC,
    COMPLETENESS_RUBRIC,
    INDEPENDENT_VERIFIABILITY_RUBRIC,
    STANDARD_RUBRICS,
)
from .envelope import (
    JudgmentEnvelope,
    build_judgment_envelope,
    canonical_json,
    envelope_hash,
    GENESIS_HASH,
    JUDGMENT_SCHEMA,
)
from .importers import (
    ImportResult,
    MappingReport,
    build_imported_envelope,
    LANGFUSE_SCHEMA,
    LANGSMITH_SCHEMA,
    import_langfuse_trace,
    import_langsmith_run,
)

__all__ = [
    "__version__",
    # Protocols + models
    "LLMClient",
    "Rubric",
    "Judgment",
    "JudgmentScore",
    "JudgmentVerdict",
    # Judge
    "LLMAsJudge",
    "parse_judgment_response",
    # Rubrics
    "EVIDENCE_COVERAGE_RUBRIC",
    "CORRECTNESS_RUBRIC",
    "COMPLETENESS_RUBRIC",
    "INDEPENDENT_VERIFIABILITY_RUBRIC",
    "STANDARD_RUBRICS",
    # Envelope
    "JudgmentEnvelope",
    "build_judgment_envelope",
    "canonical_json",
    "envelope_hash",
    "GENESIS_HASH",
    "JUDGMENT_SCHEMA",
    # Importers (F13)
    "ImportResult",
    "MappingReport",
    "build_imported_envelope",
    "LANGFUSE_SCHEMA",
    "LANGSMITH_SCHEMA",
    "import_langfuse_trace",
    "import_langsmith_run",
]
