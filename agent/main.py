"""
Minimal Step 1 tutor agent loop.

The loop is intentionally visible:

goal -> retrieve -> answer -> memory update

Configuration:
    BERGET_API_KEY      required for model answers
    BERGET_BASE_URL     optional, defaults to https://api.berget.ai/v1
    BERGET_MODEL        optional, defaults to Mistral Small 3.2
    TAVILY_API_KEY      optional, enables web-search fallback
    WEB_SEARCH_ENABLED  optional, set false to disable web search
    LOCAL_CONTEXT_MIN_SCORE optional, defaults to 0.10
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
from tools.update_memory import read_memory, update_memory
from tools.web_search import format_web_results_for_prompt, search_web


BASE_DIR = Path(__file__).resolve().parent
COURSE_DIR = BASE_DIR / "course_material"
MEMORY_FILE = BASE_DIR / "memory" / "struggles.md"
AGENT_FILE = BASE_DIR / "agent.md"
SOUL_FILE = BASE_DIR / "soul.md"
ENV_FILE = BASE_DIR.parent / ".env"
DEFAULT_BERGET_MODEL = "mistralai/Mistral-Small-3.2-24B-Instruct-2506"
DEFAULT_LOCAL_CONTEXT_MIN_SCORE = 0.10

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

LEARNING_SIGNAL_PHRASES = (
    "i am studying",
    "i'm studying",
    "i need to learn",
    "i want to learn",
    "i struggle with",
    "i have trouble with",
    "i find",
    "hard for me",
)

WEB_SEARCH_REQUEST_PHRASES = (
    "search the web",
    "web search",
    "search online",
    "look it up",
    "google it",
    "use the web",
    "internet search",
)

GENERAL_WEB_FALLBACK_PHRASES = (
    "how long has",
    "how long have",
    "when did",
    "when was",
    "who won",
    "latest",
    "current",
    "today",
    "recent",
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

        retrieval_question = question_for_retrieval(question, previous_questions)
        explicit_web_request = wants_web_search(question)
        if retrieval_question != question:
            print(f"\nGoal: answer previous question with web search: {retrieval_question}")
        else:
            print("\nGoal: answer using local course material.")

        print("Retrieve: searching course_material/...")
        chunks = search_documents(retrieval_question, COURSE_DIR, top_k=3)
        web_results = []
        web_reason = None
        use_web_fallback, fallback_reason = should_use_web_fallback(
            retrieval_question,
            chunks,
            explicit_web_request,
        )
        if chunks:
            for chunk in chunks:
                print(f"- {chunk.source} chunk {chunk.chunk_id} (score {chunk.score:.4f})")
        else:
            print("- No relevant chunks found.")

        if use_web_fallback:
            if chunks:
                print(f"- Local context looks weak ({fallback_reason}).")
            print("Skill: web_search fallback...")
            web_results, web_reason = search_web(retrieval_question, max_results=3)
            if web_results:
                for result in web_results:
                    print(f"- {result.title} ({result.url})")
            else:
                print(f"- No web context retrieved ({web_reason}).")

        print("Answer:")
        answer = answer_question(retrieval_question, chunks, web_results, web_reason)
        print(answer)

        should_update, reason = should_update_memory(
            retrieval_question,
            previous_questions,
            chunks,
            web_results,
            web_reason,
        )
        print("Memory update:")
        if should_update:
            update_memory(MEMORY_FILE, retrieval_question, reason, answer)
            print(f"- Updated {MEMORY_FILE.relative_to(BASE_DIR)} ({reason}).")
        else:
            print("- No update needed.")

        previous_questions.append(retrieval_question)
        print()


def answer_question(
    question: str,
    chunks: list,
    web_results: list | None = None,
    web_reason: str | None = None,
) -> str:
    """
    Ask Berget's OpenAI-compatible chat API to answer with retrieved context.

    If no API key is configured, return a clear local fallback so the loop still
    demonstrates retrieval and memory behavior.
    """

    course_context = format_chunks_for_prompt(chunks)
    external_context = format_web_results_for_prompt(web_results or [])
    memory_context = read_memory(MEMORY_FILE)

    if course_context and external_context:
        context = (
            "Course context, retrieved first:\n"
            f"{course_context}\n\n"
            "External web context from the web_search skill, retrieved because local context looked weak:\n"
            f"{external_context}"
        )
    elif course_context:
        context = f"Course context:\n{course_context}"
    elif external_context:
        context = (
            "No relevant course context was retrieved.\n\n"
            "External web context from the web_search skill:\n"
            f"{external_context}"
        )
    else:
        reason = web_reason or "web search was not attempted"
        context = (
            "No relevant course context was retrieved.\n"
            f"No external web context was retrieved because {reason}."
        )

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
        "Use course context as the primary source of truth.\n"
        "If external web context is provided, use it when the course context is missing or incomplete, "
        "and clearly say which parts are based on web search rather than the uploaded material.\n"
        "Do not ask permission to search the web; if web context is present, the search has already happened.\n"
        "If neither source has enough context, say so honestly.\n\n"
        f"Student memory:\n{memory_context}\n\n"
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


def should_use_web_fallback(
    question: str,
    chunks: list,
    explicit_web_request: bool = False,
) -> tuple[bool, str]:
    """Decide whether local retrieval is too weak and web search should run."""

    if explicit_web_request:
        return True, "the student explicitly requested web search"

    if not chunks:
        return True, "no local chunks found"

    normalized = question.lower()
    if any(phrase in normalized for phrase in GENERAL_WEB_FALLBACK_PHRASES):
        return True, "the question asks for broad or time-sensitive external context"

    min_score = float(os.getenv("LOCAL_CONTEXT_MIN_SCORE", DEFAULT_LOCAL_CONTEXT_MIN_SCORE))
    best_score = max(chunk.score for chunk in chunks)
    if best_score < min_score:
        return True, f"best local score {best_score:.4f} is below {min_score:.4f}"

    return False, ""


def question_for_retrieval(question: str, previous_questions: list[str]) -> str:
    """Use the previous substantive question when the student asks to search web."""

    if wants_web_search(question) and previous_questions:
        return previous_questions[-1]

    return question


def wants_web_search(question: str) -> bool:
    """Detect direct requests to use external web search."""

    normalized = question.lower()
    return any(phrase in normalized for phrase in WEB_SEARCH_REQUEST_PHRASES)


def should_update_memory(
    question: str,
    previous_questions: list[str],
    chunks: list | None = None,
    web_results: list | None = None,
    web_reason: str | None = None,
) -> tuple[bool, str]:
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

    if any(phrase in normalized for phrase in LEARNING_SIGNAL_PHRASES):
        return True, "student learning preference or struggle signal"

    if web_results:
        return True, "needed external web context"

    if chunks:
        min_score = float(os.getenv("LOCAL_CONTEXT_MIN_SCORE", DEFAULT_LOCAL_CONTEXT_MIN_SCORE))
        best_score = max(chunk.score for chunk in chunks)
        if best_score < min_score:
            return True, "weak local retrieval"

    if web_reason:
        return True, f"web fallback did not retrieve context ({web_reason})"

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
