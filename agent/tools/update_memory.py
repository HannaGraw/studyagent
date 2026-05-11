"""
File-based memory tools for the Step 1 tutor agent.

The tutor calls this explicitly when it decides the student is struggling.
Memory is markdown because it is easy for a human to inspect and edit.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def read_memory(memory_file: Path, max_chars: int = 1800) -> str:
    """Read a compact memory summary for the model prompt."""

    memory_file = Path(memory_file)
    if not memory_file.exists():
        return "No memory recorded yet."

    text = memory_file.read_text(encoding="utf-8").strip()
    if not text:
        return "No memory recorded yet."

    if len(text) <= max_chars:
        return text

    return "Recent memory excerpt:\n" + text[-max_chars:]


def update_memory(memory_file: Path, question: str, reason: str, answer: str = "") -> None:
    """Append a short struggle observation to memory/struggles.md."""

    memory_file = Path(memory_file)
    memory_file.parent.mkdir(parents=True, exist_ok=True)

    if not memory_file.exists():
        memory_file.write_text("# Student Struggle Areas\n\n", encoding="utf-8")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = (
        f"\n## {timestamp}\n\n"
        f"- Reason: {reason}\n"
        f"- Student question: {question.strip()}\n"
    )
    if answer:
        entry += f"- Tutor response summary: {_summarize_answer(answer)}\n"

    with memory_file.open("a", encoding="utf-8") as file:
        file.write(entry)


def _summarize_answer(answer: str, max_chars: int = 220) -> str:
    compact = " ".join(answer.split())
    if len(compact) <= max_chars:
        return compact

    return compact[: max_chars - 3] + "..."
