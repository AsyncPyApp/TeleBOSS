# Tasks board: {{PLAN_TITLE}}

- **Plan ID:** {{PLAN_ID}}
- **Plan file:** `.cursor/plans/{{PLAN_ID}}-plan.md`
- **Tasks dir:** `.cursor/plans/{{PLAN_ID}}/`
- **Status:** draft | awaiting_operator | ready | in_progress | done
- **Created:** {{DATE}}

## Open questions (blocking)

- [ ] {{Q1}}

> Gate: no task may move to `ready`/`in_progress` while blocking questions remain.

## Shared context (board-only)

{{SHARED_GATES_AND_DECISIONS_OR_N_A}}

> Keep this short. Per-task details live in individual task files — do not paste full task bodies here.

## Validation log (board)

| When | Stage | Verdict | Blocking findings | Notes |
|------|-------|---------|-------------------|-------|
| {{TIMESTAMP}} | plan-to-tasks | pass \| pass_with_notes \| fail | {{NONE_OR_LIST}} | {{NOTES}} |

> Gate: board status `ready` and **task-executor** only after last board Validator verdict is `pass` or `pass_with_notes`.

## Task index

| ID | Title | File | Lead expert | Reviewers | Depends on | Status |
|----|-------|------|-------------|-----------|------------|--------|
| T01 | {{TITLE}} | `T01-{{slug}}.md` | Programmer | Code Reviewer | — | draft |

> One row per task. Body of each task is **only** in its file under this directory.
