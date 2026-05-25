"""Signed envelope chain for Judgment records.

The audit-chain pattern mirrors the one in ``phionyx_langchain_langgraph``
and ``phionyx_mcp_server``: each Judgment becomes a JSON payload with
``schema``, ``subject``, ``judgment``, and an ``integrity`` block whose
``current`` hash binds to the previous envelope's ``current``.

The signing surface is intentionally minimal — production deployments
substitute Ed25519 for the demo HMAC.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from .protocols import Judgment

GENESIS_HASH = "sha256:" + "0" * 64
JUDGMENT_SCHEMA = "phionyx.judgment_envelope.v1"
RUNTIME = "phionyx-eval"


def canonical_json(payload: Any) -> str:
    """Deterministic JSON encoding: sorted keys, no whitespace, NaN-rejected."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def envelope_hash(payload: dict[str, Any], previous_hash: str) -> str:
    """SHA-256 over canonical-JSON ``{record: payload, previous: previous_hash}``."""
    blob = canonical_json({"record": payload, "previous": previous_hash})
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


class JudgmentSigner(Protocol):
    """Signer Protocol — production swaps to Ed25519."""

    def sign(self, current_hash: str) -> str:
        ...


class HmacJudgmentSigner:
    """Demo-grade HMAC signer for the eval-side judgment chain.

    NOT cryptographically suitable for production — the secret default is
    public. Production deployments substitute an Ed25519 implementation
    that satisfies the :class:`JudgmentSigner` protocol.
    """

    def __init__(self, secret: str = "phionyx.eval.demo.replace.in.production") -> None:
        self._secret = secret.encode("utf-8")

    def sign(self, current_hash: str) -> str:
        digest = hmac.new(
            self._secret, current_hash.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return f"hmac-sha256:{digest}"


@dataclass
class JudgmentEnvelope:
    """In-memory view of one signed Judgment envelope."""

    schema: str
    subject: dict[str, Any]
    judgment: dict[str, Any]
    integrity: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "subject": self.subject,
            "judgment": self.judgment,
            "integrity": self.integrity,
        }


def build_judgment_envelope(
    *,
    judgment: Judgment,
    package_version: str,
    previous_hash: str,
    turn_index: int,
    signer: JudgmentSigner | None = None,
) -> dict[str, Any]:
    """Build one signed envelope from a :class:`Judgment`.

    The hash domain covers ``schema`` + ``subject`` + ``judgment``. The
    ``integrity`` block is added after the hash is computed.

    Parameters
    ----------
    judgment:
        The :class:`Judgment` produced by :class:`LLMAsJudge`.
    package_version:
        Version string written into ``subject.version`` (typically the
        caller's ``phionyx_eval.__version__``).
    previous_hash:
        Previous envelope's ``integrity.current`` (or :data:`GENESIS_HASH`).
    turn_index:
        Monotonic counter for this chain.
    signer:
        Signer instance. Defaults to :class:`HmacJudgmentSigner`.

    Returns:
        The envelope dict, ready for persistence or transport.
    """
    signer = signer or HmacJudgmentSigner()

    payload: dict[str, Any] = {
        "schema": JUDGMENT_SCHEMA,
        "subject": {
            "runtime": RUNTIME,
            "version": package_version,
            "turn_index": turn_index,
            "rubric_name": judgment.rubric_name,
            "verdict": judgment.verdict,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        },
        "judgment": judgment.model_dump(mode="json"),
    }

    current_hash = envelope_hash(payload, previous_hash)
    payload["integrity"] = {
        "previous": previous_hash,
        "current": current_hash,
        "signature": signer.sign(current_hash),
        "canonical_json": True,
    }
    return payload
