"""
Weekly heartbeat runner.

Run manually:
    python agent/tools/weekly_heartbeat.py --force

Schedule with cron or Windows Task Scheduler:
    python agent/tools/weekly_heartbeat.py

Without --force, the script only calls the model when the schedule is enabled
and the current day matches memory/heartbeat_schedule.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from heartbeat_schedule import load_schedule, save_schedule


BASE_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BASE_DIR.parent
ENV_FILE = REPO_DIR / ".env"
HEARTBEAT_FILE = BASE_DIR / "heartbeat.md"
MEMORY_DIR = BASE_DIR / "memory"
SCHEDULE_FILE = MEMORY_DIR / "heartbeat_schedule.json"
STRUGGLES_FILE = MEMORY_DIR / "struggles.md"
MASTERY_FILE = MEMORY_DIR / "mastery.md"
WEEKLY_REPORTS_FILE = MEMORY_DIR / "weekly_reports.md"
NOTES_DIR = BASE_DIR / "generated_notes"
DEFAULT_OPENAI_BASE_URL = "https://api.berget.ai/v1"
DEFAULT_OPENAI_MODEL = "mistralai/Mistral-Small-3.2-24B-Instruct-2506"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the weekly study heartbeat.")
    parser.add_argument("--force", action="store_true", help="Run even if schedule is disabled or not due.")
    args = parser.parse_args()

    load_env_file(ENV_FILE)
    schedule = load_schedule(SCHEDULE_FILE)
    now = datetime.now()

    if not args.force and not is_due(schedule, now):
        print("Weekly heartbeat is not due.")
        print(f"- Enabled: {schedule.get('enabled')}")
        print(f"- Scheduled: {schedule.get('day')} at {schedule.get('time')}")
        print(f"- Today: {now.strftime('%A')}")
        return

    report = generate_weekly_report(now)
    append_weekly_report(WEEKLY_REPORTS_FILE, report)

    schedule["last_run_date"] = now.strftime("%Y-%m-%d")
    save_schedule(SCHEDULE_FILE, schedule)

    print(f"Weekly heartbeat written to {WEEKLY_REPORTS_FILE.relative_to(BASE_DIR)}.")


def is_due(schedule: dict, now: datetime) -> bool:
    """Return true when enabled and today's weekday matches the schedule."""

    if not schedule.get("enabled"):
        return False

    if schedule.get("day") != now.strftime("%A"):
        return False

    if schedule.get("last_run_date") == now.strftime("%Y-%m-%d"):
        return False

    return True


def generate_weekly_report(now: datetime) -> str:
    """Ask the chat model for a concise weekly study report."""

    heartbeat_prompt = read_text_or_default(HEARTBEAT_FILE, "Write a weekly study report.")
    struggles = read_text_or_default(STRUGGLES_FILE, "No struggle memory recorded.")
    mastery = read_text_or_default(MASTERY_FILE, "No mastery memory recorded.")
    generated_notes = list_generated_notes(NOTES_DIR)

    user_prompt = (
        f"Week ending: {now.strftime('%Y-%m-%d')}\n\n"
        f"Heartbeat instructions:\n{heartbeat_prompt}\n\n"
        f"Student struggle memory:\n{trim(struggles, 2500)}\n\n"
        f"Concept mastery memory:\n{trim(mastery, 2500)}\n\n"
        f"Generated notes:\n{generated_notes}"
    )

    report = call_chat_model(
        "You are a safe weekly heartbeat for a course-grounded study agent.",
        user_prompt,
    )
    return report.strip()


def append_weekly_report(path: Path, report: str) -> None:
    """Append a generated heartbeat report to memory/weekly_reports.md."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("# Weekly Heartbeat Reports\n\n", encoding="utf-8")

    with path.open("a", encoding="utf-8") as file:
        file.write(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        file.write(report.strip() + "\n")


def list_generated_notes(notes_dir: Path) -> str:
    """Return generated note filenames for the weekly report context."""

    if not notes_dir.exists():
        return "No generated notes folder found."

    notes = sorted(path.name for path in notes_dir.glob("*.md"))
    if not notes:
        return "No generated notes found."

    return "\n".join(f"- {note}" for note in notes[-20:])


def call_chat_model(system_prompt: str, user_prompt: str) -> str:
    """Call the configured OpenAI-compatible chat-completions model."""

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("BERGET_API_KEY")
    if not api_key:
        return "OPENAI_API_KEY is not set, so the heartbeat could not call the model."

    base_url = (
        os.getenv("OPENAI_BASE_URL")
        or os.getenv("BERGET_BASE_URL")
        or DEFAULT_OPENAI_BASE_URL
    ).rstrip("/")
    model = os.getenv("OPENAI_MODEL") or os.getenv("BERGET_MODEL") or DEFAULT_OPENAI_MODEL
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }
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

    return data["choices"][0]["message"]["content"]


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE lines from .env."""

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


def read_text_or_default(path: Path, default: str) -> str:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8").strip() or default


def trim(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return "Recent excerpt:\n" + text[-max_chars:]


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nStopped.")
