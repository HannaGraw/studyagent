# Weekly Heartbeat Skill

Use this skill when the student wants a scheduled weekly study summary.

Purpose:

- Keep the heartbeat disabled by default to avoid unwanted API calls.
- Let the student schedule a weekly study heartbeat from the interactive agent.
- Generate a weekly report from memory, mastery, and generated-note metadata.
- Support manual testing and external scheduling with cron or Windows Task
  Scheduler.

Interactive commands:

- "Schedule weekly heartbeat every Sunday at 18:00"
- "Enable heartbeat on Friday at 16:30"
- "Heartbeat status"
- "Disable heartbeat"

Files:

- `agent/heartbeat.md`: prompt/instructions for the heartbeat.
- `agent/memory/heartbeat_schedule.json`: opt-in schedule config.
- `agent/tools/weekly_heartbeat.py`: schedule-compatible runner.
- `agent/memory/weekly_reports.md`: generated weekly reports.

Runner:

- Manual test: `python agent/tools/weekly_heartbeat.py --force`
- Scheduled run: `python agent/tools/weekly_heartbeat.py`

The runner only calls the model when the schedule is enabled and due, unless
`--force` is used.
