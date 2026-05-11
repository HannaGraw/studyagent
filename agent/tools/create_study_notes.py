"""
Study-notes file tool for the tutor agent.

The chat model creates the note content, while this tool handles safe filenames
and writes the Markdown artifact into the agent workspace.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


def create_study_note(notes_dir: Path, topic: str, content: str) -> Path:
    """Save a generated study note as Markdown and return its path."""

    notes_dir = Path(notes_dir)
    notes_dir.mkdir(parents=True, exist_ok=True)

    date_prefix = datetime.now().strftime("%Y%m%d")
    filename = f"{date_prefix}-{_slugify(topic)}.md"
    note_path = notes_dir / filename
    note_path.write_text(content.strip() + "\n", encoding="utf-8")
    return note_path


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return slug[:80] or "study-notes"
