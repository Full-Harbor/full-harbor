"""
Ingest Social Chemistry 101 → Ask a Sailor corpus JSONL
========================================================
Converts the Social Chemistry 101 dataset (Allen AI) into the JSONL
chunk format expected by the Ask a Sailor RAG pipeline.

Each *rule-of-thumb* (ROT) is emitted as a single chunk containing
the social situation, the rule, and the moral judgment.

Dataset: https://github.com/mbforbes/social-chemistry-101
Download: https://storage.googleapis.com/ai2-mosaic-public/projects/social-chemistry/data/social-chem-101.zip
License: CC BY-SA 4.0

Usage
-----
1. Download and extract to ``data/external/social-chemistry-101/``::

       mkdir -p data/external
       wget -qO /tmp/social-chem-101.zip \\
           https://storage.googleapis.com/ai2-mosaic-public/projects/social-chemistry/data/social-chem-101.zip
       unzip /tmp/social-chem-101.zip -d data/external/social-chemistry-101/

2. Run this script::

       python scripts/ingest_social_chemistry.py \\
           --input-dir data/external/social-chemistry-101 \\
           --output-dir /tmp/full-harbor/corpus/social_chemistry
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

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


def find_tsv(input_dir: Path) -> Path | None:
    """Locate the main TSV file inside *input_dir*."""
    candidates = list(input_dir.rglob("social-chem-101*.tsv"))
    if candidates:
        return candidates[0]
    # Fallback: any .tsv
    candidates = list(input_dir.rglob("*.tsv"))
    return candidates[0] if candidates else None


def rot_to_chunk(row: dict) -> dict | None:
    """
    Convert a single ROT row into a corpus chunk dict.

    Returns ``None`` if the row is empty or contains PII.
    """
    rot = row.get("rot", "").strip()
    situation = row.get("situation", "").strip()
    action = row.get("action", "").strip()
    judgment = row.get("rot-judgment", "").strip()
    rot_id = row.get("rot-id", "").strip()

    if not rot:
        return None

    lines: list[str] = []
    if situation:
        lines.append(f"Situation: {situation}")
    if action:
        lines.append(f"Action: {action}")
    lines.append(f"Rule of thumb: {rot}")
    if judgment:
        lines.append(f"Judgment: {judgment}")

    text = "\n".join(lines).strip()
    if _has_pii(text):
        return None

    doc_id = _make_chunk_id(rot_id or text)
    return {
        "chunk_id": f"{doc_id}_c0",
        "doc_id": doc_id,
        "club_slug": "",
        "source_type": "social_chemistry",
        "source_url": "allenai/social-chemistry-101",
        "title": f"Social norm — {rot[:80]}",
        "text": text,
        "metadata": {
            "judgment": judgment,
            "area": row.get("area", "").strip(),
            "dataset": "Social Chemistry 101",
            "license": "CC BY-SA 4.0",
        },
    }


def ingest(input_dir: Path, output_dir: Path) -> list[dict]:
    """
    Full pipeline: locate TSV → parse → convert → filter → write JSONL.

    Returns the list of emitted chunks.
    """
    tsv_path = find_tsv(input_dir)
    if tsv_path is None:
        logger.error("No TSV file found in %s", input_dir)
        return []

    logger.info("Reading %s", tsv_path)

    chunks: list[dict] = []
    skipped = 0

    with open(tsv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            chunk = rot_to_chunk(row)
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
        description="Ingest Social Chemistry 101 into Ask a Sailor corpus JSONL"
    )
    parser.add_argument(
        "--input-dir",
        default="data/external/social-chemistry-101",
        help="Path to extracted Social Chemistry 101 directory",
    )
    parser.add_argument(
        "--output-dir",
        default="/tmp/full-harbor/corpus/social_chemistry",
        help="Where to write corpus.jsonl",
    )
    args = parser.parse_args()
    ingest(Path(args.input_dir), Path(args.output_dir))


if __name__ == "__main__":
    main()
