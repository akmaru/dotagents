---
name: grill-me
description: Interview the user relentlessly about a plan or design until reaching shared understanding, resolving each branch of the decision tree. Use when user wants to stress-test a plan, get grilled on their design, or mentions "grill me".
compatibility: Designed for Claude Code and OpenCode
---

Interview the user about their plan or design through focused, one-at-a-time questioning using the AskUserQuestion tool.

## Rules

- Always use `AskUserQuestion` tool — never ask questions as plain text
- Ask exactly one question at a time; wait for the answer before proceeding
- Provide 2–4 concrete multiple-choice options representing the most realistic answers for the specific context
- After each answer, acknowledge briefly (1–2 sentences), then immediately ask the next question
- Explore the codebase or files yourself rather than asking the user to describe them
- Continue until all branches of the decision tree are resolved
- Conclude with a concise summary of all decisions made

## Workflow

1. Start by asking what plan or design to grill
2. Identify the key decision points and unknowns
3. Work through each branch systematically
4. Summarize all resolved decisions at the end
