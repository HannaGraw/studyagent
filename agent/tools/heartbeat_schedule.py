"""
Schedule configuration helpers for the weekly heartbeat.

The heartbeat is disabled by default. The interactive agent can enable or
disable it by editing memory/heartbeat_schedule.json. A separate script can then
be called manually or by cron/Windows Task Scheduler.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


DAYS = {
    "monday": "Monday",
    "tuesday": "Tuesday",
    "wednesday": "Wednesday",
    "thursday": "Thursday",
    "friday": "Friday",
    "saturday": "Saturday",
    "sunday": "Sunday",
}

DEFAULT_SCHEDULE = {
    "enabled": False,
    "day": "Sunday",
    "time": "18:00",
    "action": "weekly_study_summary",
    "last_run_date": "",
}


def load_schedule(schedule_file: Path) -> dict:
    """Load heartbeat schedule config, creating a disabled default if missing."""

    schedule_file = Path(schedule_file)
    if not schedule_file.exists():
        save_schedule(schedule_file, DEFAULT_SCHEDULE)
        return dict(DEFAULT_SCHEDULE)

    try:
        loaded = json.loads(schedule_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        loaded = {}

    schedule = dict(DEFAULT_SCHEDULE)
    schedule.update(loaded)
    return schedule


def save_schedule(schedule_file: Path, schedule: dict) -> None:
    """Save heartbeat schedule config as readable JSON."""

    schedule_file = Path(schedule_file)
    schedule_file.parent.mkdir(parents=True, exist_ok=True)
    schedule_file.write_text(json.dumps(schedule, indent=2) + "\n", encoding="utf-8")


def parse_schedule_request(text: str) -> tuple[str, str]:
    """Extract day and time from a schedule request."""

    normalized = text.lower()
    day = ""
    for candidate, canonical in DAYS.items():
        if candidate in normalized:
            day = canonical
            break

    time_match = re.search(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", normalized)
    time = ""
    if time_match:
        time = f"{int(time_match.group(1)):02d}:{time_match.group(2)}"

    if not day:
        day = DEFAULT_SCHEDULE["day"]
    if not time:
        time = DEFAULT_SCHEDULE["time"]

    return day, time


def format_schedule(schedule: dict) -> str:
    """Render schedule config for the terminal."""

    status = "enabled" if schedule.get("enabled") else "disabled"
    return (
        "Weekly heartbeat schedule:\n"
        f"- Status: {status}\n"
        f"- Day: {schedule.get('day', DEFAULT_SCHEDULE['day'])}\n"
        f"- Time: {schedule.get('time', DEFAULT_SCHEDULE['time'])}\n"
        f"- Action: {schedule.get('action', DEFAULT_SCHEDULE['action'])}\n"
        f"- Last run date: {schedule.get('last_run_date') or 'never'}"
    )
