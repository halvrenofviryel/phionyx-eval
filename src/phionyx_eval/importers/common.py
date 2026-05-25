"""Shared infra for cross-runtime importers.

Defines:

- :class:`MappingReport` — per-importer record of which foreign fields
  mapped cleanly, which were preserved as ``imported_extras``, and which
  were dropped.
- :class:`ImportResult` — bundle of (Phionyx envelopes, mapping report).
- :func:`build_imported_envelope` — common helper that mirrors the
  audit-chain pattern from ``phionyx_eval.envelope`` but writes the
  importer's chosen schema identifier into ``schema``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..envelope import (
    HmacJudgmentSigner,
    JudgmentSigner,
    canonical_json,
    envelope_hash,
)


@dataclass
class MappingReport:
    """Record of what the importer did with each foreign field.

    ``mapped_fields`` — foreign field name → Phionyx envelope path.
    ``preserved_extras`` — foreign field name (string list); these are
    written verbatim under ``subject.metadata.imported_extras``.
    ``dropped_fields`` — foreign field names that the importer
    intentionally dropped (e.g. integration-specific noise).
    """

    mapped_fields: dict[str, str] = field(default_factory=dict)
    preserved_extras: list[str] = field(default_factory=list)
    dropped_fields: list[str] = field(default_factory=list)


@dataclass
class ImportResult:
    """Bundle returned by every importer."""

    envelopes: list[dict[str, Any]]
    mapping_report: MappingReport

    def __len__(self) -> int:
        return len(self.envelopes)


def build_imported_envelope(
    *,
    schema: str,
    importer_runtime: str,
    importer_version: str,
    foreign_trace_id: str,
    turn_index: int,
    event_type: str,
    record: dict[str, Any],
    imported_extras: dict[str, Any],
    previous_hash: str,
    signer: JudgmentSigner | None = None,
    timestamp_utc: str | None = None,
) -> dict[str, Any]:
    """Build one signed, hash-chained envelope from an importer.

    Mirrors :func:`phionyx_eval.envelope.build_judgment_envelope` but with
    the importer's choice of ``schema`` identifier and a generic
    ``record`` payload (the importer is responsible for what goes there).

    The ``subject.metadata.imported_extras`` field is the verbatim
    overflow space for foreign fields that do not map onto Phionyx's
    envelope shape but should be preserved for round-trip fidelity.
    """
    signer = signer or HmacJudgmentSigner()
    ts = timestamp_utc or datetime.now(timezone.utc).isoformat()

    payload: dict[str, Any] = {
        "schema": schema,
        "subject": {
            "runtime": importer_runtime,
            "version": importer_version,
            "turn_index": turn_index,
            "event_type": event_type,
            "foreign_trace_id": foreign_trace_id,
            "timestamp_utc": ts,
            "metadata": {
                "imported_extras": imported_extras,
            },
        },
        "record": record,
    }

    current_hash = envelope_hash(payload, previous_hash)
    payload["integrity"] = {
        "previous": previous_hash,
        "current": current_hash,
        "signature": signer.sign(current_hash),
        "canonical_json": True,
    }
    return payload


__all__ = [
    "ImportResult",
    "MappingReport",
    "build_imported_envelope",
    "canonical_json",
]
