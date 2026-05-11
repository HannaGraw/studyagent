# Quiz Tutor Skill

Use this skill when the student asks to be quizzed, tested, drilled, or given
practice questions that should be answered interactively.

Purpose:

- Turn retrieved context into a short diagnostic quiz.
- Grade the student's next answer.
- Track concept mastery in `agent/memory/mastery.md`.
- Help the student discover knowledge gaps rather than only receive summaries.

Activation examples:

- "Quiz me on BM25"
- "Test me on AI agents"
- "Drill me on embeddings"
- "Give me a short quiz about traditional information retrieval"

Workflow:

1. Extract the quiz topic from the student request.
2. Retrieve course context first, with web fallback if needed.
3. Generate a short quiz of 3 questions.
4. Store the generated quiz as pending in the current session.
5. Treat the student's next non-command message as their quiz answer.
6. Grade the answer using the original quiz, source context, memory, and recent
   conversation history.
7. Update `agent/memory/mastery.md` with the topic, score, status, and error
   notes.

Mastery labels:

- weak: major gaps or many missing answers.
- developing: partial understanding with fixable mistakes.
- strong: mostly correct.
- mastered: correct, concise, and transferable understanding.
