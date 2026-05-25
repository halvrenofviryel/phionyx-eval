"""F13 W3 — LangSmith importer tests.

Verifies that a LangSmith run + its descendants produces a depth-first
envelope chain, that mappable fields land in their declared positions,
and that the tree shape (parent_run_id, child_run_ids) is preserved.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from phionyx_eval import (
    GENESIS_HASH,
    LANGSMITH_SCHEMA,
    envelope_hash,
    import_langsmith_run,
)


FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "langsmith_sample.json"


@pytest.fixture(scope="module")
def langsmith_payload() -> dict:
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope="module")
def imported(langsmith_payload):
    return import_langsmith_run(
        langsmith_payload["root"],
        descendants=langsmith_payload["descendants"],
    )


class TestEnvelopeShape:
    def test_one_envelope_per_run(self, imported):
        # root + 2 children = 3
        assert len(imported) == 3

    def test_dfs_preorder(self, imported):
        ids = [e["subject"]["foreign_trace_id"] for e in imported.envelopes]
        assert ids == [
            "ls_run_root_a1b2c3d4",
            "ls_run_child_001",
            "ls_run_child_002",
        ]

    def test_run_type_in_event_type(self, imported):
        types = [e["subject"]["event_type"] for e in imported.envelopes]
        assert types == ["chain", "llm", "tool"]

    def test_schema_marks_langsmith_provenance(self, imported):
        for env in imported.envelopes:
            assert env["schema"] == LANGSMITH_SCHEMA
            assert "langsmith" in env["subject"]["runtime"]


class TestHashChain:
    def test_root_previous_is_genesis(self, imported):
        assert imported.envelopes[0]["integrity"]["previous"] == GENESIS_HASH

    def test_each_envelope_links_to_predecessor(self, imported):
        envs = imported.envelopes
        for i in range(1, len(envs)):
            assert envs[i]["integrity"]["previous"] == envs[i - 1]["integrity"]["current"]

    def test_each_hash_recomputable(self, imported):
        for env in imported.envelopes:
            hash_inputs = {k: v for k, v in env.items() if k != "integrity"}
            recomputed = envelope_hash(hash_inputs, env["integrity"]["previous"])
            assert recomputed == env["integrity"]["current"]


class TestFieldMapping:
    def test_root_inputs_outputs(self, imported):
        root = imported.envelopes[0]
        assert root["record"]["inputs"]["question"].startswith("What evidence formats")
        assert root["record"]["outputs"]["answer"].startswith("Three evidence rows")

    def test_root_child_run_ids_preserved(self, imported):
        root = imported.envelopes[0]
        assert root["record"]["child_run_ids"] == [
            "ls_run_child_001",
            "ls_run_child_002",
        ]
        assert root["record"]["parent_run_id"] is None

    def test_child_parent_run_id_preserved(self, imported):
        child = imported.envelopes[1]
        assert child["record"]["parent_run_id"] == "ls_run_root_a1b2c3d4"

    def test_root_extras_preserved(self, imported):
        root = imported.envelopes[0]
        extras = root["subject"]["metadata"]["imported_extras"]
        assert "session_id_langsmith_specific" in extras
        assert extras["session_id_langsmith_specific"] == "ls_session_xyz"
        assert "manifest_langsmith_specific" in extras

    def test_child_extras_preserved(self, imported):
        child = imported.envelopes[1]
        extras = child["subject"]["metadata"]["imported_extras"]
        assert "private_token_count_langsmith_specific" in extras

    def test_events_and_feedback_mapped(self, imported):
        tool_run = imported.envelopes[2]
        assert tool_run["record"]["events"][0]["name"] == "validation_passed"
        assert tool_run["record"]["feedback"][0]["score"] == 0.9

    def test_mapping_report_records_mappings(self, imported):
        report = imported.mapping_report
        assert "root.name" in report.mapped_fields
        assert "root.run_type" in report.mapped_fields


class TestInputValidation:
    def test_non_dict_run_rejected(self):
        with pytest.raises(ValueError, match="must be a dict"):
            import_langsmith_run("not a dict")  # type: ignore[arg-type]

    def test_missing_id_rejected(self):
        with pytest.raises(ValueError, match="non-empty string 'id'"):
            import_langsmith_run({"name": "no_id"})

    def test_descendant_not_dict_rejected(self):
        with pytest.raises(ValueError, match="descendant must be a dict"):
            import_langsmith_run(
                {"id": "run_x"},
                descendants=["not a dict"],  # type: ignore[arg-type, list-item]
            )

    def test_descendant_missing_id_rejected(self):
        with pytest.raises(ValueError, match="descendant must carry"):
            import_langsmith_run(
                {"id": "run_x"},
                descendants=[{"name": "no_id"}],
            )

    def test_no_descendants_produces_only_root(self):
        result = import_langsmith_run({"id": "run_alone", "name": "solo", "run_type": "chain"})
        assert len(result) == 1
        assert result.envelopes[0]["subject"]["foreign_trace_id"] == "run_alone"

    def test_missing_descendant_in_child_run_ids_skipped_silently(self):
        """Real LangSmith exports occasionally truncate sub-trees;
        the importer must not crash when child_run_ids points to a
        run that isn't in the descendants list."""
        result = import_langsmith_run(
            {
                "id": "run_root",
                "run_type": "chain",
                "child_run_ids": ["missing_child"],
            },
            descendants=[],
        )
        assert len(result) == 1  # only root


class TestRoundTripIntegrity:
    def test_re_importing_same_input_gives_same_envelope_count(self, langsmith_payload):
        a = import_langsmith_run(
            langsmith_payload["root"],
            descendants=langsmith_payload["descendants"],
        )
        b = import_langsmith_run(
            langsmith_payload["root"],
            descendants=langsmith_payload["descendants"],
        )
        assert len(a) == len(b) == 3
        # Same record payloads (the timestamp_utc inside subject is
        # taken from the foreign data so it is deterministic too).
        for ea, eb in zip(a.envelopes, b.envelopes):
            assert ea["record"] == eb["record"]
            assert ea["subject"]["foreign_trace_id"] == eb["subject"]["foreign_trace_id"]
            assert ea["subject"]["timestamp_utc"] == eb["subject"]["timestamp_utc"]
