"""Tests for standard rubrics + Rubric model validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from phionyx_eval import (
    COMPLETENESS_RUBRIC,
    CORRECTNESS_RUBRIC,
    EVIDENCE_COVERAGE_RUBRIC,
    INDEPENDENT_VERIFIABILITY_RUBRIC,
    STANDARD_RUBRICS,
    Rubric,
)


class TestStandardRubrics:
    def test_four_standard_rubrics_published(self):
        names = [r.name for r in STANDARD_RUBRICS]
        assert names == [
            "evidence_coverage",
            "correctness",
            "completeness",
            "independent_verifiability",
        ]

    @pytest.mark.parametrize(
        "rubric",
        [
            EVIDENCE_COVERAGE_RUBRIC,
            CORRECTNESS_RUBRIC,
            COMPLETENESS_RUBRIC,
            INDEPENDENT_VERIFIABILITY_RUBRIC,
        ],
    )
    def test_each_standard_rubric_is_well_formed(self, rubric):
        assert rubric.scale_max > rubric.scale_min
        assert 0.0 <= rubric.pass_threshold <= 1.0
        assert len(rubric.criteria) >= 1
        assert len(set(rubric.criteria)) == len(rubric.criteria), "criteria must be unique"
        assert all(c.strip() for c in rubric.criteria)

    def test_pass_threshold_within_normalised_range(self):
        for rubric in STANDARD_RUBRICS:
            assert 0.0 <= rubric.pass_threshold <= 1.0


class TestRubricValidation:
    def test_scale_max_must_exceed_scale_min(self):
        with pytest.raises(ValidationError, match="scale_max"):
            Rubric(
                name="bad",
                description="bad",
                criteria=["c1"],
                scale_min=5,
                scale_max=5,
                pass_threshold=0.5,
            )

    def test_pass_threshold_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            Rubric(
                name="bad",
                description="bad",
                criteria=["c1"],
                scale_min=0,
                scale_max=5,
                pass_threshold=1.5,
            )

    def test_duplicate_criteria_rejected(self):
        with pytest.raises(ValidationError, match="unique"):
            Rubric(
                name="bad",
                description="bad",
                criteria=["c1", "c2", "c1"],
                scale_min=0,
                scale_max=5,
                pass_threshold=0.5,
            )

    def test_empty_criterion_rejected(self):
        with pytest.raises(ValidationError, match="non-empty"):
            Rubric(
                name="bad",
                description="bad",
                criteria=["c1", "  "],
                scale_min=0,
                scale_max=5,
                pass_threshold=0.5,
            )

    def test_empty_criteria_list_rejected(self):
        with pytest.raises(ValidationError):
            Rubric(
                name="bad",
                description="bad",
                criteria=[],
                scale_min=0,
                scale_max=5,
                pass_threshold=0.5,
            )

    def test_rubric_is_frozen(self):
        with pytest.raises(ValidationError):
            EVIDENCE_COVERAGE_RUBRIC.name = "renamed"  # type: ignore[misc]
