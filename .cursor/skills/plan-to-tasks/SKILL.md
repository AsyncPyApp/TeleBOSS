---
name: plan-to-tasks
description: >-
  Splits an approved PLAN.md into a tasks board (BOARD.md) plus one file per
  task using domain Task subagents that only deepen their own areas, then a
  mandatory Validator gate. Use when the user says split the plan, break into
  tasks, plan to tasks, «разбить план на задачи», or names this skill.
---

# Plan → Tasks

## Mandatory reads (first)

1. [../shared/agent-tuning.md](../shared/agent-tuning.md)
2. [../shared/experts.md](../shared/experts.md)
3. The approved plan under `.cursor/plans/`
4. Templates: [../../plans/templates/BOARD.template.md](../../plans/templates/BOARD.template.md), [../../plans/templates/TASK.template.md](../../plans/templates/TASK.template.md)

## Hard rules

- Artifacts in **English**.
- Start only if the plan has **Plan approved = yes** and no blocking questions. Otherwise send the operator back to `idea-to-plan`.
- Experts **only** refine their domains. No cross-domain speculation.
- **Experts decide** routine task-detail ambiguities within domain (see `agent-tuning.md`). Escalate **only** true product/policy blockers → `awaiting_operator`. Do not park the backlog on every underspecified tech detail.
- Splitting is done with **Task subagents** (prompts from `experts.md`), not by a single generalist inventing the full backlog alone.
- Do not implement code here.
- **One task = one file.** Never put full task bodies into a single monolithic `*-tasks.md`. Board holds index + shared gates only.
- **Validator is mandatory** before claiming the board is ready for `task-executor`. `fail` blocks `ready` / next skill.
- Plan/task working files under `.cursor/plans/` must **not** be gitignored (discovery). Do **not** stage them in product commits; templates + README may be committed with orchestration docs.

## Workflow

```text
Plan→Tasks:
- [ ] 1. Load approved plan; verify gates
- [ ] 2. Draft coarse task slices (orchestrator, minimal)
- [ ] 3. For each slice, launch domain lead Task (+ reviewers if logical)
- [ ] 4. Experts deepen context, acceptance, tests/security notes (decide routine details)
- [ ] 5. Ask operator only about blocking product/policy questions
- [ ] 6. Write BOARD.md + one T0x-*.md per task; set ready only when unblocked
- [ ] 7. Launch Validator Task; record board Validation log; fix and re-validate on fail
```

### 1. Verify plan gates

Refuse to split if:

- plan missing / not approved
- plan status is `awaiting_operator`
- blocking questions remain in plan §1.6
- plan Validation log shows last Validator verdict `fail` (re-run idea-to-plan Validator first)

### 2. Coarse slices (orchestrator)

Propose a short task list from plan acceptance criteria and synthesis only:

- one primary outcome per task
- explicit lead expert per task
- dependencies
- reviewers: **Code Reviewer required** if lead is Programmer / implementation; Security reviewer if plan routed security
- short ASCII slug per task for the filename

Show the coarse list to the operator if structure is non-obvious; otherwise proceed and still surface **blocking** questions later if any.

### 3–4. Domain deepening via Task subagents

For each coarse task, launch Task(s):

1. **Lead** expert — deepen context, goal, out of scope, implementation notes (facts from repo), acceptance criteria. Decide routine details; document assumptions.
2. **Optional reviewers** — Tester always when behavior/structure changes (Test notes must name expected **executable** coverage and commands, not docs-only checklists); Security when routed; Architect when cross-module; Code Reviewer reviews the *task spec quality* for implementation tasks (completeness, testability), not code yet.

Pass to each subagent **only**: the plan synthesis excerpt they need + that task’s draft — **not** the full board of other tasks.

Each subagent must:

- stay in domain
- read cited files when claiming behavior
- **decide** naming, split boundaries, test details, import defaults when constraints are known
- return numbered open questions **only** for true product/policy blockers (or "none")

### 5. Operator gate

Aggregate **blocking** open questions into `BOARD.md`. Wait until answered. Update the relevant task file(s) with decisions. Do not list routine expert decisions as operator questions.

### 6. Persist artifacts (split files)

Create directory:

`.cursor/plans/{{PLAN_ID}}/`

Write:

1. `BOARD.md` — from board template: status, blocking questions, short shared context, Validation log, **task index only** (with `File` column).
2. `T{{NN}}-{{slug}}.md` — one file per task from task template. No other task’s body in that file.

Link the board back to `.cursor/plans/{{PLAN_ID}}-plan.md`.

Status `ready` only when no blocking questions remain **and** Validator has not failed (step 7).

**Forbidden:** a single `{{PLAN_ID}}-tasks.md` that concatenates all task bodies.

### 7. Validator gate

Launch a **Validator** Task with the prompt from `experts.md`, plus:

- paths to PLAN, `BOARD.md`, and the tasks directory
- stage = `plan-to-tasks`
- instruction: read-only; process + rules; every index row has a matching task file; each task file has lead, goal, out of scope, AC, deps; Code Reviewer listed for programming tasks; no monolithic tasks dump

Record the return in the board **Validation log**.

- `pass` / `pass_with_notes` → set board `ready` if otherwise unblocked; tell the operator the directory path; next skill is **task-executor**
- `fail` → keep status below `ready`, fix gaps, re-launch Validator

## Task quality bar

Each task file must have:

- single lead expert
- clear goal + out of scope
- acceptance criteria checkboxes
- dependency IDs
- empty or resolved open questions (blockers only)

Reject mega-tasks that mix unrelated domains — split further.

## Done criteria

- `BOARD.md` + one file per task under `.cursor/plans/{{PLAN_ID}}/`
- Every task has lead (+ Code Reviewer listed for programming tasks)
- No blocking questions
- Validator verdict `pass` or `pass_with_notes` on the board
- Operator informed of path; next skill is **task-executor**
