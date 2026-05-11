"""
Context audit tool for the tutor agent.

This tool makes the agent's context pipeline inspectable: local retrieval,
web fallback, memory, and conversation history are summarized before the model
answers. It is inspired by layered agent systems where tools and memory can make
answers hard to trace unless provenance is shown explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ContextAudit:
    """A compact provenance report for one agent turn."""

    course_status: str
    web_status: str
    memory_status: str
    history_status: str
    grounding: str


def build_context_audit(
    chunks: list,
    web_results: list | None = None,
    web_reason: str | None = None,
    memory_text: str = "",
    conversation_history: list[dict[str, str]] | None = None,
    follow_up_used: bool = False,
    fallback_reason: str = "",
) -> ContextAudit:
    """Summarize which context sources were used and why."""

    web_results = web_results or []
    conversation_history = conversation_history or []

    if chunks:
        best_score = max(chunk.score for chunk in chunks)
        sources = sorted({chunk.source for chunk in chunks})
        course_status = (
            f"used {len(chunks)} chunk(s), best score {best_score:.4f}, "
            f"sources: {', '.join(sources)}"
        )
    else:
        course_status = "not used; no local chunks found"

    if web_results:
        web_status = f"used {len(web_results)} result(s)"
        if fallback_reason:
            web_status += f" because {fallback_reason}"
    elif web_reason:
        web_status = f"attempted but no context retrieved: {web_reason}"
    elif not chunks:
        web_status = "not used; no web fallback was attempted"
    else:
        web_status = "not used; local context was considered sufficient"

    if memory_text and "No memory recorded yet." not in memory_text:
        memory_status = "used recent student memory"
    else:
        memory_status = "not used; no stored memory yet"

    if conversation_history:
        history_status = f"used {min(len(conversation_history), 4)} recent turn(s)"
        if follow_up_used:
            history_status += " to interpret a follow-up"
    else:
        history_status = "not used; no previous turns in this session"

    if chunks and web_results:
        grounding = "course material plus external web context"
    elif chunks:
        grounding = "course material"
    elif web_results:
        grounding = "external web context"
    else:
        grounding = "insufficient retrieved context"

    return ContextAudit(
        course_status=course_status,
        web_status=web_status,
        memory_status=memory_status,
        history_status=history_status,
        grounding=grounding,
    )


def format_context_audit(audit: ContextAudit) -> str:
    """Render the audit for terminal output and model context."""

    return (
        "Context audit:\n"
        f"- Course retrieval: {audit.course_status}\n"
        f"- Web search: {audit.web_status}\n"
        f"- Memory: {audit.memory_status}\n"
        f"- Conversation history: {audit.history_status}\n"
        f"- Planned grounding: {audit.grounding}"
    )
