# StudyAgent

StudyAgent is a course-grounded AI tutor agent built for an Information
Retrieval assignment. It answers questions from local course material, improves
context with retrieval tools, and can perform study-oriented actions such as
creating notes, running quizzes, tracking mastery, and generating weekly
heartbeat summaries.

The project is designed to run with an OpenAI-compatible chat-completions API.
Berget AI works because it exposes an OpenAI-style `/v1/chat/completions`
endpoint.

## Repository

GitHub: <https://github.com/HannaGraw/studyagent>

## Features

- Local course-material retrieval from files in `agent/course_material/`.
- PDF support through `pypdf`.
- Optional web-search fallback through Tavily.
- File-based memory in `agent/memory/struggles.md`.
- Concept mastery tracking in `agent/memory/mastery.md`.
- Recent conversation history for follow-up questions.
- Context audit showing which sources were used before each answer.
- Study-note generation into `agent/generated_notes/`.
- Quiz tutor mode with grading and mastery updates.
- Opt-in weekly heartbeat reports that can be run manually or scheduled.

## Setup

Create and activate a Python environment. The project has been tested with
Python 3.12.

```powershell
conda create -n ir-a2 python=3.12 pypdf
conda activate ir-a2
```

If you already have an environment, install the only required non-standard
package:

```powershell
pip install pypdf
```

## Environment Variables

Create a `.env` file in the repository root. The required model configuration
uses OpenAI-compatible names:

```env
OPENAI_API_KEY=your_openai_format_api_key_here
OPENAI_BASE_URL=https://api.berget.ai/v1
OPENAI_MODEL=mistralai/Mistral-Small-3.2-24B-Instruct-2506
```

For compatibility, the code also accepts the older Berget-specific aliases:

```env
BERGET_API_KEY=...
BERGET_BASE_URL=...
BERGET_MODEL=...
```

Web search is optional. Add a Tavily key only if you want the web-search
fallback:

```env
TAVILY_API_KEY=your_tavily_api_key_here
WEB_SEARCH_ENABLED=true
TAVILY_SEARCH_DEPTH=basic
LOCAL_CONTEXT_MIN_SCORE=0.10
```

Without `TAVILY_API_KEY`, the agent still runs with local document retrieval,
memory, conversation history, context audit, study notes, quizzes, and heartbeat
tools.

## Course Material

Put course files directly in:

```text
agent/course_material/
```

PDF files are supported. Uploaded course PDFs and generated indexes are ignored
by Git.

## Running the Agent

From the repository root:

```powershell
python agent/main.py
```

If your shell points to the wrong Python environment, run through Conda:

```powershell
conda run -n ir-a2 python agent/main.py
```

The agent indexes course material on startup and then accepts interactive
commands.

## Example Prompts

Ask a course-grounded question:

```text
What is BM25?
```

Ask for web fallback:

```text
Search the web for the history of AI agents.
```

Create study notes:

```text
Create study notes about traditional information retrieval.
```

Run an interactive quiz:

```text
Quiz me on BM25.
```

Schedule a weekly heartbeat:

```text
Schedule weekly heartbeat every Sunday at 18:00.
```

Check or disable the heartbeat:

```text
Heartbeat status
Disable heartbeat
```

## Weekly Heartbeat

The heartbeat is disabled by default. It is configured in:

```text
agent/memory/heartbeat_schedule.json
```

Run manually for testing:

```powershell
python agent/tools/weekly_heartbeat.py --force
```

Run without `--force` from cron or Windows Task Scheduler:

```powershell
python agent/tools/weekly_heartbeat.py
```

When enabled and due, the heartbeat reads memory, mastery, generated-note
metadata, and `agent/heartbeat.md`, then writes a weekly report to:

```text
agent/memory/weekly_reports.md
```

Generated heartbeat reports are ignored by Git.

## Project Structure

```text
agent/
  main.py                     Interactive tutor loop
  agent.md                    Agent behavior instructions
  soul.md                     Tutor style/personality instructions
  heartbeat.md                Weekly heartbeat prompt
  tools/
    search_documents.py       Local document retrieval
    web_search.py             Optional Tavily web search
    update_memory.py          File-based student memory
    update_mastery.py         Quiz mastery tracking
    context_audit.py          Context provenance reporting
    create_study_notes.py     Saved Markdown note artifacts
    heartbeat_schedule.py     Heartbeat schedule config helpers
    weekly_heartbeat.py       Schedule-compatible heartbeat runner
  skills/
    memory.md
    web_search.md
    context_audit.md
    study_notes.md
    quiz_tutor.md
    weekly_heartbeat.md
  memory/
    struggles.md
    mastery.md
    heartbeat_schedule.json
  generated_notes/
    .gitkeep
```

## Notes on Git-ignored Files

The following are intentionally not committed:

- `.env`, because it contains API keys.
- `agent/course_material/*.pdf`, because course PDFs may be private or
  copyrighted.
- `agent/course_material/.document_index.json`, because it is generated.
- `agent/generated_notes/*.md`, because these are user/session artifacts.
- `agent/memory/weekly_reports.md`, because heartbeat reports are generated.

The local memory file `agent/memory/struggles.md` is tracked as a starter file,
but real session entries should be reviewed before committing.

## Assignment Relevance

The system extends a basic AI agent with several IR-oriented context tools:

- document search over local course material;
- optional web retrieval;
- working memory and long-term mastery files;
- conversation-history context for follow-up questions;
- actions that create new study artifacts;
- a context audit layer inspired by OpenClaw-style transparent tool use;
- an opt-in weekly heartbeat that can be scheduled externally.

This means the agent does not only answer from a prompt. It retrieves context,
uses tools, performs actions, updates memory, and exposes how its answer is
grounded.
