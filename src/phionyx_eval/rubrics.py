"""Standard rubrics for Phionyx eval-side judging.

Four canonical dimensions, all framed around the runtime-evidence wedge
(*A model saying 'fixed' is not evidence — it is a claim*). Each rubric
fixes its criteria, the integer scale, and a normalised pass threshold.

These are the *defaults*. Callers are encouraged to author their own
rubrics for domain-specific judging; the standard set covers the
cross-domain baseline.
"""

from __future__ import annotations

from .protocols import Rubric


EVIDENCE_COVERAGE_RUBRIC = Rubric(
    name="evidence_coverage",
    description=(
        "Does the supplied evidence actually support the specific claim, or "
        "only support a near-neighbour claim? Coverage is judged against the "
        "claim's stated scope: a claim about path A is not covered by evidence "
        "that exercises path B."
    ),
    criteria=[
        "evidence_addresses_claim_scope",
        "evidence_exercises_claimed_paths",
        "evidence_independent_of_claim_text",
    ],
    scale_min=0,
    scale_max=5,
    pass_threshold=0.7,
)

CORRECTNESS_RUBRIC = Rubric(
    name="correctness",
    description=(
        "Given the supplied evidence, is the claim factually correct? "
        "A claim that the evidence contradicts scores low; a claim the "
        "evidence supports without ambiguity scores high. The judge does NOT "
        "assess whether the evidence itself is trustworthy — that is the "
        "evidence-coverage rubric's job."
    ),
    criteria=[
        "claim_consistent_with_evidence",
        "no_internal_contradictions",
        "scope_appropriately_qualified",
    ],
    scale_min=0,
    scale_max=5,
    pass_threshold=0.7,
)

COMPLETENESS_RUBRIC = Rubric(
    name="completeness",
    description=(
        "Does the claim cover the full scope the user asked about? A claim "
        "that addresses 60% of the asked surface and silently omits the rest "
        "scores low for completeness even if it is correct on the 60% it "
        "addresses."
    ),
    criteria=[
        "claim_addresses_full_user_scope",
        "omissions_explicitly_acknowledged",
        "edge_cases_considered",
    ],
    scale_min=0,
    scale_max=5,
    pass_threshold=0.6,
)

INDEPENDENT_VERIFIABILITY_RUBRIC = Rubric(
    name="independent_verifiability",
    description=(
        "Could a third party reproduce the verification from the supplied "
        "evidence alone, without trusting the agent's narration? Evidence "
        "that names test commands, paths, expected output, and reproduction "
        "steps scores high. Evidence that consists only of agent-narrated "
        "summaries scores low."
    ),
    criteria=[
        "evidence_contains_reproduction_steps",
        "evidence_names_specific_paths_or_commands",
        "evidence_independent_of_agent_narration",
    ],
    scale_min=0,
    scale_max=5,
    pass_threshold=0.7,
)


STANDARD_RUBRICS = (
    EVIDENCE_COVERAGE_RUBRIC,
    CORRECTNESS_RUBRIC,
    COMPLETENESS_RUBRIC,
    INDEPENDENT_VERIFIABILITY_RUBRIC,
)
