# Web Search Skill

Use this skill only when local course-material retrieval returns no useful
context.

Purpose:

- Retrieve external context from the web as a fallback IR method.
- Keep course material as the primary source of truth.
- Clearly label web context as external and non-course-based.

Activation rule:

1. Search `agent/course_material/` first.
2. If no local chunks are found, or the best local score is below
   `LOCAL_CONTEXT_MIN_SCORE`, call `tools.web_search.search_web`.
3. If the student explicitly asks for web search, reuse the previous substantive
   question as the search query.
4. If web results are found, pass them to the model as external context.
5. The final answer must state that the information came from web search, not
   from the uploaded course material.

Configuration:

- `TAVILY_API_KEY` enables Tavily web search.
- `WEB_SEARCH_ENABLED=false` disables the skill even when a key is present.
- `TAVILY_SEARCH_DEPTH` is optional and defaults to `basic`.
- `LOCAL_CONTEXT_MIN_SCORE` controls when local retrieval is considered weak.
