"""Tests for the Judgment envelope chain.

Verifies that build_judgment_envelope produces hash-linked records and
that mutation of any envelope's payload breaks the chain.
"""

from __future__ import annotations

import pytest

from phionyx_eval import (
    EVIDENCE_COVERAGE_RUBRIC,
    GENESIS_HASH,
    JUDGMENT_SCHEMA,
    Judgment,
    JudgmentScore,
    build_judgment_envelope,
    canonical_json,
    envelope_hash,
    __version__,
)
from phionyx_eval.envelope import HmacJudgmentSigner


def _make_judgment(score: int = 5) -> Judgment:
    rubric = EVIDENCE_COVERAGE_RUBRIC
    scores = [JudgmentScore(criterion=c, score=score, rationale="ok") for c in rubric.criteria]
    span = rubric.scale_max - rubric.scale_min
    aggregate = (score - rubric.scale_min) / span if span > 0 else 0.0
    return Judgment(
        rubric_name=rubric.name,
        scores=scores,
        aggregate_score=aggregate,
        verdict="pass" if aggregate >= rubric.pass_threshold else "fail",
        rationale="overall ok",
    )


# ---------------------------------------------------------------------------
# Envelope construction
# ---------------------------------------------------------------------------


class TestBuildEnvelope:
    def test_basic_envelope_shape(self):
        judgment = _make_judgment()
        env = build_judgment_envelope(
            judgment=judgment,
            package_version=__version__,
            previous_hash=GENESIS_HASH,
            turn_index=0,
        )
        assert env["schema"] == JUDGMENT_SCHEMA
        assert env["subject"]["runtime"] == "phionyx-eval"
        assert env["subject"]["rubric_name"] == judgment.rubric_name
        assert env["subject"]["verdict"] == judgment.verdict
        assert env["subject"]["turn_index"] == 0
        assert env["judgment"]["rubric_name"] == judgment.rubric_name
        assert env["integrity"]["previous"] == GENESIS_HASH
        assert env["integrity"]["current"].startswith("sha256:")
        assert env["integrity"]["signature"].startswith("hmac-sha256:")
        assert env["integrity"]["canonical_json"] is True

    def test_hash_chain_links(self):
        env1 = build_judgment_envelope(
            judgment=_make_judgment(5),
            package_version=__version__,
            previous_hash=GENESIS_HASH,
            turn_index=0,
        )
        env2 = build_judgment_envelope(
            judgment=_make_judgment(4),
            package_version=__version__,
            previous_hash=env1["integrity"]["current"],
            turn_index=1,
        )
        assert env2["integrity"]["previous"] == env1["integrity"]["current"]
        assert env2["integrity"]["current"] != env1["integrity"]["current"]

    def test_hash_recomputable_from_payload(self):
        env = build_judgment_envelope(
            judgment=_make_judgment(),
            package_version=__version__,
            previous_hash=GENESIS_HASH,
            turn_index=0,
        )
        hash_inputs = {k: v for k, v in env.items() if k != "integrity"}
        recomputed = envelope_hash(hash_inputs, env["integrity"]["previous"])
        assert recomputed == env["integrity"]["current"]

    def test_tampering_payload_breaks_recomputed_hash(self):
        env = build_judgment_envelope(
            judgment=_make_judgment(),
            package_version=__version__,
            previous_hash=GENESIS_HASH,
            turn_index=0,
        )
        # Tamper a judgment field
        env["judgment"]["rationale"] = "TAMPERED"
        hash_inputs = {k: v for k, v in env.items() if k != "integrity"}
        recomputed = envelope_hash(hash_inputs, env["integrity"]["previous"])
        assert recomputed != env["integrity"]["current"]


class TestCanonicalJson:
    def test_keys_sorted(self):
        out = canonical_json({"b": 1, "a": 2})
        assert out == '{"a":2,"b":1}'

    def test_no_whitespace(self):
        out = canonical_json({"x": [1, 2, 3]})
        assert " " not in out

    def test_nan_rejected(self):
        with pytest.raises(ValueError):
            canonical_json({"x": float("nan")})


class TestSignerSubstitution:
    def test_custom_signer_is_used(self):
        class StubSigner:
            def __init__(self) -> None:
                self.calls = 0

            def sign(self, current_hash: str) -> str:
                self.calls += 1
                return f"stub:{current_hash[:8]}"

        signer = StubSigner()
        env = build_judgment_envelope(
            judgment=_make_judgment(),
            package_version=__version__,
            previous_hash=GENESIS_HASH,
            turn_index=0,
            signer=signer,
        )
        assert signer.calls == 1
        assert env["integrity"]["signature"].startswith("stub:")

    def test_hmac_signer_default(self):
        env = build_judgment_envelope(
            judgment=_make_judgment(),
            package_version=__version__,
            previous_hash=GENESIS_HASH,
            turn_index=0,
        )
        assert env["integrity"]["signature"].startswith("hmac-sha256:")

    def test_hmac_signer_deterministic_for_same_hash(self):
        s = HmacJudgmentSigner(secret="fixed")
        h = "sha256:" + "a" * 64
        assert s.sign(h) == s.sign(h)
