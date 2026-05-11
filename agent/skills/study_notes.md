# Study Notes Skill

Use this skill when the student asks to create, save, organize, or generate
study notes, exam notes, summaries, practice questions, or learning materials
from the course content.

Purpose:

- Turn retrieved course material into a reusable Markdown study artifact.
- Include concise explanations, examples, diagrams, and practice questions.
- Save generated notes in `agent/generated_notes/` so the student can review
  them later.

Activation examples:

- "Create study notes about BM25"
- "Make exam notes for embeddings"
- "Generate practice questions about AI agents"
- "Summarize lecture 6 as study notes"

Workflow:

1. Extract the requested topic from the student's message.
2. Retrieve course chunks for that topic first.
3. Use web search only when local retrieval is weak or missing.
4. Ask the model to generate Markdown study notes from the retrieved context.
5. Save the note with `tools.create_study_notes.create_study_note`.
6. Tell the student where the note was saved and whether it used course
   material, web context, or both.

Note template:

- Title and one-sentence summary.
- Source note explaining whether context came from course material or web.
- Key concepts with short explanations.
- Mermaid diagram when useful.
- Concrete examples.
- Summary table.
- Practice questions with brief answers.
- Related topics to review next.
