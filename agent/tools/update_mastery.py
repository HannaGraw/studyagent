"""
Concept mastery tracker for quiz-based tutoring.

Mastery is intentionally simple and human-readable. The agent updates this file
after grading a quiz so future sessions can see which concepts need more work.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def read_mastery(mastery_file: Path, max_chars: int = 1800) -> str:
    """Read a compact mastery summary for prompt context."""

    mastery_file = Path(mastery_file)
    if not mastery_file.exists():
        return "No mastery data recorded yet."

    text = mastery_file.read_text(encoding="utf-8").strip()
    if not text:
        return "No mastery data recorded yet."

    if len(text) <= max_chars:
        return text

    return "Recent mastery excerpt:\n" + text[-max_chars:]


def update_mastery(mastery_file: Path, topic: str, grade_report: str) -> None:
    """Append a quiz result to memory/mastery.md."""

    mastery_file = Path(mastery_file)
    mastery_file.parent.mkdir(parents=True, exist_ok=True)

    if not mastery_file.exists():
        mastery_file.write_text("# Concept Mastery\n\n", encoding="utf-8")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = (
        f"\n## {timestamp} - {topic.strip()}\n\n"
        f"{grade_report.strip()}\n"
    )
    with mastery_file.open("a", encoding="utf-8") as file:
        file.write(entry)
