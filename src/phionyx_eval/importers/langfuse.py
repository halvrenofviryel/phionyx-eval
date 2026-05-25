"""Langfuse trace → Phionyx envelope chain.

Langfuse traces carry a top-level trace object with nested observations
(``generation``, ``span``, ``event``, ``score``). The importer emits one
Phionyx envelope per observation, plus one root envelope for the trace
itself, all bound into a single hash chain.

Mappable Langfuse fields:

    Trace level:
        id, name, userId, sessionId, release, version, input, output,
        metadata, tags, public, createdAt, updatedAt

    Observation level:
        id, type, name, startTime, endTime, input, output, level,
        statusMessage, model, modelParameters, usage, parentObservationId

Non-mappable-but-preserved fields go under
``subject.metadata.imported_extras``. Unknown top-level keys are
preserved by default (conservative for round-trip fidelity).
"""

from __future__ import annotations

from typing import Any

from .. import __version__
from ..envelope import GENESIS_HASH, JudgmentSigner
from .common import ImportResult, MappingReport, build_imported_envelope


LANGFUSE_SCHEMA = "phionyx.imported_langfuse_envelope.v1"
LANGFUSE_RUNTIME = "phionyx-eval-importer-langfuse"

# Foreign field name → Phionyx envelope path. The values are dotted
# strings used purely for the MappingReport — they document *where* the
# Phionyx envelope places each foreign field.
_TRACE_FIELD_MAP: dict[str, str] = {
    "id": "subject.foreign_trace_id",
    "name": "record.trace_name",
    "userId": "record.user_id",
    "sessionId": "record.session_id",
    "release": "record.release",
    "version": "record.version",
    "input": "record.input",
    "output": "record.output",
    "metadata": "record.metadata",
    "tags": "record.tags",
    "public": "record.public",
    "createdAt": "record.created_at",
    "updatedAt": "record.updated_at",
}

_OBSERVATION_FIELD_MAP: dict[str, str] = {
    "id": "record.observation_id",
    "type": "subject.event_type",
    "name": "record.observation_name",
    "startTime": "record.start_time",
    "endTime": "record.end_time",
    "input": "record.input",
    "output": "record.output",
    "level": "record.level",
    "statusMessage": "record.status_message",
    "model": "record.model",
    "modelParameters": "record.model_parameters",
    "usage": "record.usage",
    "parentObservationId": "record.parent_observation_id",
}


def _split_known_extras(
    foreign: dict[str, Any], known_keys: dict[str, str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Partition a foreign dict into mapped / preserved-extras."""
    mapped: dict[str, Any] = {}
    extras: dict[str, Any] = {}
    for key, value in foreign.items():
        if key in known_keys:
            mapped[key] = value
        else:
            extras[key] = value
    return mapped, extras


def import_langfuse_trace(
    trace: dict[str, Any],
    *,
    signer: JudgmentSigner | None = None,
) -> ImportResult:
    """Convert one Langfuse trace JSON into a Phionyx envelope chain.

    Parameters
    ----------
    trace:
        Langfuse trace dict (as returned by the Langfuse export API or
        SDK). MUST carry ``id``; SHOULD carry ``observations`` (a list of
        observation dicts). Everything else is optional.
    signer:
        Optional :class:`JudgmentSigner`. Defaults to
        :class:`HmacJudgmentSigner` for parity with the rest of
        ``phionyx_eval``.

    Returns
    -------
    ImportResult
        ``envelopes[0]`` is the trace-level root envelope; subsequent
        envelopes correspond to observations in their original order.
        Hash chain links every envelope to its predecessor.

    Raises
    ------
    ValueError
        If ``trace`` is not a dict or is missing the required ``id``.
    """
    if not isinstance(trace, dict):
        raise ValueError(
            f"langfuse trace must be a dict, got {type(trace).__name__}"
        )
    foreign_trace_id = trace.get("id")
    if not foreign_trace_id or not isinstance(foreign_trace_id, str):
        raise ValueError("langfuse trace must carry a non-empty string 'id'")

    observations: list[dict[str, Any]] = list(trace.get("observations") or [])

    mapping = MappingReport()
    envelopes: list[dict[str, Any]] = []

    # --- Root envelope (the trace itself) ---
    trace_without_obs = {k: v for k, v in trace.items() if k != "observations"}
    mapped_trace, extras_trace = _split_known_extras(
        trace_without_obs, _TRACE_FIELD_MAP
    )
    for k in mapped_trace:
        mapping.mapped_fields[f"trace.{k}"] = _TRACE_FIELD_MAP[k]
    for k in extras_trace:
        mapping.preserved_extras.append(f"trace.{k}")

    root_record: dict[str, Any] = {"trace_id": foreign_trace_id}
    for foreign_key, value in mapped_trace.items():
        if foreign_key == "id":
            continue  # already in subject.foreign_trace_id
        phionyx_path = _TRACE_FIELD_MAP[foreign_key]
        if phionyx_path.startswith("record."):
            root_record[phionyx_path[len("record.") :]] = value

    envelope = build_imported_envelope(
        schema=LANGFUSE_SCHEMA,
        importer_runtime=LANGFUSE_RUNTIME,
        importer_version=__version__,
        foreign_trace_id=foreign_trace_id,
        turn_index=0,
        event_type="trace_root",
        record=root_record,
        imported_extras=extras_trace,
        previous_hash=GENESIS_HASH,
        signer=signer,
        timestamp_utc=trace.get("updatedAt") or trace.get("createdAt"),
    )
    envelopes.append(envelope)

    # --- Observation envelopes, in original order, linked by hash chain ---
    for idx, obs in enumerate(observations, start=1):
        if not isinstance(obs, dict):
            raise ValueError(
                f"langfuse observation[{idx - 1}] must be a dict, got {type(obs).__name__}"
            )
        mapped_obs, extras_obs = _split_known_extras(obs, _OBSERVATION_FIELD_MAP)
        for k in mapped_obs:
            mapping.mapped_fields.setdefault(
                f"observation.{k}", _OBSERVATION_FIELD_MAP[k]
            )
        for k in extras_obs:
            mapping.preserved_extras.append(f"observation[{idx-1}].{k}")

        obs_record: dict[str, Any] = {}
        event_type = mapped_obs.get("type", "observation")
        for foreign_key, value in mapped_obs.items():
            phionyx_path = _OBSERVATION_FIELD_MAP[foreign_key]
            if phionyx_path.startswith("record."):
                obs_record[phionyx_path[len("record.") :]] = value
            # subject.event_type handled separately

        envelope = build_imported_envelope(
            schema=LANGFUSE_SCHEMA,
            importer_runtime=LANGFUSE_RUNTIME,
            importer_version=__version__,
            foreign_trace_id=foreign_trace_id,
            turn_index=idx,
            event_type=str(event_type),
            record=obs_record,
            imported_extras=extras_obs,
            previous_hash=envelopes[-1]["integrity"]["current"],
            signer=signer,
            timestamp_utc=mapped_obs.get("endTime") or mapped_obs.get("startTime"),
        )
        envelopes.append(envelope)

    return ImportResult(envelopes=envelopes, mapping_report=mapping)
