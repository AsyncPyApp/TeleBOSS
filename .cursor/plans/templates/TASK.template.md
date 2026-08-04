# {{TASK_ID}} — {{TITLE}}

- **Plan ID:** {{PLAN_ID}}
- **Board:** `BOARD.md` (same directory)
- **Status:** draft | awaiting_operator | ready | in_progress | blocked | done
- **Lead expert:** {{LEAD}}
- **Reviewers:** {{REVIEWERS_OR_NONE}}
- **Depends on:** {{IDS_OR_NONE}}
- **Domain scope:** only what this lead owns; do not expand

### Context (deepened by domain experts)

{{CONTEXT}}

### Goal

{{GOAL}}

### Out of scope

{{OUT_OF_SCOPE}}

### Implementation notes (facts only)

{{NOTES}}

### Acceptance criteria

- [ ] {{AC1}}

### Test notes (Tester)

Executable coverage expected at execute time (paths/commands); residual live-Telegram only if not automatable:

{{TEST_NOTES}}

### Security notes (if routed)

{{SEC_NOTES_OR_N_A}}

### Open questions

- [ ] {{Q}}

### Execution log

| When | Expert | Result |
|------|--------|--------|
| | | |

### Review log

| When | Reviewer | Verdict |
|------|----------|---------|
| | | |

### Validation log

| When | Stage | Verdict | Blocking findings | Notes |
|------|-------|---------|-------------------|-------|
| | task-executor | pass \| pass_with_notes \| fail | | |

> Gate: task status `done` only after last Validator verdict is `pass` or `pass_with_notes`, AC are evidenced, and the task commit policy is satisfied (see task-executor).

### Commit log

| When | Commit | Message |
|------|--------|---------|
| | {{SHA_OR_PENDING}} | `[tag] …` |
