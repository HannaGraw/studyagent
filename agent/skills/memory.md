# Memory Skill

Use this skill to preserve useful context about the student's learning process
across turns.

Purpose:

- Remember repeated questions, confusion, weak retrieval cases, and topics that
  needed web fallback.
- Give the tutor a compact memory excerpt before answering.
- Keep memory human-readable in `agent/memory/struggles.md`.

Read rule:

1. Before calling the chat model, read recent memory with
   `tools.update_memory.read_memory`.
2. Include the memory excerpt separately from retrieved course and web context.
3. Use memory only to adapt tutoring style and follow-up focus; do not treat it
   as a source of course facts.

Update rule:

1. Update memory after an answer when the student shows confusion, repeats a
   question, states a learning preference or struggle, needs external web
   context, or gets weak/no retrieved context.
2. Store the reason, student question, and a short tutor response summary.
3. Do not store API keys or private unrelated information.
