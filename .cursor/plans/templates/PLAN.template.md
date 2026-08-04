# Plan: {{PLAN_TITLE}}

- **ID:** {{PLAN_ID}}
- **Status:** draft | awaiting_operator | experts_review | approved | superseded
- **Created:** {{DATE}}
- **Operator:** {{OPERATOR}}
- **Source idea:** {{ONE_LINE_IDEA}}

## 1. Idea formation (with operator)

### 1.1 Problem / opportunity
{{PROBLEM}}

### 1.2 Desired outcome
{{OUTCOME}}

### 1.3 Non-goals
{{NON_GOALS}}

### 1.4 Constraints
{{CONSTRAINTS}}

### 1.5 Operator decisions log
| Date | Question | Decision |
|------|----------|----------|
| {{DATE}} | {{Q}} | {{A}} |

### 1.6 Open questions (blocking)
- [ ] {{Q1}}

> Gate: do not leave this section empty of a resolution path. If any box is unchecked, status must be `awaiting_operator`.

## 2. Expert routing

| Expert | Required? | Why |
|--------|-----------|-----|
| Architect | yes/no | |
| Programmer | yes/no | |
| Telegram | yes/no | |
| Tester | yes/no | |
| Vulnerability Analyst | yes/no | |
| Code Reviewer | yes/no | mandatory if programming in scope |
| Validator | yes (stage gate) | mandatory after PLAN written; not an analysis expert |

## 3. Expert analysis

### 3.1 Architect
{{ARCHITECT_FINDINGS}}

### 3.2 Programmer
{{PROGRAMMER_FINDINGS}}

### 3.3 Telegram
{{TELEGRAM_FINDINGS}}

### 3.4 Tester
{{TESTER_FINDINGS}}

### 3.5 Vulnerability Analyst
{{SECURITY_FINDINGS_OR_N_A}}

### 3.6 Code Reviewer (planning-level, if any)
{{REVIEWER_NOTES_OR_N_A}}

## 4. Synthesis

### 4.1 Recommended approach
{{APPROACH}}

### 4.2 Alternatives considered
{{ALTERNATIVES}}

### 4.3 Risks and mitigations
| Risk | Severity | Mitigation |
|------|----------|------------|
| | | |

### 4.4 Compatibility / versioning impact
- VERSION bump needed?: yes/no — {{SEMVER}}
  - If **yes**: conscious release only (operator intent or this approved plan). Intermediate tasks must keep `VERSION` unchanged.
  - If **no**: do not touch `ConfigData` version fields or add a release section to `CHANGELOG.md`.
- MIN_VERSION impact?: yes/no — {{NOTES}}
- CHANGELOG.md update required?: yes/no (must be **yes** whenever VERSION bump is yes)
- Changelog draft bullets (for `CHANGELOG.md` + release commit; Russian):
  1. {{BULLET}}

### 4.5 Acceptance criteria
- [ ] {{AC1}}

## 5. Operator approval

- **Plan approved:** yes/no
- **Approved at:** {{TIMESTAMP}}
- **Notes:** {{NOTES}}

> Gate: Task splitting must not start until **Plan approved = yes** and section 1.6 has no unchecked blocking questions.

## 6. Validation log

| When | Stage | Verdict | Blocking findings | Notes |
|------|-------|---------|-------------------|-------|
| {{TIMESTAMP}} | idea-to-plan | pass \| pass_with_notes \| fail | {{NONE_OR_LIST}} | {{NOTES}} |

> Gate: next skill **plan-to-tasks** only after last Validator verdict is `pass` or `pass_with_notes`.
