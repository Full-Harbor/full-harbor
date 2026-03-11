"""
Quick demo: Run Ask a Sailor against the LYC corpus
using structured audit data only (no web scraping, no embeddings).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "packages/ask-a-sailor/src"))

from ingestion.ingest_club_content import ingest_structured_data, chunk_document, save_corpus

CORPUS_DIR = Path("/tmp/full-harbor/corpus")

# 1. Build corpus from structured audit data
print("Building corpus from verified audit data...")
for slug in ["lyc", "hyc", "tcyc"]:
    docs = ingest_structured_data(slug)
    all_chunks = []
    for doc in docs:
        all_chunks.extend(chunk_document(doc))
    out_path = CORPUS_DIR / slug / "corpus.jsonl"
    save_corpus(all_chunks, out_path)
    print(f"  {slug}: {len(all_chunks)} chunks")

print("\n✅ Corpus ready at /tmp/full-harbor/corpus/")
print("\nTo run Ask a Sailor (requires OPENAI_API_KEY):")
print("  cd /tmp/full-harbor")
print("  python packages/ask-a-sailor/src/rag/agent.py \\")
print("    --club lyc \\")
print("    --corpus-dir /tmp/full-harbor/corpus \\")
print("    --question 'How much does Opti Camp cost for non-members?'")
print("\nTo run the Club Auditor:")
print("  python packages/club-auditor/src/analyzer/audit.py --club all")
print("\nTo ingest 990 data:")
print("  python packages/harbor-commons/src/ingestion/ingest_990.py --known --benchmark")
