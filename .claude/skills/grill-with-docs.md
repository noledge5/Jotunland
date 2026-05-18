# Grill With Docs

Quiz the user on content from a specific documentation source — a URL, a local file, or pasted text. All questions are derived strictly from the provided material.

## Usage

```
/grill-with-docs <source> [--questions <n>]
```

- `<source>` — a URL, a file path, or the word `paste` (to paste doc text inline)
- `--questions <n>` — number of questions (default: 5)

## Behavior

1. Fetch or read the source:
   - URL → use WebFetch to retrieve the page content.
   - File path → read the file.
   - `paste` → ask the user to paste the content, then proceed.
2. Announce what was loaded (title or filename) and the number of questions.
3. For each question:
   - Generate a question that can be answered from the loaded content alone.
   - Wait for the user's answer.
   - Give a one-sentence verdict and cite the relevant section/line from the docs if the user was wrong.
4. After all questions, print a score summary and name any sections worth re-reading.

## Rules

- Only ask questions answerable from the provided source — no outside knowledge.
- Quote or cite the relevant part of the docs when giving feedback.
- Never reveal the answer before the user responds.
- Vary question types: definitions, how-to steps, gotchas, comparisons.
