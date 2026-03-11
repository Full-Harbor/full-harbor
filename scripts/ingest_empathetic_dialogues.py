"""
Ingest EmpatheticDialogues → Ask a Sailor corpus JSONL
======================================================
Converts Facebook's EmpatheticDialogues dataset into the JSONL chunk
format expected by the Ask a Sailor RAG pipeline.

Each conversation is grouped by ``conv_id`` and emitted as a single
chunk whose text includes the emotional context, the situation prompt,
and all utterances labelled by speaker role.

Dataset: https://dl.fbaipublicfiles.com/parlai/empatheticdialogues/empatheticdialogues.tar.gz
License: CC BY 4.0

Usage
-----
1. Download and extract to ``data/external/empatheticdialogues/``::

       mkdir -p data/external
       wget -qO- https://dl.fbaipublicfiles.com/parlai/empatheticdialogues/empatheticdialogues.tar.gz | tar xz -C data/external/

2. Run this script::

       python scripts/ingest_empathetic_dialogues.py \\
           --input-dir data/external/empatheticdialogues \\
           --output-dir /tmp/full-harbor/corpus/empathetic_dialogues
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
from collections import defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Columns in the EmpatheticDialogues CSV files
EXPECTED_COLUMNS = [
    "conv_id", "utterance_idx", "context", "prompt",
    "speaker_idx", "utterance", "selfeval", "tags",
]

# Simple patterns that indicate PII leakage (phone, email, SSN)
PII_PATTERNS = [
    re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),          # phone
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.\w+"),  # email
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),                   # SSN
]


def _has_pii(text: str) -> bool:
    """Return True if *text* matches any PII pattern."""
    return any(p.search(text) for p in PII_PATTERNS)


def _make_chunk_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def parse_conversations(input_dir: Path) -> dict[str, list[dict]]:
    """
    Read all EmpatheticDialogues CSV splits and group rows by conv_id.

    Returns a dict mapping ``conv_id`` → list of row dicts, ordered by
    ``utterance_idx``.
    """
    conversations: dict[str, list[dict]] = defaultdict(list)

    for split in ("train", "valid", "test"):
        path = input_dir / f"{split}.csv"
        if not path.exists():
            logger.warning("Split file not found: %s", path)
            continue

        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                conv_id = row.get("conv_id", "").strip()
                if not conv_id:
                    continue
                conversations[conv_id].append(row)

    # Sort utterances within each conversation
    for conv_id in conversations:
        conversations[conv_id].sort(
            key=lambda r: int(r.get("utterance_idx", 0))
        )
    return dict(conversations)


def conversation_to_chunk(conv_id: str, rows: list[dict]) -> dict | None:
    """
    Convert a single conversation (list of rows) into a corpus chunk dict.

    Returns ``None`` if the conversation is empty or contains PII.
    """
    if not rows:
        return None

    context = rows[0].get("context", "unknown").strip()
    prompt = rows[0].get("prompt", "").strip().replace("_comma_", ",")

    lines: list[str] = []
    if prompt:
        lines.append(f"Situation: {prompt}")
    lines.append(f"Emotion: {context}")
    lines.append("")

    for row in rows:
        speaker = "Speaker" if row.get("speaker_idx", "0") == "0" else "Listener"
        utterance = row.get("utterance", "").strip()
        if utterance:
            utterance = utterance.replace("_comma_", ",")
            lines.append(f"{speaker}: {utterance}")

    text = "\n".join(lines).strip()
    if not text or _has_pii(text):
        return None

    doc_id = _make_chunk_id(conv_id)
    return {
        "chunk_id": f"{doc_id}_c0",
        "doc_id": doc_id,
        "club_slug": "",
        "source_type": "empathetic_dialogues",
        "source_url": "facebook/empathetic_dialogues",
        "title": f"Empathetic dialogue — {context}",
        "text": text,
        "metadata": {
            "emotion": context,
            "dataset": "EmpatheticDialogues",
            "license": "CC BY 4.0",
        },
    }


def ingest(input_dir: Path, output_dir: Path) -> list[dict]:
    """
    Full pipeline: parse → convert → filter → write JSONL.

    Returns the list of emitted chunks.
    """
    conversations = parse_conversations(input_dir)
    logger.info("Parsed %d conversations from %s", len(conversations), input_dir)

    chunks: list[dict] = []
    skipped = 0
    for conv_id, rows in conversations.items():
        chunk = conversation_to_chunk(conv_id, rows)
        if chunk is None:
            skipped += 1
            continue
        chunks.append(chunk)

    logger.info(
        "Converted %d chunks (%d skipped for PII or empty)",
        len(chunks),
        skipped,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "corpus.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    logger.info("Saved %d chunks → %s", len(chunks), out_path)
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest EmpatheticDialogues into Ask a Sailor corpus JSONL"
    )
    parser.add_argument(
        "--input-dir",
        default="data/external/empatheticdialogues",
        help="Path to extracted EmpatheticDialogues directory",
    )
    parser.add_argument(
        "--output-dir",
        default="/tmp/full-harbor/corpus/empathetic_dialogues",
        help="Where to write corpus.jsonl",
    )
    args = parser.parse_args()
    ingest(Path(args.input_dir), Path(args.output_dir))


if __name__ == "__main__":
    main()
