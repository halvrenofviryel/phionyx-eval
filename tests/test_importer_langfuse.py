"""F13 W3 — Langfuse importer tests.

Verifies that a Langfuse trace dict produces a well-formed Phionyx
envelope chain, with all mappable fields landing in their declared
positions and all non-mappable fields preserved under imported_extras.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from phionyx_eval import (
    GENESIS_HASH,
    LANGFUSE_SCHEMA,
    envelope_hash,
    import_langfuse_trace,
)


FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "langfuse_sample.json"


@pytest.fixture(scope="module")
def langfuse_trace() -> dict:
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope="module")
def imported(langfuse_trace):
    return import_langfuse_trace(langfuse_trace)


class TestEnvelopeShape:
    def test_one_envelope_per_observation_plus_root(self, imported):
        # 1 trace_root + 3 observations
        assert len(imported.envelopes) == 4
        assert len(imported) == 4

    def test_first_envelope_is_trace_root(self, imported):
        env = imported.envelopes[0]
        assert env["subject"]["event_type"] == "trace_root"
        assert env["subject"]["turn_index"] == 0
        assert env["schema"] == LANGFUSE_SCHEMA
        assert env["subject"]["runtime"] == "phionyx-eval-importer-langfuse"

    def test_observations_in_order(self, imported):
        events = [e["subject"]["event_type"] for e in imported.envelopes[1:]]
        assert events == ["generation", "span", "event"]
        indices = [e["subject"]["turn_index"] for e in imported.envelopes]
        assert indices == [0, 1, 2, 3]

    def test_foreign_trace_id_in_every_envelope(self, imported):
        for env in imported.envelopes:
            assert env["subject"]["foreign_trace_id"] == "trace_lf_e6a575f0a1b2c3d4"


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
    def test_trace_name_in_root_record(self, imported):
        root = imported.envelopes[0]
        assert root["record"]["trace_name"] == "Phionyx Eval Quickstart"

    def test_trace_input_output_mapped(self, imported):
        root = imported.envelopes[0]
        assert root["record"]["input"].startswith("What evidence formats")
        assert root["record"]["output"].startswith("Three evidence rows")

    def test_trace_user_session_release_version(self, imported):
        root = imported.envelopes[0]
        assert root["record"]["user_id"] == "user_42"
        assert root["record"]["session_id"] == "session_abc"
        assert root["record"]["release"] == "0.1.0a1"
        assert root["record"]["version"] == "0.1.0"

    def test_trace_extras_preserved(self, imported):
        root = imported.envelopes[0]
        extras = root["subject"]["metadata"]["imported_extras"]
        # observations are split out; project_id is non-mappable → extras
        assert "projectId_langfuse_specific" in extras
        assert extras["projectId_langfuse_specific"] == "proj_xyz"
        assert extras["bookmarked_langfuse_specific"] is True

    def test_observation_model_and_usage(self, imported):
        gen = imported.envelopes[1]  # observation[0]
        assert gen["record"]["model"] == "claude-3-5-sonnet-20241022"
        assert gen["record"]["usage"]["total"] == 570
        assert gen["record"]["model_parameters"]["temperature"] == 0.0

    def test_observation_extras_preserved(self, imported):
        gen = imported.envelopes[1]
        extras = gen["subject"]["metadata"]["imported_extras"]
        assert "promptId_langfuse_specific" in extras
        assert extras["promptId_langfuse_specific"] == "prompt_lf_abc"

    def test_observation_parent_observation_id(self, imported):
        span = imported.envelopes[2]
        assert span["record"]["parent_observation_id"] == "obs_001"

    def test_mapping_report_records_mappings(self, imported):
        report = imported.mapping_report
        assert "trace.name" in report.mapped_fields
        assert "observation.type" in report.mapped_fields
        # extras list contains observation-level extras keyed by index
        assert any(
            "promptId_langfuse_specific" in extra
            for extra in report.preserved_extras
        )


class TestInputValidation:
    def test_non_dict_input_rejected(self):
        with pytest.raises(ValueError, match="must be a dict"):
            import_langfuse_trace("not a dict")  # type: ignore[arg-type]

    def test_missing_id_rejected(self):
        with pytest.raises(ValueError, match="non-empty string 'id'"):
            import_langfuse_trace({"name": "trace_without_id"})

    def test_observation_not_dict_rejected(self):
        bad_trace = {
            "id": "trace_x",
            "observations": ["not a dict"],  # type: ignore[list-item]
        }
        with pytest.raises(ValueError, match="observation.*must be a dict"):
            import_langfuse_trace(bad_trace)

    def test_empty_observations_produces_only_root_envelope(self):
        trace = {"id": "trace_y", "name": "empty", "observations": []}
        result = import_langfuse_trace(trace)
        assert len(result) == 1
        assert result.envelopes[0]["subject"]["event_type"] == "trace_root"

    def test_missing_observations_field_produces_only_root_envelope(self):
        trace = {"id": "trace_z"}
        result = import_langfuse_trace(trace)
        assert len(result) == 1


class TestProvenance:
    def test_schema_marks_langfuse_provenance(self, imported):
        for env in imported.envelopes:
            assert env["schema"] == "phionyx.imported_langfuse_envelope.v1"
            assert "langfuse" in env["subject"]["runtime"]
