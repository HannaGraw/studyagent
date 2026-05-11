# Context Audit Skill

Use this skill on every turn to make the agent's context choices visible.

Purpose:

- Show which sources the agent used before answering.
- Explain why web search was or was not used.
- Separate course material, web context, memory, and conversation history.
- Make the agent more trustworthy than opaque multi-tool agents.

OpenClaw-inspired motivation:

OpenClaw-style agents combine memory, skills, tools, and external actions. That
power can make answers hard to trace. This skill adds a lightweight provenance
layer for an educational IR agent: the student can inspect the context pipeline
before trusting the answer.

Workflow:

1. Retrieve course context.
2. Optionally run web search when local context is weak or explicitly requested.
3. Read memory and recent conversation history.
4. Build an audit with `tools.context_audit.build_context_audit`.
5. Print the audit before the answer or action result.
6. Include the audit in the model prompt so the answer aligns with the visible
   provenance report.

Audit fields:

- Course retrieval: number of chunks, best score, and sources.
- Web search: whether it was skipped, used, or failed.
- Memory: whether stored student memory was included.
- Conversation history: whether recent turns helped interpret the prompt.
- Planned grounding: course material, web context, both, or insufficient context.
