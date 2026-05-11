"""
Minimal Step 1 tutor agent loop.

The loop is intentionally visible:

goal -> retrieve -> answer -> memory update

Configuration:
    BERGET_API_KEY      required for model answers
    BERGET_BASE_URL     optional, defaults to https://api.berget.ai/v1
    BERGET_MODEL        optional, defaults to Mistral Small 3.2
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from tools.search_documents import (
    build_index,
    format_chunks_for_prompt,
    save_index,
    search_documents,
)
from tools.update_memory import update_memory


BASE_DIR = Path(__file__).resolve().parent
COURSE_DIR = BASE_DIR / "course_material"
MEMORY_FILE = BASE_DIR / "memory" / "struggles.md"
AGENT_FILE = BASE_DIR / "agent.md"
SOUL_FILE = BASE_DIR / "soul.md"
ENV_FILE = BASE_DIR.parent / ".env"
DEFAULT_BERGET_MODEL = "mistralai/Mistral-Small-3.2-24B-Instruct-2506"

CONFUSION_PHRASES = (
    "i don't get",
    "i dont get",
    "i do not get",
    "i'm confused",
    "im confused",
    "i am confused",
    "this is confusing",
    "can you explain again",
    "still confused",
    "doesn't make sense",
    "does not make sense",
)


def main() -> None:
    """Run a tiny interactive tutor session."""

    load_env_file(ENV_FILE)
    ensure_workspace()

    print("Indexing course material...")
    index = build_index(COURSE_DIR)
    save_index(COURSE_DIR, index)
    print(f"Indexed {index['chunk_count']} chunks from {COURSE_DIR}.")
    if index.get("skipped_files"):
        print("Skipped some files:")
        for skipped_file in index["skipped_files"]:
            print(f"- {skipped_file['source']}: {skipped_file['reason']}")
    print("Ask a question, or type 'exit' to stop.\n")

    previous_questions: list[str] = []

    while True:
        question = input("Student> ").strip()
        if question.lower() in {"exit", "quit"}:
            break
        if not question:
            continue

        print("\nGoal: answer using local course material.")

        print("Retrieve: searching course_material/...")
        chunks = search_documents(question, COURSE_DIR, top_k=3)
        if chunks:
            for chunk in chunks:
                print(f"- {chunk.source} chunk {chunk.chunk_id} (score {chunk.score:.4f})")
        else:
            print("- No relevant chunks found.")

        print("Answer:")
        answer = answer_question(question, chunks)
        print(answer)

        should_update, reason = should_update_memory(question, previous_questions)
        print("Memory update:")
        if should_update:
            update_memory(MEMORY_FILE, question, reason)
            print(f"- Updated {MEMORY_FILE.relative_to(BASE_DIR)} ({reason}).")
        else:
            print("- No update needed.")

        previous_questions.append(question)
        print()


def answer_question(question: str, chunks: list) -> str:
    """
    Ask Berget's OpenAI-compatible chat API to answer with retrieved context.

    If no API key is configured, return a clear local fallback so the loop still
    demonstrates retrieval and memory behavior.
    """

    context = format_chunks_for_prompt(chunks)
    if not context:
        context = "No relevant course context was retrieved."

    api_key = os.getenv("BERGET_API_KEY")
    if not api_key:
        return (
            "BERGET_API_KEY is not set, so I cannot call the model yet.\n"
            "Retrieved context:\n"
            f"{context}"
        )

    system_prompt = (
        AGENT_FILE.read_text(encoding="utf-8")
        + "\n\n"
        + SOUL_FILE.read_text(encoding="utf-8")
    )
    user_prompt = (
        "Use only the retrieved course context unless you clearly say the context is insufficient.\n\n"
        f"Retrieved context:\n{context}\n\n"
        f"Student question: {question}"
    )

    payload = {
        "model": os.getenv("BERGET_MODEL", DEFAULT_BERGET_MODEL),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }

    base_url = os.getenv("BERGET_BASE_URL", "https://api.berget.ai/v1").rstrip("/")
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as error:
        return (
            f"Model call failed: {error}\n"
            "Retrieved context is shown below so the retrieval step remains inspectable:\n"
            f"{context}"
        )

    return data["choices"][0]["message"]["content"].strip()


def should_update_memory(question: str, previous_questions: list[str]) -> tuple[bool, str]:
    """
    Decide whether the agent should call the memory tool.

    This is deliberately simple for Step 1: update memory for explicit confusion
    phrases or repeated questions within the same session.
    """

    normalized = question.lower()
    if any(phrase in normalized for phrase in CONFUSION_PHRASES):
        return True, "explicit confusion phrase"

    if normalized in (old_question.lower() for old_question in previous_questions):
        return True, "repeated question"

    return False, ""


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE lines from .env without requiring python-dotenv."""

    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def ensure_workspace() -> None:
    """Create the file-based workspace pieces if they are missing."""

    COURSE_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not MEMORY_FILE.exists():
        MEMORY_FILE.write_text("# Student Struggle Areas\n\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nStopped.")
