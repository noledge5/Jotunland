# Grill Me

Quiz the user on a topic with a rapid-fire Q&A session. Ask one question at a time, wait for an answer, then give brief feedback before moving to the next question.

## Usage

```
/grill-me <topic> [--questions <n>]
```

- `<topic>` — what to be quizzed on (e.g. "React hooks", "SQL joins", "git rebasing")
- `--questions <n>` — number of questions (default: 5)

## Behavior

1. Announce the topic and number of questions.
2. For each question:
   - Ask a clear, specific question about the topic (mix conceptual, practical, and edge-case questions).
   - Wait for the user's answer.
   - Give a one-sentence verdict ("Correct!", "Close — …", or "Not quite — …") and the correct answer if they missed it.
3. After all questions, print a score summary (e.g. "4/5 — solid understanding") and one sentence on what to review if any were missed.

## Rules

- Never reveal the answer before the user responds.
- Vary difficulty: start easy, ramp up.
- Keep questions unambiguous — one right answer per question.
- Do not repeat questions within a session.
