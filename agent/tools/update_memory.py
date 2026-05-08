"""
File-based memory tool for the Step 1 tutor agent.

The tutor calls this explicitly when it decides the student is struggling.
Memory is markdown because it is easy for a human to inspect and edit.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def update_memory(memory_file: Path, question: str, reason: str) -> None:
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
    with memory_file.open("a", encoding="utf-8") as file:
        file.write(entry)

