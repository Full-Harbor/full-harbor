"""
Tests for canonical_qa.py — issue #22
"""
import pytest
from src.evaluation.canonical_qa import (
    CANONICAL_QA,
    CANONICAL_QA_BY_ID,
    LYC_QA, HYC_QA, TCYC_QA,
    Club, Category, Difficulty,
)


class TestCanonicalQASet:
    def test_minimum_count(self):
        """Must have at least 40 questions across all clubs (issue #22 requires 40)."""
        assert len(CANONICAL_QA) >= 40, f"Only {len(CANONICAL_QA)} QAs, need ≥40"

    def test_all_clubs_represented(self):
        clubs = {qa.club for qa in CANONICAL_QA}
        assert Club.HYC in clubs
        assert Club.LYC in clubs
        assert Club.TCYC in clubs

    def test_all_ids_unique(self):
        ids = [qa.id for qa in CANONICAL_QA]
        assert len(ids) == len(set(ids)), "Duplicate QA IDs found"

    def test_id_format(self):
        """IDs should follow pattern: {club}-{category_prefix}-{num}"""
        for qa in CANONICAL_QA:
            parts = qa.id.split("-")
            assert len(parts) >= 3, f"Malformed ID: {qa.id}"
            assert parts[0] in [c.value for c in Club], f"Bad club in ID: {qa.id}"

    def test_all_clubs_have_governance_questions(self):
        """Each club needs at least one governance (990-based) question."""
        for club in Club:
            gov_qs = [qa for qa in CANONICAL_QA
                      if qa.club == club and qa.category == Category.GOVERNANCE]
            assert len(gov_qs) >= 1, f"{club.value} has no governance questions"

    def test_all_clubs_have_cost_questions(self):
        for club in Club:
            cost_qs = [qa for qa in CANONICAL_QA
                       if qa.club == club and qa.category == Category.COST]
            assert len(cost_qs) >= 1, f"{club.value} has no cost questions"

    def test_difficulty_distribution(self):
        """Should have questions across all three difficulty levels."""
        diffs = {qa.difficulty for qa in CANONICAL_QA}
        assert Difficulty.EASY in diffs
        assert Difficulty.MEDIUM in diffs
        assert Difficulty.HARD in diffs

    def test_source_types(self):
        """Sources should be URLs, 990 references, or 'not-disclosed'."""
        for qa in CANONICAL_QA:
            assert qa.source, f"{qa.id} has empty source"
            valid = (
                qa.source.startswith("http")
                or qa.source.startswith("990-")
                or qa.source == "not-disclosed"
            )
            assert valid, f"{qa.id} has unexpected source format: {qa.source}"

    def test_audit_question_ids_valid(self):
        """audit_question_id, if set, must be 1-20."""
        for qa in CANONICAL_QA:
            if qa.audit_question_id is not None:
                assert 1 <= qa.audit_question_id <= 20, \
                    f"{qa.id} has audit_question_id={qa.audit_question_id} outside 1-20"

    def test_expected_answers_non_empty(self):
        for qa in CANONICAL_QA:
            assert qa.expected_answer.strip(), f"{qa.id} has empty expected_answer"

    def test_questions_non_empty(self):
        for qa in CANONICAL_QA:
            assert qa.question.strip(), f"{qa.id} has empty question"

    def test_lookup_by_id(self):
        qa = CANONICAL_QA_BY_ID.get("lyc-cost-001")
        assert qa is not None
        assert qa.club == Club.LYC
        assert qa.category == Category.COST

    def test_hard_questions_have_990_sources(self):
        """Hard questions should reference 990 data or 'not-disclosed'."""
        hard_qs = [qa for qa in CANONICAL_QA if qa.difficulty == Difficulty.HARD]
        for qa in hard_qs:
            valid = qa.source.startswith("990-") or qa.source == "not-disclosed"
            assert valid, f"Hard question {qa.id} has unexpected source: {qa.source}"

    def test_lyc_has_most_questions(self):
        """LYC is the primary test club — should have the most questions."""
        lyc_count = len(LYC_QA)
        hyc_count = len(HYC_QA)
        tcyc_count = len(TCYC_QA)
        assert lyc_count >= hyc_count, "LYC should have ≥ HYC questions"
