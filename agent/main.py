"""
Minimal Step 1 tutor agent loop.

The loop is intentionally visible:

goal -> retrieve -> answer -> memory update

Configuration:
    OPENAI_API_KEY      required for model answers
    OPENAI_BASE_URL     optional, defaults to https://api.berget.ai/v1
    OPENAI_MODEL        optional, defaults to Mistral Small 3.2
    BERGET_API_KEY      optional alias for OPENAI_API_KEY
    BERGET_BASE_URL     optional alias for OPENAI_BASE_URL
    BERGET_MODEL        optional alias for OPENAI_MODEL
    TAVILY_API_KEY      optional, enables web-search fallback
    WEB_SEARCH_ENABLED  optional, set false to disable web search
    LOCAL_CONTEXT_MIN_SCORE optional, defaults to 0.10
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from tools.context_audit import build_context_audit, format_context_audit
from tools.create_study_notes import create_study_note
from tools.heartbeat_schedule import format_schedule, load_schedule, parse_schedule_request, save_schedule
from tools.search_documents import (
    build_or_update_index,
    build_index,
    format_chunks_for_prompt,
    save_index,
    search_documents,
)
from tools.update_mastery import read_mastery, update_mastery
from tools.update_memory import read_memory, update_memory
from tools.web_search import format_web_results_for_prompt, search_web


BASE_DIR = Path(__file__).resolve().parent
COURSE_DIR = BASE_DIR / "course_material"
MEMORY_FILE = BASE_DIR / "memory" / "struggles.md"
MASTERY_FILE = BASE_DIR / "memory" / "mastery.md"
HEARTBEAT_SCHEDULE_FILE = BASE_DIR / "memory" / "heartbeat_schedule.json"
NOTES_DIR = BASE_DIR / "generated_notes"
AGENT_FILE = BASE_DIR / "agent.md"
SOUL_FILE = BASE_DIR / "soul.md"
ENV_FILE = BASE_DIR.parent / ".env"
DEFAULT_OPENAI_BASE_URL = "https://api.berget.ai/v1"
DEFAULT_OPENAI_MODEL = "mistralai/Mistral-Small-3.2-24B-Instruct-2506"
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

STUDY_NOTES_PHRASES = (
    "create study notes",
    "make study notes",
    "generate study notes",
    "write study notes",
    "create notes",
    "make notes",
    "write notes",
    "exam notes",
    "study guide",
    "practice questions",
    "summarize",
)

QUIZ_REQUEST_PHRASES = (
    "quiz me",
    "test me",
    "drill me",
    "practice quiz",
    "give me a quiz",
    "ask me questions",
)

FOLLOW_UP_CUES = (
    "yes",
    "no",
    "why",
    "how",
    "what about",
    "can you",
    "could you",
    "can you explain",
    "explain more",
    "tell me more",
    "give an example",
    "examples",
    "interesting",
    "that",
    "this",
    "it",
)

VAGUE_TOPIC_REFERENCES = (
    "this topic",
    "that topic",
    "this",
    "that",
    "it",
    "the topic",
)


def main() -> None:
    """Run a tiny interactive tutor session."""

    args = parse_args()
    load_env_file(ENV_FILE)
    ensure_workspace()

    if args.reindex:
        print("Reindexing course material...")
        index = build_index(COURSE_DIR)
        save_index(COURSE_DIR, index)
    else:
        print("Checking course material index...")
        index = build_or_update_index(COURSE_DIR)
    print(f"Indexed {index['chunk_count']} chunks from {COURSE_DIR.relative_to(BASE_DIR)}.")
    if index.get("updated_files"):
        print("Indexed new or changed files:")
        for source in index["updated_files"]:
            print(f"- {source}")
    if index.get("skipped_files"):
        print("Skipped some files:")
        for skipped_file in index["skipped_files"]:
            print(f"- {skipped_file['source']}: {skipped_file['reason']}")
    print("Ask a question, or type 'exit' to stop.\n")

    previous_questions: list[str] = []
    conversation_history: list[dict[str, str]] = []
    pending_quiz: dict[str, str] | None = None

    while True:
        question = input("Student> ").strip()
        if question.lower() in {"exit", "quit"}:
            break
        if not question:
            continue

        if wants_heartbeat_command(question):
            print()
            print(handle_heartbeat_command(question))
            print()
            continue

        if pending_quiz and not wants_new_action(question):
            print(f"\nGoal: grade quiz answer for {pending_quiz['topic']}.")
            answer = grade_quiz_answer(question, pending_quiz, conversation_history)
            print(answer)
            update_mastery(MASTERY_FILE, pending_quiz["topic"], answer)
            print(f"Mastery update: updated {MASTERY_FILE.relative_to(BASE_DIR)}.")
            update_memory(MEMORY_FILE, pending_quiz["topic"], "completed quiz attempt", answer)
            print(f"Memory update: updated {MEMORY_FILE.relative_to(BASE_DIR)}.")
            remember_turn(conversation_history, question, answer)
            pending_quiz = None
            print()
            continue

        retrieval_question = question_for_retrieval(question, previous_questions)
        retrieval_query = query_for_retrieval(question, retrieval_question, conversation_history)
        explicit_web_request = wants_web_search(question)
        if retrieval_question != question:
            print(f"\nGoal: answer previous question with web search: {retrieval_question}")
        elif retrieval_query != question:
            print(f"\nGoal: answer follow-up using recent conversation: {question}")
        else:
            print("\nGoal: answer using local course material.")

        print("Retrieve: searching course_material/...")
        chunks = search_documents(retrieval_query, COURSE_DIR, top_k=3)
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

        memory_context = read_memory(MEMORY_FILE)
        context_audit = format_context_audit(
            build_context_audit(
                chunks=chunks,
                web_results=web_results,
                web_reason=web_reason,
                memory_text=memory_context,
                conversation_history=conversation_history,
                follow_up_used=retrieval_query != retrieval_question,
                fallback_reason=fallback_reason,
            )
        )
        print(context_audit)

        if wants_quiz(question):
            print("Skill: quiz_tutor...")
            created_study_notes = False
            answer = create_quiz_answer(
                question,
                chunks,
                web_results,
                web_reason,
                conversation_history,
                context_audit,
            )
            pending_quiz = {
                "topic": extract_quiz_topic(question, conversation_history),
                "quiz": answer,
                "context": build_source_context(chunks, web_results, web_reason),
            }
        elif wants_study_notes(question):
            print("Skill: study_notes...")
            created_study_notes = True
            answer, note_path = create_study_notes_answer(
                question,
                chunks,
                web_results,
                web_reason,
                conversation_history,
                context_audit,
            )
            if note_path:
                print(f"- Saved {note_path.relative_to(BASE_DIR)}")
            else:
                print("- Study notes were not saved.")
        else:
            created_study_notes = False
            print("Answer:")
            answer = answer_question(
                retrieval_question,
                chunks,
                web_results,
                web_reason,
                conversation_history,
                context_audit,
            )
        print(answer)

        should_update, reason = should_update_memory(
            retrieval_question,
            previous_questions,
            chunks,
            web_results,
            web_reason,
            created_study_notes,
        )
        print("Memory update:")
        if should_update:
            update_memory(MEMORY_FILE, retrieval_question, reason, answer)
            print(f"- Updated {MEMORY_FILE.relative_to(BASE_DIR)} ({reason}).")
        else:
            print("- No update needed.")

        previous_questions.append(retrieval_question)
        remember_turn(conversation_history, question, answer)
        print()


def parse_args() -> argparse.Namespace:
    """Parse command-line flags for the interactive agent."""

    parser = argparse.ArgumentParser(description="Run the course-grounded study agent.")
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Rebuild the course-material index before starting.",
    )
    return parser.parse_args()


def answer_question(
    question: str,
    chunks: list,
    web_results: list | None = None,
    web_reason: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    context_audit: str = "",
) -> str:
    """
    Ask an OpenAI-compatible chat API to answer with retrieved context.

    If no API key is configured, return a clear local fallback so the loop still
    demonstrates retrieval and memory behavior.
    """

    context = build_source_context(chunks, web_results, web_reason)
    memory_context = read_memory(MEMORY_FILE)
    history_context = format_conversation_history(conversation_history or [])

    api_key = get_chat_api_key()
    if not api_key:
        return (
            "OPENAI_API_KEY is not set, so I cannot call the model yet.\n"
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
        f"Recent conversation:\n{history_context}\n\n"
        f"{context_audit}\n\n"
        f"Retrieved context:\n{context}\n\n"
        f"Student question: {question}"
    )

    answer = call_chat_model(system_prompt, user_prompt)
    if answer.startswith("Model call failed:"):
        return (
            f"{answer}\n"
            "Retrieved context is shown below so the retrieval step remains inspectable:\n"
            f"{context}"
        )

    return answer


def create_study_notes_answer(
    question: str,
    chunks: list,
    web_results: list | None = None,
    web_reason: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    context_audit: str = "",
) -> tuple[str, Path | None]:
    """Generate structured study notes and save them as a Markdown artifact."""

    topic = extract_study_notes_topic(question, conversation_history or [])
    source_context = build_source_context(chunks, web_results, web_reason)
    memory_context = read_memory(MEMORY_FILE)
    history_context = format_conversation_history(conversation_history or [])

    api_key = get_chat_api_key()
    if not api_key:
        return (
            "OPENAI_API_KEY is not set, so I cannot create study notes yet.\n"
            "Retrieved context:\n"
            f"{source_context}",
            None,
        )

    system_prompt = (
        AGENT_FILE.read_text(encoding="utf-8")
        + "\n\n"
        + SOUL_FILE.read_text(encoding="utf-8")
        + "\n\n"
        + (BASE_DIR / "skills" / "study_notes.md").read_text(encoding="utf-8")
    )
    user_prompt = (
        f"Create Markdown study notes for this topic: {topic}\n\n"
        "Use the retrieved course context as the primary source. If external web context is present, "
        "clearly label it as web context. If context is insufficient, say what is missing.\n"
        "Return only the Markdown note content. Do not mention that you saved a file, and do not invent a file path.\n"
        "Use plain ASCII characters for formulas and symbols.\n"
        "Use this structure: title, source note, key concepts, one Mermaid diagram if useful, "
        "examples, summary table, practice questions with brief answers, and related topics.\n\n"
        f"Student memory:\n{memory_context}\n\n"
        f"Recent conversation:\n{history_context}\n\n"
        f"{context_audit}\n\n"
        f"Retrieved context:\n{source_context}"
    )

    note_content = call_chat_model(system_prompt, user_prompt)
    if note_content.startswith("Model call failed:") or note_content.startswith("OPENAI_API_KEY is not set"):
        return (
            f"Could not create study notes for '{topic}'.\n"
            f"{note_content}\n\n"
            "Retrieved context is shown below so the retrieval step remains inspectable:\n"
            f"{source_context}",
            None,
        )

    note_content = clean_study_note_content(note_content)
    note_path = create_study_note(NOTES_DIR, topic, note_content)
    response = (
        f"Created study notes for '{topic}'.\n"
        f"Saved to: {note_path.relative_to(BASE_DIR)}\n\n"
        f"{note_content}"
    )
    return response, note_path


def create_quiz_answer(
    question: str,
    chunks: list,
    web_results: list | None = None,
    web_reason: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    context_audit: str = "",
) -> str:
    """Generate a short interactive quiz and leave grading for the next turn."""

    topic = extract_quiz_topic(question, conversation_history or [])
    source_context = build_source_context(chunks, web_results, web_reason)
    memory_context = read_memory(MEMORY_FILE)
    mastery_context = read_mastery(MASTERY_FILE)
    history_context = format_conversation_history(conversation_history or [])

    system_prompt = (
        AGENT_FILE.read_text(encoding="utf-8")
        + "\n\n"
        + SOUL_FILE.read_text(encoding="utf-8")
        + "\n\n"
        + (BASE_DIR / "skills" / "quiz_tutor.md").read_text(encoding="utf-8")
    )
    user_prompt = (
        f"Create a short diagnostic quiz for this topic: {topic}\n\n"
        "Return exactly 3 numbered questions. Do not include the answers yet. "
        "Ask the student to answer all three in their next message.\n\n"
        f"Student memory:\n{memory_context}\n\n"
        f"Mastery memory:\n{mastery_context}\n\n"
        f"Recent conversation:\n{history_context}\n\n"
        f"{context_audit}\n\n"
        f"Retrieved context:\n{source_context}"
    )

    quiz = call_chat_model(system_prompt, user_prompt)
    if quiz.startswith("Model call failed:"):
        return (
            f"{quiz}\n"
            "Retrieved context is shown below so the retrieval step remains inspectable:\n"
            f"{source_context}"
        )

    return (
        f"Quiz topic: {topic}\n\n"
        f"{quiz}\n\n"
        "Reply with your answers when you are ready, and I will grade them."
    )


def grade_quiz_answer(
    student_answer: str,
    pending_quiz: dict[str, str],
    conversation_history: list[dict[str, str]] | None = None,
) -> str:
    """Grade a pending quiz answer and return a mastery-oriented report."""

    memory_context = read_memory(MEMORY_FILE)
    mastery_context = read_mastery(MASTERY_FILE)
    history_context = format_conversation_history(conversation_history or [])

    system_prompt = (
        AGENT_FILE.read_text(encoding="utf-8")
        + "\n\n"
        + SOUL_FILE.read_text(encoding="utf-8")
        + "\n\n"
        + (BASE_DIR / "skills" / "quiz_tutor.md").read_text(encoding="utf-8")
    )
    user_prompt = (
        f"Grade this quiz answer for topic: {pending_quiz['topic']}\n\n"
        "Return: score out of 3, mastery label, per-question feedback, error notes, "
        "and one targeted next study action.\n\n"
        f"Quiz:\n{pending_quiz['quiz']}\n\n"
        f"Student answer:\n{student_answer}\n\n"
        f"Source context used to create quiz:\n{pending_quiz['context']}\n\n"
        f"Student memory:\n{memory_context}\n\n"
        f"Mastery memory:\n{mastery_context}\n\n"
        f"Recent conversation:\n{history_context}"
    )

    return call_chat_model(system_prompt, user_prompt)


def build_source_context(
    chunks: list,
    web_results: list | None = None,
    web_reason: str | None = None,
) -> str:
    """Build a shared context block for answers and study-note generation."""

    course_context = format_chunks_for_prompt(chunks)
    external_context = format_web_results_for_prompt(web_results or [])

    if course_context and external_context:
        return (
            "Course context, retrieved first:\n"
            f"{course_context}\n\n"
            "External web context from the web_search skill, retrieved because local context looked weak:\n"
            f"{external_context}"
        )
    if course_context:
        return f"Course context:\n{course_context}"
    if external_context:
        return (
            "No relevant course context was retrieved.\n\n"
            "External web context from the web_search skill:\n"
            f"{external_context}"
        )

    reason = web_reason or "web search was not attempted"
    return (
        "No relevant course context was retrieved.\n"
        f"No external web context was retrieved because {reason}."
    )


def clean_study_note_content(content: str) -> str:
    """Remove assistant preamble so saved notes contain only the note itself."""

    content = fix_common_mojibake(content)
    lines = content.strip().splitlines()
    for index, line in enumerate(lines):
        if line.startswith("#"):
            return "\n".join(lines[index:]).strip()

    return content.strip()


def fix_common_mojibake(text: str) -> str:
    """Clean common UTF-8/Windows console artifacts from generated notes."""

    replacements = {
        "â‰ˆ": "approximately",
        "â€“": "-",
        "â€”": "-",
        "â€™": "'",
        "â€œ": '"',
        "â€": '"',
        "â€¢": "-",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text


def get_chat_api_key() -> str:
    """Read an OpenAI-format API key, with provider-specific aliases supported."""

    return os.getenv("OPENAI_API_KEY") or os.getenv("BERGET_API_KEY", "")


def get_chat_base_url() -> str:
    """Read the OpenAI-compatible chat API base URL."""

    return (
        os.getenv("OPENAI_BASE_URL")
        or os.getenv("BERGET_BASE_URL")
        or DEFAULT_OPENAI_BASE_URL
    )


def get_chat_model() -> str:
    """Read the OpenAI-compatible chat model name."""

    return os.getenv("OPENAI_MODEL") or os.getenv("BERGET_MODEL") or DEFAULT_OPENAI_MODEL


def call_chat_model(system_prompt: str, user_prompt: str) -> str:
    """Call the configured OpenAI-compatible chat-completions model."""

    api_key = get_chat_api_key()
    if not api_key:
        return (
            "OPENAI_API_KEY is not set, so I cannot call the model yet.\n"
            f"Prompt that would have been sent:\n{user_prompt}"
        )

    payload = {
        "model": get_chat_model(),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }

    base_url = get_chat_base_url().rstrip("/")
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
        return f"Model call failed: {error}"

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


def query_for_retrieval(
    question: str,
    retrieval_question: str,
    conversation_history: list[dict[str, str]],
) -> str:
    """Expand short follow-ups with the previous turn for better retrieval."""

    if retrieval_question != question:
        return retrieval_question

    if not conversation_history:
        return question

    if wants_study_notes(question) and has_vague_topic_reference(question):
        return conversation_history[-1]["student"]

    if not looks_like_follow_up(question):
        return question

    previous_user = conversation_history[-1]["student"]
    return f"{previous_user}\nFollow-up: {question}"


def wants_web_search(question: str) -> bool:
    """Detect direct requests to use external web search."""

    normalized = question.lower()
    return any(phrase in normalized for phrase in WEB_SEARCH_REQUEST_PHRASES)


def looks_like_follow_up(question: str) -> bool:
    """Detect short/context-dependent follow-up turns."""

    normalized = question.lower().strip()
    word_count = len(normalized.split())
    if word_count <= 4:
        return True

    return any(normalized.startswith(cue) for cue in FOLLOW_UP_CUES)


def wants_study_notes(question: str) -> bool:
    """Detect requests to create reusable study-note artifacts."""

    normalized = question.lower()
    if any(phrase in normalized for phrase in STUDY_NOTES_PHRASES):
        return True

    return "notes" in normalized and any(
        verb in normalized
        for verb in ("create", "make", "generate", "write", "save", "prepare")
    )


def wants_quiz(question: str) -> bool:
    """Detect requests for an interactive quiz."""

    normalized = question.lower()
    return any(phrase in normalized for phrase in QUIZ_REQUEST_PHRASES)


def wants_new_action(question: str) -> bool:
    """Detect commands that should not be consumed as pending quiz answers."""

    normalized = question.lower().strip()
    if normalized in {"exit", "quit"}:
        return True

    return (
        wants_quiz(question)
        or wants_study_notes(question)
        or wants_web_search(question)
        or wants_heartbeat_command(question)
    )


def wants_heartbeat_command(question: str) -> bool:
    """Detect weekly heartbeat schedule commands."""

    normalized = question.lower()
    return "heartbeat" in normalized and any(
        word in normalized
        for word in ("schedule", "enable", "disable", "status", "weekly")
    )


def handle_heartbeat_command(question: str) -> str:
    """Enable, disable, or show the weekly heartbeat schedule."""

    normalized = question.lower()
    schedule = load_schedule(HEARTBEAT_SCHEDULE_FILE)

    if "disable" in normalized:
        schedule["enabled"] = False
        save_schedule(HEARTBEAT_SCHEDULE_FILE, schedule)
        return "Weekly heartbeat disabled.\n" + format_schedule(schedule)

    if "status" in normalized:
        return format_schedule(schedule)

    day, time = parse_schedule_request(question)
    schedule.update(
        {
            "enabled": True,
            "day": day,
            "time": time,
            "action": "weekly_study_summary",
        }
    )
    save_schedule(HEARTBEAT_SCHEDULE_FILE, schedule)
    return (
        "Weekly heartbeat scheduled. To execute it automatically, call "
        "`python agent/tools/weekly_heartbeat.py` from Windows Task Scheduler or cron.\n"
        + format_schedule(schedule)
    )


def extract_study_notes_topic(
    question: str,
    conversation_history: list[dict[str, str]] | None = None,
) -> str:
    """Extract a compact topic from a study-notes request."""

    topic = question.strip().rstrip(".?!")
    cleanup_patterns = (
        r"^please\s+",
        r"^interesting,?\s+",
        r"^can you\s+",
        r"^could you\s+",
        r"^make\s+me\s+some\s+study\s+notes\s+(about|on|for)\s+",
        r"^make\s+some\s+study\s+notes\s+(about|on|for)\s+",
        r"^create\s+study\s+notes\s+(about|on|for)\s+",
        r"^make\s+study\s+notes\s+(about|on|for)\s+",
        r"^generate\s+study\s+notes\s+(about|on|for)\s+",
        r"^create\s+notes\s+(about|on|for)\s+",
        r"^make\s+notes\s+(about|on|for)\s+",
        r"^write\s+notes\s+(about|on|for)\s+",
        r"^save\s+notes\s+(about|on|for)\s+",
        r"^prepare\s+notes\s+(about|on|for)\s+",
        r"^make\s+exam\s+notes\s+(about|on|for)\s+",
        r"^prepare\s+exam\s+notes\s+(about|on|for)\s+",
        r"^create\s+a\s+study\s+guide\s+(about|on|for)\s+",
        r"^prepare\s+a\s+study\s+guide\s+(about|on|for)\s+",
        r"^summarize\s+",
    )
    for pattern in cleanup_patterns:
        topic = re.sub(pattern, "", topic, flags=re.IGNORECASE)

    topic = topic.strip()
    if has_vague_topic_reference(topic) and conversation_history:
        return infer_topic_from_history(conversation_history)

    return topic or infer_topic_from_history(conversation_history or []) or question.strip()


def extract_quiz_topic(
    question: str,
    conversation_history: list[dict[str, str]] | None = None,
) -> str:
    """Extract a compact topic from a quiz request."""

    topic = question.strip().rstrip(".?!")
    cleanup_patterns = (
        r"^please\s+",
        r"^can you\s+",
        r"^could you\s+",
        r"^quiz\s+me\s+(about|on|for)\s+",
        r"^test\s+me\s+(about|on|for)\s+",
        r"^drill\s+me\s+(about|on|for)\s+",
        r"^give\s+me\s+a\s+quiz\s+(about|on|for)\s+",
        r"^make\s+me\s+a\s+quiz\s+(about|on|for)\s+",
        r"^ask\s+me\s+questions\s+(about|on|for)\s+",
    )
    for pattern in cleanup_patterns:
        topic = re.sub(pattern, "", topic, flags=re.IGNORECASE)

    topic = topic.strip()
    if has_vague_topic_reference(topic) and conversation_history:
        return infer_topic_from_history(conversation_history)

    return topic or infer_topic_from_history(conversation_history or []) or question.strip()


def has_vague_topic_reference(text: str) -> bool:
    """Detect requests that refer back to the previous topic."""

    normalized = text.lower().strip(" .?!,")
    return normalized in VAGUE_TOPIC_REFERENCES or any(
        reference in normalized for reference in ("this topic", "that topic", "the topic")
    )


def infer_topic_from_history(conversation_history: list[dict[str, str]]) -> str:
    """Use the previous substantive user turn as a readable note topic."""

    if not conversation_history:
        return ""

    previous = conversation_history[-1]["student"].strip().rstrip(".?!")
    previous = re.sub(r"^(what|why|how|when|where|who)\s+(is|are|does|do|did|was|were)\s+", "", previous, flags=re.IGNORECASE)
    previous = re.sub(r"^(can you|could you|please)\s+", "", previous, flags=re.IGNORECASE)
    previous = re.sub(r"\?$", "", previous).strip()
    return previous or conversation_history[-1]["student"].strip()


def format_conversation_history(history: list[dict[str, str]], max_turns: int = 4) -> str:
    """Render recent conversation turns for prompt context."""

    if not history:
        return "No previous turns in this session."

    parts = []
    for turn in history[-max_turns:]:
        parts.append(
            "Student: "
            + turn["student"]
            + "\nTutor: "
            + shorten_text(turn["tutor"], 500)
        )
    return "\n\n".join(parts)


def remember_turn(history: list[dict[str, str]], student: str, tutor: str, max_turns: int = 8) -> None:
    """Keep a compact in-session conversation history."""

    history.append({"student": student, "tutor": tutor})
    del history[:-max_turns]


def shorten_text(text: str, max_chars: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3] + "..."


def should_update_memory(
    question: str,
    previous_questions: list[str],
    chunks: list | None = None,
    web_results: list | None = None,
    web_reason: str | None = None,
    created_study_notes: bool = False,
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

    if created_study_notes:
        return True, "created study notes"

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
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    if not MEMORY_FILE.exists():
        MEMORY_FILE.write_text("# Student Struggle Areas\n\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nStopped.")
