"""
Ask a Sailor — RAG Agent
========================
Answers parent questions about sailing clubs, youth programs,
camps, pricing, schedules, and logistics.

"Build once. Deploy everywhere."

Each club deploys this same agent, pointed at their own corpus.
The agent can also answer cross-club comparative questions when
given access to multiple corpora (Harbor Commons mode).

Usage:
  python agent.py --club lyc --question "How much does Opti Camp cost?"
  python agent.py --club all --question "Which club has the best beginner program?"

API mode (FastAPI):
  uvicorn api.main:app --host 0.0.0.0 --port 8000
"""

import json
import os
import argparse
import numpy as np
from pathlib import Path
from typing import Optional

from any_llm import completion, embedding

from prompts.system import SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Simple In-Memory Vector Store (no external dependencies)
# ---------------------------------------------------------------------------

class SimpleVectorStore:
    """
    Minimal cosine-similarity vector store built on numpy.
    For production, swap with Chroma, Pinecone, Weaviate, or pgvector.
    """

    def __init__(self):
        self.chunks: list[dict] = []
        self.embeddings: list[list[float]] = []

    def load_from_jsonl(self, path: Path, embeddings_path: Optional[Path] = None):
        """Load corpus chunks. Embeddings stored separately as .npy."""
        if not path.exists():
            raise FileNotFoundError(f"Corpus not found: {path}")

        with open(path) as f:
            self.chunks = [json.loads(line) for line in f if line.strip()]

        if embeddings_path and embeddings_path.exists():
            self.embeddings = np.load(embeddings_path).tolist()
        else:
            print(f"  ⚠️  No embeddings file found at {embeddings_path}. "
                  "Run ingestion with --embed to generate embeddings.")

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 6,
        club_filter: Optional[str] = None,
    ) -> list[dict]:
        """Return top-k most similar chunks."""
        if not self.embeddings:
            # Fallback: return first N chunks (demo mode without embeddings)
            chunks = self.chunks
            if club_filter:
                chunks = [c for c in chunks if c.get("club_slug") == club_filter]
            return chunks[:top_k]

        q = np.array(query_embedding)
        scores = []
        for i, (chunk, emb) in enumerate(zip(self.chunks, self.embeddings)):
            if club_filter and chunk.get("club_slug") != club_filter:
                continue
            e = np.array(emb)
            score = float(np.dot(q, e) / (np.linalg.norm(q) * np.linalg.norm(e) + 1e-9))
            scores.append((score, i))

        scores.sort(reverse=True)
        return [self.chunks[i] for _, i in scores[:top_k]]


# ---------------------------------------------------------------------------
# Ask a Sailor Agent
# ---------------------------------------------------------------------------

class AskASailorAgent:

    def __init__(
        self,
        corpus_dir: Path,
        club_filter: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.model = model or os.environ.get("LLM_MODEL", "gpt-4o-mini")
        self.club_filter = club_filter
        self.store = SimpleVectorStore()

        # Load corpora for all clubs (or just the specified one)
        clubs_to_load = [club_filter] if club_filter else ["lyc", "hyc", "tcyc"]
        for slug in clubs_to_load:
            corpus_path = corpus_dir / slug / "corpus.jsonl"
            embeddings_path = corpus_dir / slug / "embeddings.npy"
            if corpus_path.exists():
                print(f"  Loading corpus: {slug}")
                store = SimpleVectorStore()
                store.load_from_jsonl(corpus_path, embeddings_path)
                self.store.chunks.extend(store.chunks)
                self.store.embeddings.extend(store.embeddings)
            else:
                print(f"  ⚠️  No corpus found for {slug} — run ingestion first.")

    def embed_query(self, query: str) -> list[float]:
        response = embedding(
            model="text-embedding-3-small",
            inputs=query,
        )
        return response.data[0].embedding

    def retrieve(self, query: str, top_k: int = 6) -> list[dict]:
        query_embedding = self.embed_query(query)
        return self.store.search(
            query_embedding,
            top_k=top_k,
            club_filter=self.club_filter,
        )

    def build_context(self, chunks: list[dict]) -> str:
        parts = []
        for chunk in chunks:
            source_label = (
                f"[{chunk.get('source_type', 'unknown').upper()} — "
                f"{chunk.get('club_slug', '').upper()}]"
            )
            parts.append(f"{source_label}\n{chunk['text']}")
        return "\n\n---\n\n".join(parts)

    def answer(
        self,
        question: str,
        conversation_history: Optional[list[dict]] = None,
        verbose: bool = False,
    ) -> dict:
        """
        Answer a parent question using RAG.

        Returns:
            {
                "answer": str,
                "sources": list[str],
                "retrieved_chunks": list[dict],  # if verbose
            }
        """
        # Retrieve relevant context
        chunks = self.retrieve(question)
        context = self.build_context(chunks)

        if verbose:
            print(f"\n[RAG] Retrieved {len(chunks)} chunks")
            for c in chunks:
                print(f"  - [{c['source_type']}] {c['title'][:60]}...")

        # Build messages
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        if conversation_history:
            messages.extend(conversation_history)

        messages.append({
            "role": "user",
            "content": (
                f"Here is relevant information from sailing club sources:\n\n"
                f"{context}\n\n"
                f"---\n\n"
                f"Parent question: {question}"
            ),
        })

        # Generate answer
        response = completion(
            model=self.model,
            messages=messages,
            temperature=0.3,  # Low temperature for factual accuracy
            max_tokens=800,
        )

        answer_text = response.choices[0].message.content
        sources = list({c.get("source_url", "") for c in chunks if c.get("source_url")})

        result = {
            "answer": answer_text,
            "sources": sources,
            "model": self.model,
            "chunks_retrieved": len(chunks),
        }

        if verbose:
            result["retrieved_chunks"] = chunks

        return result


# ---------------------------------------------------------------------------
# FastAPI App — see api/main.py
# ---------------------------------------------------------------------------
# The FastAPI application has been extracted to src/api/main.py.
# Run with: uvicorn api.main:app --host 0.0.0.0 --port 8000


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Ask a Sailor — CLI")
    parser.add_argument(
        "--club",
        choices=["lyc", "hyc", "tcyc", "all"],
        default="all",
        help="Club to query (default: all)",
    )
    parser.add_argument(
        "--question",
        help="Question to ask (or omit for interactive mode)",
    )
    parser.add_argument(
        "--corpus-dir",
        default="/tmp/full-harbor/corpus",
        help="Path to corpus directory",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    club_filter = None if args.club == "all" else args.club
    agent = AskASailorAgent(
        corpus_dir=Path(args.corpus_dir),
        club_filter=club_filter,
    )

    if args.question:
        result = agent.answer(args.question, verbose=args.verbose)
        print(f"\n{'='*60}")
        print(f"Q: {args.question}")
        print(f"{'='*60}")
        print(result["answer"])
        print(f"\nSources ({result['chunks_retrieved']} chunks retrieved):")
        for src in result["sources"]:
            print(f"  • {src}")
    else:
        # Interactive mode
        print("Ask a Sailor — Interactive Mode")
        print(f"Club: {args.club} | Type 'quit' to exit\n")
        history = []
        while True:
            try:
                q = input("Your question: ").strip()
            except (KeyboardInterrupt, EOFError):
                break
            if q.lower() in ("quit", "exit", "q"):
                break
            if not q:
                continue
            result = agent.answer(q, conversation_history=history)
            print(f"\nAsk a Sailor: {result['answer']}\n")
            history.append({"role": "user", "content": q})
            history.append({"role": "assistant", "content": result["answer"]})


if __name__ == "__main__":
    main()
