"""
Social Stories — Corpus Schema
==============================
Pydantic model for ABA-informed Social Stories used by the Coach and
Reflect prompt modes.

A Social Story is a short narrative that describes a situation, skill,
or concept using a specific format.  These are used with youth sailors
— especially neurodivergent youth — to preview upcoming activities,
process past experiences, and reduce anxiety around transitions.

Schema fields follow the issue specification:
  setting, roles, objective, sensory_profile, tone_preset,
  disclosure_intent

References:
  - Carol Gray's Social Stories™ criteria (2015)
  - ASD-iLLM (Lai et al., EMNLP 2025)
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TonePreset(str, Enum):
    """Pre-defined tone options for Social Story narration."""

    calm = "calm"
    encouraging = "encouraging"
    matter_of_fact = "matter-of-fact"
    playful = "playful"


class DisclosureIntent(str, Enum):
    """How openly the story addresses neurodivergence or disability."""

    none = "none"                # No mention of diagnosis/neurodivergence
    normalising = "normalising"  # Frames differences as normal variation
    explicit = "explicit"        # Directly names the condition (only if family consents)


class SocialStory(BaseModel):
    """Schema for a single Social Story in the Ask a Sailor corpus.

    Example
    -------
    >>> story = SocialStory(
    ...     setting="Lakewood Yacht Club boat ramp, Saturday morning",
    ...     roles=["sailor (child)", "instructor", "dock volunteer"],
    ...     objective="Preview the steps for launching an Opti from the dock",
    ...     sensory_profile="Loud halyards, wind, cold spray, life-jacket pressure",
    ...     tone_preset=TonePreset.calm,
    ...     disclosure_intent=DisclosureIntent.normalising,
    ... )
    """

    setting: str = Field(
        ...,
        min_length=1,
        description=(
            "Where and when the story takes place "
            "(e.g., 'Houston Yacht Club dock, first day of camp')."
        ),
    )

    roles: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "People involved in the story "
            "(e.g., ['sailor (child)', 'instructor', 'parent'])."
        ),
    )

    objective: str = Field(
        ...,
        min_length=1,
        description=(
            "What the story aims to help the reader understand or do "
            "(e.g., 'Know what to expect during capsize drill')."
        ),
    )

    sensory_profile: Optional[str] = Field(
        default=None,
        description=(
            "Sensory elements the reader may encounter "
            "(e.g., 'Loud horn, cold water splash, rocking motion')."
        ),
    )

    tone_preset: TonePreset = Field(
        default=TonePreset.calm,
        description="Narrative tone for the generated story.",
    )

    disclosure_intent: DisclosureIntent = Field(
        default=DisclosureIntent.none,
        description=(
            "Level of neurodivergence disclosure. "
            "Use 'explicit' ONLY with prior family consent."
        ),
    )
