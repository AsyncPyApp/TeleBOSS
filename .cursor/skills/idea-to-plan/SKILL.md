---
name: idea-to-plan
description: >-
  Turns an operator idea into a structured PLAN.md via discussion gates and
  domain Task subagents (Architect, Programmer, Telegram, Tester, Security,
  Code Reviewer), then a mandatory Validator gate. Use when the user says
  idea to plan, from idea to plan, «из идеи в план», draft a plan, or names
  this skill.
---

# Idea → Plan

## Mandatory reads (first)

1. [../shared/agent-tuning.md](../shared/agent-tuning.md)
2. [../shared/experts.md](../shared/experts.md)
3. Template: [../../plans/templates/PLAN.template.md](../../plans/templates/PLAN.template.md)

## Hard rules

- Artifacts and skill outputs are **English**.
- **Do not invent facts.** Ground in repo + operator answers.
- **Experts decide** routine design/tech ambiguities within their domain (see `agent-tuning.md`). Escalate to the operator **only** for true product/policy blockers. Prefer deciding and documenting assumptions over parking the plan.
- On **blocking** product/policy questions only → set status `awaiting_operator`, list those questions, **stop**.
- Expert work runs via **Task subagents** with prompts from `experts.md` — not as a vague single reply pretending to be all roles.
- Orchestrator synthesizes; experts analyze. Do not implement code in this skill.
- **Validator is mandatory** before telling the operator the plan is ready for `plan-to-tasks`. `fail` blocks completion.
- Working plan files under `.cursor/plans/` stay on disk and must **not** be gitignored (agents need Glob/Shell discovery). Do **not** stage working `*-plan.md` / `{{PLAN_ID}}/` in product commits; templates + README are fine to commit with orchestration changes.

## Workflow

Copy and track:

```text
Idea→Plan:
- [ ] 1. Form idea with operator (section 1)
- [ ] 2. Route experts (section 2)
- [ ] 3. Launch Task subagents for required experts
- [ ] 4. Fill section 3 from subagent returns
- [ ] 5. Synthesize section 4
- [ ] 6. Resolve only blocking operator questions (if any)
- [ ] 7. Operator approves plan (section 5)
- [ ] 8. Write PLAN file under .cursor/plans/
- [ ] 9. Launch Validator Task; record Validation log; fix and re-validate on fail
```

### 1. Idea formation (operator discussion)

Interview the operator until section 1 of the template is solid:

- problem, outcome, non-goals, constraints
- decisions log for every trade-off answered

If anything **product-critical** is missing → questions only; do not invent scope. Do not re-ask settled decisions.

### 2. Expert routing

Use the selection matrix in `experts.md`.

- Include **Code Reviewer** if programming will be in scope later (planning-level review of approach is enough here).
- Include **Vulnerability Analyst** only when the matrix says so (auth, votes, tokens, plugins, trust boundaries, etc.).
- **Validator** is not part of routing for analysis — it runs as the stage gate in step 9.

Announce the chosen set and why. If operator disagrees, adjust before launching Tasks.

### 3. Launch Task subagents

For each required expert, start a Task (`subagent_type`: `generalPurpose` unless a better fit exists) with:

- the expert prompt from `experts.md`
- the current idea + constraints + relevant file paths
- instruction: return findings, recommended approach, risks; **decide** routine questions themselves; escalate only true blockers; no implementation

Prefer **parallel** Tasks when experts do not depend on each other.

### 4–5. Fill analysis + synthesis

Merge returns into the PLAN template. Deduplicate. Keep conflicting expert views visible with a recommended resolution — if experts disagree and evidence + project rules cannot resolve it, ask the operator (blocker only).

Instruct experts (and yourself as synthesizer) to record decisions/assumptions in section 3–4 rather than leaving open questions for routine tech choices.

Fill versioning subsection (§4.4) when behavior/compatibility may change (see project versioning rule). Default to **no** VERSION bump unless the operator wants a release or the change truly needs SemVer. If bump = yes: draft Russian changelog bullets for root `CHANGELOG.md` **and** the release commit; mark `CHANGELOG.md update required?: yes`.

### 6–7. Gates

1. **Questions gate:** only true product/policy blockers → `awaiting_operator` and wait. Routine design/tech items must be decided by experts and logged.
2. **Approval gate:** explicit operator **Plan approved = yes** required before `plan-to-tasks`. Do not invent approval.

### 8. Persist artifact

Write:

`.cursor/plans/{{PLAN_ID}}-plan.md`

`PLAN_ID` suggestion: `YYYYMMDD-short-slug` (ASCII).

### 9. Validator gate

Launch a **Validator** Task with the prompt from `experts.md`, plus:

- path to the written PLAN
- stage = `idea-to-plan`
- instruction: read-only; process + rules depth (light evidence that expert returns were synthesized)

Record the return in the PLAN **Validation log**.

- `pass` / `pass_with_notes` → tell the operator the path and that the next skill is **plan-to-tasks**
- `fail` → apply required fixes (or re-run domain experts), update the PLAN, re-launch Validator; do **not** claim ready for `plan-to-tasks`

## Done criteria

- PLAN file exists from template with all sections filled or `N/A` + reason
- No blocking open questions (routine decisions documented instead)
- Operator approval recorded
- Expert set documented
- Validator verdict `pass` or `pass_with_notes` recorded in Validation log
