"""LangSmith run → Phionyx envelope chain.

LangSmith runs are tree-shaped: each run has ``parent_run_id`` and
``child_run_ids``. The importer flattens a run-and-its-descendants tree
into a single linear envelope chain in depth-first pre-order, so each
envelope's ``parent_envelope_hash`` (= ``integrity.previous``) gives a
linear traversal a verifier can walk without traversing the foreign
tree shape.

Mappable LangSmith fields per run:

    id, name, run_type, inputs, outputs, start_time, end_time, error,
    extra, parent_run_id, child_run_ids, events, feedback

Tree shape (parent_run_id / child_run_ids) is preserved in
``record.parent_run_id`` so a downstream consumer that wants to
reconstruct the tree can.
"""

from __future__ import annotations

from typing import Any, Iterator

from .. import __version__
from ..envelope import GENESIS_HASH, JudgmentSigner
from .common import ImportResult, MappingReport, build_imported_envelope


LANGSMITH_SCHEMA = "phionyx.imported_langsmith_envelope.v1"
LANGSMITH_RUNTIME = "phionyx-eval-importer-langsmith"

_RUN_FIELD_MAP: dict[str, str] = {
    "id": "subject.foreign_trace_id",
    "name": "record.run_name",
    "run_type": "subject.event_type",
    "inputs": "record.inputs",
    "outputs": "record.outputs",
    "start_time": "record.start_time",
    "end_time": "record.end_time",
    "error": "record.error",
    "extra": "record.extra",
    "parent_run_id": "record.parent_run_id",
    "child_run_ids": "record.child_run_ids",
    "events": "record.events",
    "feedback": "record.feedback",
}


def _split_known_extras(
    foreign: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    mapped: dict[str, Any] = {}
    extras: dict[str, Any] = {}
    for key, value in foreign.items():
        if key in _RUN_FIELD_MAP:
            mapped[key] = value
        else:
            extras[key] = value
    return mapped, extras


def _depth_first_flatten(
    run: dict[str, Any],
    child_runs_by_id: dict[str, dict[str, Any]],
) -> Iterator[dict[str, Any]]:
    """Yield the run and its descendants in DFS pre-order.

    Walks ``child_run_ids`` and resolves each ID to a dict via the
    supplied lookup. Missing children are skipped silently (real
    LangSmith exports occasionally truncate sub-trees)."""
    yield run
    for cid in run.get("child_run_ids") or []:
        child = child_runs_by_id.get(cid)
        if child is None:
            continue
        yield from _depth_first_flatten(child, child_runs_by_id)


def import_langsmith_run(
    run: dict[str, Any],
    *,
    descendants: list[dict[str, Any]] | None = None,
    signer: JudgmentSigner | None = None,
) -> ImportResult:
    """Convert one LangSmith run-tree into a Phionyx envelope chain.

    Parameters
    ----------
    run:
        Root LangSmith run dict. MUST carry ``id``. SHOULD carry
        ``child_run_ids`` (a list of LangSmith run UUIDs).
    descendants:
        Optional list of additional LangSmith run dicts (descendant runs).
        Each must carry its own ``id``. The importer resolves
        ``child_run_ids`` against this list to walk the run tree. If
        omitted, only the root run is imported.
    signer:
        Optional :class:`JudgmentSigner`.

    Returns
    -------
    ImportResult
        Envelopes in depth-first pre-order. The root run becomes
        envelope[0]; each descendant becomes a subsequent envelope
        linked by hash chain.

    Raises
    ------
    ValueError
        If ``run`` is not a dict or is missing the required ``id``.
    """
    if not isinstance(run, dict):
        raise ValueError(
            f"langsmith run must be a dict, got {type(run).__name__}"
        )
    foreign_trace_id = run.get("id")
    if not foreign_trace_id or not isinstance(foreign_trace_id, str):
        raise ValueError("langsmith run must carry a non-empty string 'id'")

    child_runs_by_id: dict[str, dict[str, Any]] = {}
    for d in descendants or []:
        if not isinstance(d, dict):
            raise ValueError(
                f"langsmith descendant must be a dict, got {type(d).__name__}"
            )
        d_id = d.get("id")
        if not d_id or not isinstance(d_id, str):
            raise ValueError("langsmith descendant must carry a non-empty string 'id'")
        child_runs_by_id[d_id] = d

    mapping = MappingReport()
    envelopes: list[dict[str, Any]] = []

    previous_hash = GENESIS_HASH
    for idx, current_run in enumerate(
        _depth_first_flatten(run, child_runs_by_id)
    ):
        mapped, extras = _split_known_extras(current_run)
        path_prefix = "root" if idx == 0 else f"descendant[{idx-1}]"
        for k in mapped:
            mapping.mapped_fields.setdefault(
                f"{path_prefix}.{k}", _RUN_FIELD_MAP[k]
            )
        for k in extras:
            mapping.preserved_extras.append(f"{path_prefix}.{k}")

        record: dict[str, Any] = {}
        event_type = mapped.get("run_type", "run")
        for foreign_key, value in mapped.items():
            phionyx_path = _RUN_FIELD_MAP[foreign_key]
            if phionyx_path.startswith("record."):
                record[phionyx_path[len("record.") :]] = value

        envelope = build_imported_envelope(
            schema=LANGSMITH_SCHEMA,
            importer_runtime=LANGSMITH_RUNTIME,
            importer_version=__version__,
            foreign_trace_id=str(current_run["id"]),
            turn_index=idx,
            event_type=str(event_type),
            record=record,
            imported_extras=extras,
            previous_hash=previous_hash,
            signer=signer,
            timestamp_utc=mapped.get("end_time") or mapped.get("start_time"),
        )
        envelopes.append(envelope)
        previous_hash = envelope["integrity"]["current"]

    return ImportResult(envelopes=envelopes, mapping_report=mapping)
