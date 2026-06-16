# phionyx-eval

> LLM-as-judge primitive (eval-side) for Phionyx runtime-evidence chains. Score a (claim, evidence) pair under a rubric; produce a signed Judgment envelope; verify the chain end-to-end. The caller supplies the LLM client — there is no hard dependency on any provider SDK.

## Status

**v0.1.0a1 — alpha.** This is an **eval-side adapter** in the Phionyx portfolio (it carries its own version line, independent of the engine and the evidence format it composes with). It is published to the public [`halvrenofviryel/phionyx-eval`](https://github.com/halvrenofviryel/phionyx-eval) repo.

### Where this sits in the Phionyx stack

| Component | Repo / package | Role | Version |
|---|---|---|---|
| **Engine** | `phionyx-core` | Deterministic runtime (46-block pipeline, audit chain) | v0.8.1 |
| **Evidence format** | `ai-runtime-evidence-protocol` | AI Runtime Evidence Protocol (AIREP) — a vendor-neutral, experimental open format for a per-decision AI decision receipt | v0.1 (experimental) |
| **This package** | `phionyx-eval` (adapter) | Eval-side LLM-as-judge for claim/evidence pairs | **v0.1.0a1** |

`phionyx-eval` is an adapter, not the engine or the evidence format. It produces a `JudgmentEnvelope` — a signed, hash-chained record of one judgment — which sits alongside the AIREP decision records emitted by the Phionyx runtime.

## What this package is

A small eval-side toolkit:

- **`LLMClient`** — Protocol surface (`complete(prompt: str) -> str`). Plug in Anthropic SDK, OpenAI SDK, LiteLLM, an HTTP wrapper, or a mock.
- **`Rubric`** — Pydantic model for a scoring rubric: criteria, integer scale, normalised pass threshold. Four canonical Phionyx rubrics ship by default.
- **`LLMAsJudge`** — judges one (claim, evidence) pair under a rubric. Produces a `Judgment` with per-criterion scores, an aggregate normalised score, a deterministic verdict (pass / fail / uncertain), and the model's overall rationale.
- **`build_judgment_envelope`** — wraps a `Judgment` in a signed, hash-chained envelope. Mirrors the audit-chain pattern used by `phionyx-langchain-langgraph` and `phionyx-mcp-server`.

## What this package is NOT

- **NOT a runtime reasoning component.** LLM-as-judge is a measurement tool. It does not update memory or affect determinism in `phionyx-core` — measurement only, not a runtime reasoning component and not a capability advance.
- **NOT a benchmark runner.** It scores one (claim, evidence) pair at a time. Batch evaluation, score aggregation across many calls, and dashboarding are out of scope for v0.1.
- **NOT a compliance certifier.** Phionyx publishes mappings; it does not issue compliance guarantees. A passing judgment is *passed structural rubric evaluation*, not *approved for production*.

## Install

```bash
pip install phionyx-eval
```

Requires Python ≥3.10 and `phionyx-core`. The package declares a `phionyx-core >= 0.5.0` floor; it is tested against the current `phionyx-core` v0.8.x line.

## 60-second usage

```python
from phionyx_eval import (
    EVIDENCE_COVERAGE_RUBRIC,
    LLMAsJudge,
    build_judgment_envelope,
    GENESIS_HASH,
    __version__,
)

class MyClient:
    """Your existing LLM client — anything with .complete(prompt) -> str."""
    def complete(self, prompt: str) -> str:
        return your_llm.invoke(prompt)  # replace with your call

judge = LLMAsJudge(MyClient())
verdict = judge.judge(
    claim="Fixed the off-by-one in paginate() for the empty-input case",
    evidence="pytest tests/unit/test_paginate.py -k off_by_one — 1/1 pass",
    rubric=EVIDENCE_COVERAGE_RUBRIC,
)
print(verdict.verdict, verdict.aggregate_score)

# Wrap the judgment in a signed envelope for the audit chain:
envelope = build_judgment_envelope(
    judgment=verdict,
    package_version=__version__,
    previous_hash=GENESIS_HASH,  # or the previous envelope's integrity.current
    turn_index=0,
)
```

## Standard rubrics

| Rubric | Pass threshold | Criteria |
|---|---|---|
| `EVIDENCE_COVERAGE_RUBRIC` | 0.7 | `evidence_addresses_claim_scope`, `evidence_exercises_claimed_paths`, `evidence_independent_of_claim_text` |
| `CORRECTNESS_RUBRIC` | 0.7 | `claim_consistent_with_evidence`, `no_internal_contradictions`, `scope_appropriately_qualified` |
| `COMPLETENESS_RUBRIC` | 0.6 | `claim_addresses_full_user_scope`, `omissions_explicitly_acknowledged`, `edge_cases_considered` |
| `INDEPENDENT_VERIFIABILITY_RUBRIC` | 0.7 | `evidence_contains_reproduction_steps`, `evidence_names_specific_paths_or_commands`, `evidence_independent_of_agent_narration` |

All four use a 0–5 integer scale per criterion. Caller-authored rubrics work the same way; pass a `Rubric` instance to `judge.judge(...)`.

## Verdict derivation

Verdicts are deterministic, not LLM-emitted:

1. Average the per-criterion integer scores.
2. Normalise into [0, 1] against `(scale_max - scale_min)`.
3. If `aggregate >= pass_threshold` → `pass`.
4. Else if `aggregate >= pass_threshold - 0.05` → `uncertain` (near-miss band).
5. Else → `fail`.

The LLM does not vote on its own pass/fail.

## Composing with the Phionyx audit chain

The `JudgmentEnvelope` follows the same hash-chained pattern Phionyx uses for `AgentMessageEnvelope` and the `subagent_chain` block. A producer accumulating many judgments builds a single linear chain by passing the prior envelope's `integrity.current` as the next call's `previous_hash`. Tampering any envelope's payload (claim text, rubric name, score, rationale) breaks `envelope_hash` recomputation.

## Cross-runtime importers

Import Langfuse traces and LangSmith runs into Phionyx envelope chains. Round-trip lossless for the mappable fields named below; non-mappable foreign fields are preserved verbatim under `subject.metadata.imported_extras` so a future Phionyx-side exporter could reconstruct the foreign shape.

### Langfuse

```python
from phionyx_eval import import_langfuse_trace

result = import_langfuse_trace(langfuse_trace_dict)
# result.envelopes[0]   → trace_root envelope
# result.envelopes[1:]  → one envelope per observation, in original order
# result.mapping_report → MappingReport (mapped_fields, preserved_extras, dropped_fields)
```

Mappable Langfuse fields:

| Foreign | Phionyx |
|---|---|
| `id` | `subject.foreign_trace_id` |
| `name`, `userId`, `sessionId`, `release`, `version`, `input`, `output`, `metadata`, `tags`, `public`, `createdAt`, `updatedAt` | `record.<snake_case>` |
| Observation `id` | `record.observation_id` |
| Observation `type` | `subject.event_type` |
| Observation `name`, `startTime`, `endTime`, `input`, `output`, `level`, `statusMessage`, `model`, `modelParameters`, `usage`, `parentObservationId` | `record.<snake_case>` |

Schema: `phionyx.imported_langfuse_envelope.v1`.

### LangSmith

```python
from phionyx_eval import import_langsmith_run

result = import_langsmith_run(
    root_run_dict,
    descendants=descendant_run_dicts,  # optional; resolved via child_run_ids
)
# result.envelopes is in depth-first pre-order traversal of the run tree.
```

Mappable LangSmith fields per run:

| Foreign | Phionyx |
|---|---|
| `id` | `subject.foreign_trace_id` |
| `run_type` | `subject.event_type` |
| `name`, `inputs`, `outputs`, `start_time`, `end_time`, `error`, `extra`, `parent_run_id`, `child_run_ids`, `events`, `feedback` | `record.<snake_case>` |

Schema: `phionyx.imported_langsmith_envelope.v1`. Tree shape preserved in `record.parent_run_id` / `record.child_run_ids` so a downstream consumer can reconstruct the tree.

### Composition with the judge

The output of either importer is a list of Phionyx envelopes. The LLMAsJudge can then run over any envelope's `record` payload to score a specific claim (e.g. *the drafting step's output addresses the input*) under an evidence-coverage rubric — turning a third-party trace into a Phionyx-evaluable evidence record without re-running the original system.

## Composing with AIREP decision records

The four built-in rubrics implement Phionyx's cross-domain evidence baseline. They compose cleanly with the [AI Runtime Evidence Protocol (AIREP)](https://github.com/halvrenofviryel/ai-runtime-evidence-protocol) — an experimental, vendor-neutral open format for a per-decision **AI decision receipt**: one signed, hash-chained, offline-checkable record per AI runtime decision, readable by anyone and tied to no vendor.

An AIREP record names *what happened* in a decision — its `claim`, the `evidence` cited, the `output`, and the `integrity` hash chain that ties them together. This package names *how* a judge grades the evidence quality behind one of those claims. The two compose: a judge can run `EVIDENCE_COVERAGE_RUBRIC` over the `claim`/`evidence` pair carried in an AIREP record to grade whether the claim is actually supported by the evidence cited.

The Phionyx **Reasoned Governance Envelope (RGE)** is AIREP's reference producer — the first system that emits AIREP records, maturing by conforming to the format. AIREP is an experimental, proposed open format with one reference implementation; it is not a ratified standard.

## License

AGPL-3.0-or-later, consistent with the rest of the Phionyx open-source distribution.

## Links

- [Phionyx Research](https://phionyx.ai)
- [AI Runtime Evidence Protocol (AIREP)](https://github.com/halvrenofviryel/ai-runtime-evidence-protocol)
- [phionyx-core on PyPI](https://pypi.org/project/phionyx-core/)
