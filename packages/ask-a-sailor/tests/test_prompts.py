"""
Tests for ABA-informed prompt modes and Social Stories schema.
==============================================================
Verifies:
  1. Coach and Reflect prompts exist and are distinct from each other.
  2. Boundary-hygiene language is present in both ABA-informed prompts.
  3. Persona keywords differentiate Coach (in-the-moment) from Reflect
     (post-session metacognitive).
  4. SocialStory Pydantic model validates required fields and enums.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from prompts.system import (
    SYSTEM_PROMPT,
    COACH_SYSTEM_PROMPT,
    REFLECT_SYSTEM_PROMPT,
    PARENT_QUESTION_CATEGORIES,
    _BOUNDARY_BLOCK,
)
from prompts.social_stories import (
    SocialStory,
    TonePreset,
    DisclosureIntent,
)


# ---------------------------------------------------------------------------
# Prompt existence and distinctness
# ---------------------------------------------------------------------------

class TestPromptModes:
    """Coach and Reflect are distinct, non-empty prompts."""

    def test_coach_prompt_is_non_empty(self):
        assert len(COACH_SYSTEM_PROMPT.strip()) > 0

    def test_reflect_prompt_is_non_empty(self):
        assert len(REFLECT_SYSTEM_PROMPT.strip()) > 0

    def test_default_prompt_unchanged(self):
        """Original SYSTEM_PROMPT still contains core 'Ask a Sailor' identity."""
        assert "Ask a Sailor" in SYSTEM_PROMPT

    def test_coach_and_reflect_are_different(self):
        assert COACH_SYSTEM_PROMPT != REFLECT_SYSTEM_PROMPT

    def test_coach_differs_from_default(self):
        assert COACH_SYSTEM_PROMPT != SYSTEM_PROMPT

    def test_reflect_differs_from_default(self):
        assert REFLECT_SYSTEM_PROMPT != SYSTEM_PROMPT

    def test_parent_question_categories_still_present(self):
        assert len(PARENT_QUESTION_CATEGORIES) >= 16


# ---------------------------------------------------------------------------
# Boundary hygiene — both ABA prompts must decline diagnosis
# ---------------------------------------------------------------------------

BOUNDARY_REQUIRED_PHRASES = [
    "not a licensed therapist",
    "never diagnose",
    "qualified professional",
    "BCBA",
]


class TestBoundaryHygiene:
    """Both ABA-informed prompts carry explicit clinical-boundary language."""

    @pytest.mark.parametrize("phrase", BOUNDARY_REQUIRED_PHRASES)
    def test_coach_contains_boundary_phrase(self, phrase):
        assert phrase.lower() in COACH_SYSTEM_PROMPT.lower(), (
            f"Coach prompt missing boundary phrase: '{phrase}'"
        )

    @pytest.mark.parametrize("phrase", BOUNDARY_REQUIRED_PHRASES)
    def test_reflect_contains_boundary_phrase(self, phrase):
        assert phrase.lower() in REFLECT_SYSTEM_PROMPT.lower(), (
            f"Reflect prompt missing boundary phrase: '{phrase}'"
        )

    def test_boundary_block_shared(self):
        """Both prompts should embed the same shared boundary block."""
        assert _BOUNDARY_BLOCK in COACH_SYSTEM_PROMPT
        assert _BOUNDARY_BLOCK in REFLECT_SYSTEM_PROMPT

    def test_default_prompt_no_boundary_block(self):
        """Original RAG prompt should NOT contain the clinical boundary block."""
        assert _BOUNDARY_BLOCK not in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Persona keyword differentiation
# ---------------------------------------------------------------------------

COACH_KEYWORDS = [
    "in-the-moment",
    "actionable",
    "positive-reinforcement",
    "sensory",
]

REFLECT_KEYWORDS = [
    "metacognitive",
    "look back",
    "self-awareness",
    "validating",
]


class TestPersonaDifferentiation:
    """Coach and Reflect carry persona-specific language."""

    @pytest.mark.parametrize("keyword", COACH_KEYWORDS)
    def test_coach_has_persona_keyword(self, keyword):
        assert keyword.lower() in COACH_SYSTEM_PROMPT.lower(), (
            f"Coach prompt missing persona keyword: '{keyword}'"
        )

    @pytest.mark.parametrize("keyword", REFLECT_KEYWORDS)
    def test_reflect_has_persona_keyword(self, keyword):
        assert keyword.lower() in REFLECT_SYSTEM_PROMPT.lower(), (
            f"Reflect prompt missing persona keyword: '{keyword}'"
        )


# ---------------------------------------------------------------------------
# Social Stories schema validation
# ---------------------------------------------------------------------------

class TestSocialStorySchema:
    """SocialStory Pydantic model validates correctly."""

    def test_valid_minimal_story(self):
        story = SocialStory(
            setting="Lakewood Yacht Club dock, Saturday morning",
            roles=["sailor (child)", "instructor"],
            objective="Preview the steps for rigging an Opti",
        )
        assert story.tone_preset == TonePreset.calm
        assert story.disclosure_intent == DisclosureIntent.none
        assert story.sensory_profile is None

    def test_valid_full_story(self):
        story = SocialStory(
            setting="Houston Yacht Club, regatta day",
            roles=["sailor (child)", "parent", "race committee"],
            objective="Know what happens during a start sequence",
            sensory_profile="Loud horn, wind, crowded dock",
            tone_preset=TonePreset.encouraging,
            disclosure_intent=DisclosureIntent.normalising,
        )
        assert story.setting == "Houston Yacht Club, regatta day"
        assert len(story.roles) == 3
        assert story.sensory_profile == "Loud horn, wind, crowded dock"
        assert story.tone_preset == TonePreset.encouraging
        assert story.disclosure_intent == DisclosureIntent.normalising

    def test_missing_required_setting_raises(self):
        with pytest.raises(Exception):
            SocialStory(
                roles=["sailor"],
                objective="Preview dock walk",
            )

    def test_missing_required_roles_raises(self):
        with pytest.raises(Exception):
            SocialStory(
                setting="Dock",
                objective="Preview dock walk",
            )

    def test_missing_required_objective_raises(self):
        with pytest.raises(Exception):
            SocialStory(
                setting="Dock",
                roles=["sailor"],
            )

    def test_empty_roles_list_raises(self):
        with pytest.raises(Exception):
            SocialStory(
                setting="Dock",
                roles=[],
                objective="Preview dock walk",
            )

    def test_empty_setting_raises(self):
        with pytest.raises(Exception):
            SocialStory(
                setting="",
                roles=["sailor"],
                objective="Preview dock walk",
            )

    def test_tone_preset_values(self):
        assert set(TonePreset) == {
            TonePreset.calm,
            TonePreset.encouraging,
            TonePreset.matter_of_fact,
            TonePreset.playful,
        }

    def test_disclosure_intent_values(self):
        assert set(DisclosureIntent) == {
            DisclosureIntent.none,
            DisclosureIntent.normalising,
            DisclosureIntent.explicit,
        }

    def test_story_serialisation_roundtrip(self):
        story = SocialStory(
            setting="TCYC classroom",
            roles=["sailor (child)"],
            objective="Understand capsize recovery steps",
            sensory_profile="Cold water, loud splash",
            tone_preset=TonePreset.matter_of_fact,
            disclosure_intent=DisclosureIntent.explicit,
        )
        data = story.model_dump()
        restored = SocialStory(**data)
        assert restored == story
