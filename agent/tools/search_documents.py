"""
Explicit document retrieval tool for the Step 1 tutor agent.

This module reads local course material, chunks it, builds a tiny lexical index,
and retrieves the most relevant chunks for a question. It intentionally avoids
embeddings and external services so the MVP stays easy to inspect.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SUPPORTED_EXTENSIONS = {".txt", ".md", ".py", ".csv"}
INDEX_FILENAME = ".document_index.json"
CHUNK_WORDS = 180
CHUNK_OVERLAP = 40


@dataclass
class RetrievedChunk:
    """A small piece of course material returned by search_documents."""

    source: str
    chunk_id: int
    score: float
    text: str


def build_index(course_dir: Path) -> dict:
    """
    Build a simple in-memory index from files in course_dir.

    Each chunk stores raw text and token counts. Search later computes a compact
    TF-IDF-like score over these counts.
    """

    course_dir = Path(course_dir)
    chunks = []

    for path in sorted(_iter_course_files(course_dir)):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for chunk_id, chunk_text in enumerate(_chunk_text(text)):
            tokens = _tokenize(chunk_text)
            if not tokens:
                continue
            chunks.append(
                {
                    "source": str(path.relative_to(course_dir)),
                    "chunk_id": chunk_id,
                    "text": chunk_text,
                    "term_counts": dict(Counter(tokens)),
                }
            )

    document_frequency = defaultdict(int)
    for chunk in chunks:
        for term in chunk["term_counts"]:
            document_frequency[term] += 1

    return {
        "chunk_count": len(chunks),
        "chunks": chunks,
        "document_frequency": dict(document_frequency),
    }


def save_index(course_dir: Path, index: dict) -> None:
    """Persist the index in the file-based agent workspace."""

    index_path = Path(course_dir) / INDEX_FILENAME
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")


def load_or_build_index(course_dir: Path) -> dict:
    """
    Load a saved index if present, otherwise build one.

    This keeps the main loop explicit while avoiding hidden global state.
    """

    course_dir = Path(course_dir)
    index_path = course_dir / INDEX_FILENAME
    if index_path.exists():
        return json.loads(index_path.read_text(encoding="utf-8"))

    index = build_index(course_dir)
    save_index(course_dir, index)
    return index


def search_documents(query: str, course_dir: Path, top_k: int = 3) -> list[RetrievedChunk]:
    """
    Explicit retrieval action: return top_k relevant chunks for query.

    The scoring is intentionally simple:
    - tokenize the question
    - reward chunks containing rare query terms
    - normalize slightly by chunk length
    """

    index = load_or_build_index(course_dir)
    query_terms = _tokenize(query)
    if not query_terms:
        return []

    query_counts = Counter(query_terms)
    total_chunks = max(index["chunk_count"], 1)
    scored_chunks = []

    for chunk in index["chunks"]:
        term_counts = chunk["term_counts"]
        score = 0.0
        chunk_length = sum(term_counts.values()) or 1

        for term, query_count in query_counts.items():
            if term not in term_counts:
                continue
            tf = term_counts[term] / chunk_length
            idf = math.log((1 + total_chunks) / (1 + index["document_frequency"].get(term, 0))) + 1
            score += query_count * tf * idf

        if score > 0:
            scored_chunks.append(
                RetrievedChunk(
                    source=chunk["source"],
                    chunk_id=chunk["chunk_id"],
                    score=score,
                    text=chunk["text"],
                )
            )

    return sorted(scored_chunks, key=lambda item: item.score, reverse=True)[:top_k]


def format_chunks_for_prompt(chunks: Iterable[RetrievedChunk]) -> str:
    """Render retrieved chunks into a compact prompt-friendly context block."""

    parts = []
    for index, chunk in enumerate(chunks, start=1):
        parts.append(
            f"[{index}] Source: {chunk.source}, chunk {chunk.chunk_id}, score {chunk.score:.4f}\n"
            f"{chunk.text}"
        )
    return "\n\n".join(parts)


def _iter_course_files(course_dir: Path) -> Iterable[Path]:
    if not course_dir.exists():
        return []
    return (
        path
        for path in course_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
        and path.name != INDEX_FILENAME
    )


def _chunk_text(text: str) -> Iterable[str]:
    words = text.split()
    if not words:
        return []

    step = max(CHUNK_WORDS - CHUNK_OVERLAP, 1)
    return (
        " ".join(words[start : start + CHUNK_WORDS])
        for start in range(0, len(words), step)
    )


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_]+", text.lower())


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parents[1]
    index = build_index(base_dir / "course_material")
    save_index(base_dir / "course_material", index)
    print(f"Indexed {index['chunk_count']} chunks.")

