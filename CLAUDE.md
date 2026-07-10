# Project Instructions

## Project Context
- This is a greenfield side project.
- Unless the user explicitly says otherwise, there are no backwards-compatibility requirements.

## Workflow
- Plans live in `.plans/`, should be committed, and should be named with implementation-order prefixes like `01-auth.md`, `02-billing.md`, and `03-dashboard.md`.
- Multi-agent reviews live in `.reviews/`; the directory is kept with `.gitkeep`, but review outputs are ignored by default.
- Generated HTML artifacts live in `.html/`, which is gitignored; they are local-only design, planning, or review aids and are not committed.
- Keep `README.md` current with the minimum context needed to run and understand the project.
## Project Learnings
Agents should capture durable project learnings when they discover a non-obvious pattern, pitfall, user preference, architecture constraint, tool behavior, or workflow fix that would save future agents time.

Do not add every lesson directly to this file. Prefer appending a structured learning record to `.agent/learnings.jsonl`. The user will periodically review those records and promote important ones into this file.

Use this JSONL shape:

```json
{"skill":"review","type":"pitfall","key":"short-stable-key","insight":"Actionable rule future agents should follow.","confidence":8,"source":"observed","files":["path/to/relevant-file"]}
```

Types: `pattern`, `pitfall`, `preference`, `architecture`, `tool`, `operational`, `investigation`.

Sources: `observed`, `user-stated`, `inferred`, `cross-model`.

Confidence: 1-10. Use 8-9 for verified observations, 4-5 for uncertain inference, and 10 for explicit user-stated preferences.

Only log learnings that are reusable, specific, and likely to prevent a future mistake. Do not log obvious facts, one-off transient errors, or broad preferences inferred without evidence.

## Development
- Prefer the simplest implementation that satisfies the current product intent.
- Every implementation step must end with passing verification.
- Write tests for behavior that would be expensive or risky to verify manually.
- Run the relevant tests, typecheck, and lint before declaring work complete.
