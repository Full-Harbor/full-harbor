"""
Test suite for Ask a Sailor — Newsletter Corpus Loader.
Tests section-type detection, date extraction, section splitting,
file loading, and deduplication.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Allow importing from the package src directory
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ingestion.newsletter_loader import (
    NewsletterLoader,
    NewsletterSection,
    detect_section_type,
    extract_issue_metadata,
    split_into_sections,
    SAMPLE_LYC_NEWSLETTER,
)

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "newsletters"


# ---------------------------------------------------------------------------
# 1. Section type detection — youth
# ---------------------------------------------------------------------------

def test_detect_section_type_youth():
    assert detect_section_type("Junior Sailing News", "Opti camp registration opens April 1.") == "youth"


# ---------------------------------------------------------------------------
# 2. Section type detection — racing
# ---------------------------------------------------------------------------

def test_detect_section_type_racing():
    assert detect_section_type("Racing Results", "PHRF A Fleet results for September series.") == "racing"


# ---------------------------------------------------------------------------
# 3. Section type detection — helm
# ---------------------------------------------------------------------------

def test_detect_section_type_helm():
    assert detect_section_type("From the Helm", "Commodore message for members.") == "helm"


# ---------------------------------------------------------------------------
# 4. Section type detection — events
# ---------------------------------------------------------------------------

def test_detect_section_type_events():
    assert detect_section_type("Upcoming Events", "October club calendar: awards dinner, cookout.") == "events"


# ---------------------------------------------------------------------------
# 5. Section type detection — member
# ---------------------------------------------------------------------------

def test_detect_section_type_member():
    assert detect_section_type("Member News", "Welcome to new members joining this fall.") == "member"


# ---------------------------------------------------------------------------
# 6. extract_issue_metadata — finds month-year date
# ---------------------------------------------------------------------------

def test_extract_issue_metadata_date():
    text = "SEAHORSE NEWSLETTER\nVolume 41, Issue 3 | March 2024\n\nContent here."
    meta = extract_issue_metadata(text)
    assert "issue_date" in meta
    assert "2024" in meta["issue_date"]


# ---------------------------------------------------------------------------
# 7. extract_issue_metadata — finds volume/issue
# ---------------------------------------------------------------------------

def test_extract_issue_metadata_volume():
    text = "SEAHORSE NEWSLETTER\nVolume 42, Issue 9 | September 2025\n\nContent."
    meta = extract_issue_metadata(text)
    assert "volume" in meta
    assert "42" in meta["volume"]


# ---------------------------------------------------------------------------
# 8. split_into_sections — header-based splitting returns multiple sections
# ---------------------------------------------------------------------------

def test_split_into_sections_header_based():
    sections = split_into_sections(SAMPLE_LYC_NEWSLETTER, "seahorse-2025-09", "lyc")
    assert len(sections) >= 3, f"Expected ≥3 sections, got {len(sections)}"
    types = {s.section_type for s in sections}
    # The sample newsletter has youth, racing, events, helm sections
    assert len(types) >= 2, f"Expected multiple section types, got {types}"


# ---------------------------------------------------------------------------
# 9. split_into_sections — paragraph fallback when no headers
# ---------------------------------------------------------------------------

def test_split_into_sections_paragraph_fallback():
    plain = (
        "This is the first paragraph with enough words to pass the minimum word count "
        "threshold so that it is not filtered out by the chunker code path.\n\n"
        "This is the second paragraph with enough words to pass the minimum word count "
        "threshold so that it is not filtered out by the chunker code path.\n\n"
        "Third paragraph adds more content to trigger the 200-word buffer flush in "
        "the paragraph-based chunking path of split_into_sections function here.\n\n"
        "Fourth paragraph adds even more content to ensure we get at least one chunk "
        "flushed during iteration and one remaining in the buffer at the end."
    )
    sections = split_into_sections(plain, "plain-issue", "lyc")
    assert len(sections) >= 1


# ---------------------------------------------------------------------------
# 10. NewsletterSection.to_chunk — correct chunk format
# ---------------------------------------------------------------------------

def test_newsletter_section_to_chunk():
    section = NewsletterSection(
        section_id="abc123",
        club_slug="lyc",
        issue_name="seahorse-2025-09",
        issue_date="September 2025",
        volume="Volume 42, Issue 9",
        section_type="youth",
        section_title="Junior Sailing News",
        content="The opti fleet has 23 sailors this fall.",
    )
    chunk = section.to_chunk()
    assert chunk["chunk_id"] == "abc123"
    assert chunk["source_type"] == "newsletter"
    assert chunk["club_slug"] == "lyc"
    assert "youth" in chunk["metadata"]["section_type"]
    assert "Junior Sailing News" in chunk["text"]


# ---------------------------------------------------------------------------
# 11. NewsletterLoader.load_file — loads fixture file and returns chunks
# ---------------------------------------------------------------------------

def test_loader_load_file():
    fixture_file = FIXTURES_DIR / "lyc" / "seahorse-2024-03.txt"
    assert fixture_file.exists(), f"Fixture not found: {fixture_file}"
    loader = NewsletterLoader(FIXTURES_DIR, "lyc")
    chunks = loader.load_file(fixture_file)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert "text" in chunk
        assert "doc_id" in chunk
        assert chunk["source_type"] == "newsletter"


# ---------------------------------------------------------------------------
# 12. NewsletterLoader.load_all — loads all fixture files
# ---------------------------------------------------------------------------

def test_loader_load_all():
    loader = NewsletterLoader(FIXTURES_DIR, "lyc")
    chunks = loader.load_all()
    assert len(chunks) >= 4  # ≥2 sections per file × 2 fixture files
    doc_ids = {c["doc_id"] for c in chunks}
    # Two different issues → two different doc_ids
    assert len(doc_ids) >= 2


# ---------------------------------------------------------------------------
# 13. Deduplication — running save_to_corpus twice produces no duplicate chunks
# ---------------------------------------------------------------------------

def test_no_duplicates_on_double_save(tmp_path):
    loader = NewsletterLoader(FIXTURES_DIR, "lyc")

    # First save
    loader.save_to_corpus(tmp_path)
    # Second save — should skip already-written issues
    loader.save_to_corpus(tmp_path)

    out_file = tmp_path / "lyc" / "newsletters.jsonl"
    assert out_file.exists()

    lines = [l.strip() for l in out_file.read_text().splitlines() if l.strip()]
    chunk_ids = [json.loads(l)["chunk_id"] for l in lines]
    assert len(chunk_ids) == len(set(chunk_ids)), "Duplicate chunk_ids found after double save"


# ---------------------------------------------------------------------------
# 14. Section detection accuracy — ≥80% of sample newsletter sections correct
# ---------------------------------------------------------------------------

def test_section_type_detection_accuracy():
    """
    Run the SAMPLE newsletter through the loader and check that the majority
    of sections are classified into a known non-general type.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        club_dir = Path(tmpdir) / "lyc"
        club_dir.mkdir()
        sample_file = club_dir / "seahorse-2025-09.txt"
        sample_file.write_text(SAMPLE_LYC_NEWSLETTER)

        loader = NewsletterLoader(Path(tmpdir), "lyc")
        chunks = loader.load_all()

    non_general = sum(
        1 for c in chunks if c["metadata"].get("section_type") != "general"
    )
    ratio = non_general / len(chunks) if chunks else 0
    assert ratio >= 0.8, (
        f"Only {non_general}/{len(chunks)} sections classified as non-general "
        f"({ratio:.0%}); expected ≥80%"
    )


# ---------------------------------------------------------------------------
# 15. Missing directory — loader returns empty list gracefully
# ---------------------------------------------------------------------------

def test_loader_missing_directory(tmp_path):
    loader = NewsletterLoader(tmp_path / "nonexistent", "lyc")
    chunks = loader.load_all()
    assert chunks == []
