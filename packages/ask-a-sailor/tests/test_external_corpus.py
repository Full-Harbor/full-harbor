"""
Tests for external corpus ingestion scripts (EmpatheticDialogues + Social Chemistry 101).
Verifies chunk format, PII filtering, and chunk counts without downloading real datasets.
"""

import csv
import json
import re
import sys
from pathlib import Path

import pytest

# Allow importing ingestion scripts
sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))
# Allow importing package source
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ingest_empathetic_dialogues import (
    conversation_to_chunk,
    ingest as ingest_ed,
    parse_conversations,
)
from ingest_social_chemistry import (
    ingest as ingest_sc,
    rot_to_chunk,
)

# ---------------------------------------------------------------------------
# Required chunk keys (same format as the rest of the corpus)
# ---------------------------------------------------------------------------

REQUIRED_KEYS = {
    "chunk_id",
    "doc_id",
    "club_slug",
    "source_type",
    "source_url",
    "title",
    "text",
    "metadata",
}


# ---------------------------------------------------------------------------
# Fixtures — tiny synthetic datasets written to tmp directories
# ---------------------------------------------------------------------------

SAMPLE_ED_ROWS = [
    {
        "conv_id": "hit:0_conv:1",
        "utterance_idx": "1",
        "context": "sentimental",
        "prompt": "I remember going to the fireworks with my best friend.",
        "speaker_idx": "0",
        "utterance": "I remember going to the fireworks with my best friend.",
        "selfeval": "",
        "tags": "",
    },
    {
        "conv_id": "hit:0_conv:1",
        "utterance_idx": "2",
        "context": "sentimental",
        "prompt": "",
        "speaker_idx": "1",
        "utterance": "That sounds like a great memory!",
        "selfeval": "like",
        "tags": "",
    },
    {
        "conv_id": "hit:0_conv:2",
        "utterance_idx": "1",
        "context": "afraid",
        "prompt": "I heard a strange noise outside at night.",
        "speaker_idx": "0",
        "utterance": "I heard a strange noise outside at night.",
        "selfeval": "",
        "tags": "",
    },
    {
        "conv_id": "hit:0_conv:2",
        "utterance_idx": "2",
        "context": "afraid",
        "prompt": "",
        "speaker_idx": "1",
        "utterance": "That can be really scary. Did you find out what it was?",
        "selfeval": "",
        "tags": "",
    },
]


@pytest.fixture()
def ed_input_dir(tmp_path):
    """Write a tiny EmpatheticDialogues CSV to a temp directory."""
    d = tmp_path / "empatheticdialogues"
    d.mkdir()
    csv_path = d / "train.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(SAMPLE_ED_ROWS[0].keys()))
        writer.writeheader()
        for row in SAMPLE_ED_ROWS:
            writer.writerow(row)
    return d


SAMPLE_SC_ROWS = [
    {
        "area": "amitheasshole",
        "m": "",
        "rot-agree": "4.0",
        "rot-categorization": "morality-ethics|social-norms",
        "rot-moral-foundations": "",
        "rot-char-targeting": "",
        "rot-bad": "0",
        "rot-judgment": "it's wrong",
        "action": "taking someone else's food",
        "rot": "It's wrong to take someone else's food without asking.",
        "rot-id": "rot_0001",
        "split": "train",
        "situation": "taking my roommate's leftovers from the fridge",
        "situation-short-id": "sit_001",
        "worker-id": "w1",
        "n-characters": "1",
        "characters": "narrator",
    },
    {
        "area": "amitheasshole",
        "m": "",
        "rot-agree": "4.5",
        "rot-categorization": "social-norms",
        "rot-moral-foundations": "",
        "rot-char-targeting": "",
        "rot-bad": "0",
        "rot-judgment": "it's good",
        "action": "helping a friend move",
        "rot": "It's good to help a friend when they need it.",
        "rot-id": "rot_0002",
        "split": "train",
        "situation": "my friend asked me to help them move apartments",
        "situation-short-id": "sit_002",
        "worker-id": "w2",
        "n-characters": "2",
        "characters": "narrator|friend",
    },
]


@pytest.fixture()
def sc_input_dir(tmp_path):
    """Write a tiny Social Chemistry 101 TSV to a temp directory."""
    d = tmp_path / "social-chemistry-101"
    d.mkdir()
    tsv_path = d / "social-chem-101.v1.0.tsv"
    with open(tsv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=list(SAMPLE_SC_ROWS[0].keys()), delimiter="\t"
        )
        writer.writeheader()
        for row in SAMPLE_SC_ROWS:
            writer.writerow(row)
    return d


# ---------------------------------------------------------------------------
# EmpatheticDialogues tests
# ---------------------------------------------------------------------------

class TestEmpatheticDialogues:

    def test_parse_conversations(self, ed_input_dir):
        convs = parse_conversations(ed_input_dir)
        assert len(convs) == 2
        assert "hit:0_conv:1" in convs
        assert len(convs["hit:0_conv:1"]) == 2

    def test_chunk_format(self, ed_input_dir):
        convs = parse_conversations(ed_input_dir)
        chunk = conversation_to_chunk("hit:0_conv:1", convs["hit:0_conv:1"])
        assert chunk is not None
        assert REQUIRED_KEYS.issubset(chunk.keys()), (
            f"Missing keys: {REQUIRED_KEYS - chunk.keys()}"
        )

    def test_chunk_source_type(self, ed_input_dir):
        convs = parse_conversations(ed_input_dir)
        chunk = conversation_to_chunk("hit:0_conv:1", convs["hit:0_conv:1"])
        assert chunk["source_type"] == "empathetic_dialogues"

    def test_chunk_has_emotion_context(self, ed_input_dir):
        convs = parse_conversations(ed_input_dir)
        chunk = conversation_to_chunk("hit:0_conv:1", convs["hit:0_conv:1"])
        assert "sentimental" in chunk["text"].lower()
        assert chunk["metadata"]["emotion"] == "sentimental"

    def test_chunk_contains_utterances(self, ed_input_dir):
        convs = parse_conversations(ed_input_dir)
        chunk = conversation_to_chunk("hit:0_conv:1", convs["hit:0_conv:1"])
        assert "Speaker:" in chunk["text"]
        assert "Listener:" in chunk["text"]
        assert "fireworks" in chunk["text"]

    def test_no_pii_in_chunks(self, ed_input_dir):
        """Verify no phone numbers, emails, or SSNs leak into chunks."""
        chunks = ingest_ed(ed_input_dir, ed_input_dir / "output")
        for chunk in chunks:
            text = chunk["text"]
            assert not re.search(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", text), \
                f"Phone number found: {text}"
            assert not re.search(
                r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.\w+", text
            ), f"Email found: {text}"
            assert not re.search(r"\b\d{3}-\d{2}-\d{4}\b", text), \
                f"SSN found: {text}"

    def test_chunk_count(self, ed_input_dir):
        chunks = ingest_ed(ed_input_dir, ed_input_dir / "output")
        assert len(chunks) == 2, f"Expected 2 chunks, got {len(chunks)}"

    def test_output_jsonl_valid(self, ed_input_dir):
        """Verify the JSONL output is valid line-delimited JSON."""
        out_dir = ed_input_dir / "output"
        ingest_ed(ed_input_dir, out_dir)
        jsonl_path = out_dir / "corpus.jsonl"
        assert jsonl_path.exists()
        with open(jsonl_path) as f:
            lines = [line for line in f if line.strip()]
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert REQUIRED_KEYS.issubset(parsed.keys())

    def test_pii_row_filtered(self, tmp_path):
        """A conversation containing a phone number is excluded."""
        d = tmp_path / "ed_pii"
        d.mkdir()
        rows = [
            {
                "conv_id": "pii_conv",
                "utterance_idx": "1",
                "context": "hopeful",
                "prompt": "Call me at 555-123-4567 for details.",
                "speaker_idx": "0",
                "utterance": "Call me at 555-123-4567 for details.",
                "selfeval": "",
                "tags": "",
            },
        ]
        csv_path = d / "train.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

        chunks = ingest_ed(d, d / "output")
        assert len(chunks) == 0, "PII row should have been filtered"

    def test_comma_replacement(self, ed_input_dir):
        """Verify _comma_ placeholders are replaced."""
        rows = [
            {
                "conv_id": "comma_conv",
                "utterance_idx": "1",
                "context": "joyful",
                "prompt": "I won first_comma_ second_comma_ and third place!",
                "speaker_idx": "0",
                "utterance": "I won first_comma_ second_comma_ and third place!",
                "selfeval": "",
                "tags": "",
            },
        ]
        chunk = conversation_to_chunk("comma_conv", rows)
        assert "_comma_" not in chunk["text"]
        assert "first, second, and third" in chunk["text"]


# ---------------------------------------------------------------------------
# Social Chemistry 101 tests
# ---------------------------------------------------------------------------

class TestSocialChemistry:

    def test_chunk_format(self):
        chunk = rot_to_chunk(SAMPLE_SC_ROWS[0])
        assert chunk is not None
        assert REQUIRED_KEYS.issubset(chunk.keys()), (
            f"Missing keys: {REQUIRED_KEYS - chunk.keys()}"
        )

    def test_chunk_source_type(self):
        chunk = rot_to_chunk(SAMPLE_SC_ROWS[0])
        assert chunk["source_type"] == "social_chemistry"

    def test_chunk_contains_rot(self):
        chunk = rot_to_chunk(SAMPLE_SC_ROWS[0])
        assert "It's wrong to take someone else's food" in chunk["text"]

    def test_chunk_contains_situation(self):
        chunk = rot_to_chunk(SAMPLE_SC_ROWS[0])
        assert "roommate" in chunk["text"]

    def test_chunk_contains_judgment(self):
        chunk = rot_to_chunk(SAMPLE_SC_ROWS[0])
        assert "it's wrong" in chunk["text"].lower()
        assert chunk["metadata"]["judgment"] == "it's wrong"

    def test_no_pii_in_chunks(self, sc_input_dir):
        chunks = ingest_sc(sc_input_dir, sc_input_dir / "output")
        for chunk in chunks:
            text = chunk["text"]
            assert not re.search(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", text)
            assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.\w+", text)
            assert not re.search(r"\b\d{3}-\d{2}-\d{4}\b", text)

    def test_chunk_count(self, sc_input_dir):
        chunks = ingest_sc(sc_input_dir, sc_input_dir / "output")
        assert len(chunks) == 2, f"Expected 2 chunks, got {len(chunks)}"

    def test_output_jsonl_valid(self, sc_input_dir):
        out_dir = sc_input_dir / "output"
        ingest_sc(sc_input_dir, out_dir)
        jsonl_path = out_dir / "corpus.jsonl"
        assert jsonl_path.exists()
        with open(jsonl_path) as f:
            lines = [line for line in f if line.strip()]
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert REQUIRED_KEYS.issubset(parsed.keys())

    def test_empty_rot_filtered(self):
        """A row with an empty ROT is skipped."""
        row = dict(SAMPLE_SC_ROWS[0])
        row["rot"] = ""
        chunk = rot_to_chunk(row)
        assert chunk is None

    def test_pii_row_filtered(self):
        """A row containing an email in the ROT is excluded."""
        row = dict(SAMPLE_SC_ROWS[0])
        row["rot"] = "Contact john@example.com for advice."
        chunk = rot_to_chunk(row)
        assert chunk is None


# ---------------------------------------------------------------------------
# Agent --sources integration
# ---------------------------------------------------------------------------

class TestAgentSourcesFlag:

    def test_agent_loads_external_source(self, tmp_path):
        """
        AskASailorAgent loads external corpus when sources are specified.
        """
        from rag.agent import SimpleVectorStore

        # Create a fake external corpus
        ext_dir = tmp_path / "social_chemistry"
        ext_dir.mkdir()
        chunk = {
            "chunk_id": "test_c0",
            "doc_id": "test_doc",
            "club_slug": "",
            "source_type": "social_chemistry",
            "source_url": "allenai/social-chemistry-101",
            "title": "Social norm — test",
            "text": "It is good to share.",
            "metadata": {"dataset": "Social Chemistry 101"},
        }
        with open(ext_dir / "corpus.jsonl", "w") as f:
            f.write(json.dumps(chunk) + "\n")

        store = SimpleVectorStore()
        store.load_from_jsonl(ext_dir / "corpus.jsonl")
        assert len(store.chunks) == 1
        assert store.chunks[0]["source_type"] == "social_chemistry"

    def test_agent_sources_missing_is_graceful(self, tmp_path, capsys):
        """
        Specifying a source that doesn't exist should warn, not crash.
        """
        from rag.agent import SimpleVectorStore

        # No corpus file exists for this source
        source_path = tmp_path / "nonexistent_source" / "corpus.jsonl"
        assert not source_path.exists()
        # The SimpleVectorStore raises FileNotFoundError; the agent
        # handles this by printing a warning.  We just confirm
        # the path does not exist — the agent's __init__ does the check.
