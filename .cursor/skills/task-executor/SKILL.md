---
name: task-executor
description: >-
  Executes all unblocked ready tasks from .cursor/plans/*/BOARD.md (dependency
  order) via expert Task subagents (lead → reviews → Validator → commit per
  task). Continues until the board is drained or a true blocker stops the
  queue. Requires Multitask Mode (/multitask); expert Tasks use
  run_in_background true. Use when the user says execute task, run task,
  implement task, task executor, «исполнитель задач», or names this skill.
---

# Task Executor

## Mandatory reads (first)

1. [../shared/agent-tuning.md](../shared/agent-tuning.md)
2. [../shared/experts.md](../shared/experts.md)
3. Discover boards: list `.cursor/plans/*/BOARD.md` (use Shell/`Get-ChildItem`/`dir` if Glob misses them). Load each task file only when that task is the current execute target
4. Do **not** load sibling task files into the lead brief unless a dependency note is required (one line + path is enough)
5. Working plan/task files must stay **visible on disk** (not gitignored). Still **do not commit** them with product changes.

## Hard rules

- Artifacts / reports in **English**.
- **Drain the ready queue.** Default: execute **all** tasks that are (or become) runnable with no blockers — in dependency order — until none remain or a true blocker stops the board. Do **not** stop after one task and ask “which next?” when the next task is clearly unblocked.
- **Multitask required.** This skill must run in Cursor **Multitask Mode**. The agent **cannot** flip the UI mode via `SwitchMode` (only `plan`/`agent` exist). Enforce the closest equivalent:
  1. **First action:** tell the operator to invoke via `/multitask` (Agents Window) or enable Multitask Mode, then continue with this skill — unless they already did / confirm Multitask is on.
  2. **Every** expert `Task` launch in this skill **must** use `run_in_background: true` (async subagents). Never block the parent on a synchronous expert Task chain when Multitask/background dispatch is available.
  3. Orchestrator stays interactive: monitor completions, then launch the next gated step (review → validator → commit) as further background Tasks when independent, or sequentially only for true dependencies (review needs lead diff; Validator needs reviews; commit needs Validator pass).
- **Execution is expert-only.** The orchestrator must **not** implement the change itself. Launch Task subagents with expert prompts from `experts.md`.
- Pattern: **one lead** delivers; **optional reviewers** follow; **Code Reviewer is mandatory** after any programming/implementation Task.
- **Experts decide** mid-flight routine ambiguities within domain (see `agent-tuning.md`). Set task `blocked` / `awaiting_operator` **only** for true product/policy blockers or Critical unresolved review findings that need a product call — not for every open design detail.
- Stay inside task goal and out of scope. No drive-by refactors.
- Obey project versioning/changelog rules. **Do not** bump `VERSION` / `BUILD_DATE` / `MIN_VERSION` / `CODENAME` or add a `CHANGELOG.md` release section unless the task is an explicit release bump (or the operator ordered a release). On a release task: sync `teleboss/shared/config.py` (`ConfigData`), root `CHANGELOG.md`, and the release commit — **subject must include the new version** (`[update] Обновление до версии X.Y.Z`); never change `VERSION` without putting that version in the same commit message.
- **Prompt hygiene:** pass the **single task file** (+ short board shared context / plan excerpt if needed). Never dump the whole plan’s task set into a subagent prompt.
- **Validator is mandatory** before marking a task `done`. `fail` blocks `done` and **stops the queue** for that board until fixed (dependent tasks must not start).
- **Commit policy:** after Validator `pass` / `pass_with_notes`, create **one git commit per task** (optionally 2–3 if clearly different concerns: product code vs tests vs docs). No commit → task stays not `done`, unless the operator explicitly wrote **skip commit** for that task.
- **Do not commit** `.cursor/plans/` working artifacts (`*-plan.md`, `{{PLAN_ID}}/` boards and task files). Templates + README may be committed when orchestration docs change. Do **not** gitignore working plans — that hides them from agent discovery.
- Commit messages follow the repo Russian `[tag] …` rule.

## Workflow

```text
Execute board:
- [ ] 0. Multitask gate
- [ ] 0b. Discover BOARD(s); build runnable queue (deps done, no blockers)
- [ ] 0c. Loop while runnable tasks exist:
- [ ]     1–10. Run one task end-to-end (lead → reviews → Validator → commit → done)
- [ ]     Refresh BOARD; enqueue newly unblocked tasks
- [ ] 0d. Stop on blocker / empty queue; report summary of all tasks touched
```

Per-task pipeline (steps 1–10):

```text
One task:
- [ ] 1. Load only that task file + BOARD; verify ready + dependencies done
- [ ] 2. Confirm lead + reviewers with operator only if routing unclear
- [ ] 3. Launch lead expert Task (background)
- [ ] 4. If programming: Code Reviewer Task (background)
- [ ] 5. Other reviewers when logical — parallel background when independent
- [ ] 6. Apply Critical must-fixes via lead Task again (background)
- [ ] 7. Update execution/review logs; refresh BOARD index
- [ ] 8. Validator Task (background)
- [ ] 9. On pass: commit(s); Commit log
- [ ] 10. Mark done only when AC + Validator + commit policy satisfied
```

### 0. Multitask gate

Before launching experts:

1. If the operator did **not** start from `/multitask` / Multitask Mode, **stop once** and ask them to re-run: `/multitask` then `/task-executor`. Do not pretend the UI mode was switched.
2. Proceed only after confirmation **or** when the session is already Multitask.
3. From this point: **every** `Task(...)` call sets `run_in_background: true`.

### 0b. Board / queue discovery

1. Enumerate `.cursor/plans/*/BOARD.md` (Shell if needed). Ignore `templates/`.
2. Prefer the board the operator named; else the single `ready`/`in_progress` board; if **multiple** boards are active → ask which Plan ID (board choice only).
3. Never conclude from Glob alone when it only returns `templates/` — verify with Shell first.

### 0c. Drain ready queue (default)

On the chosen board:

1. Build the **runnable set**: status `ready` (or operator override), board/task blocking questions empty, dependencies all `done`, board Validator not `fail`.
2. Order by dependency topology then task ID (`T01`, `T02`, …).
3. **While** the runnable set is non-empty:
   - Take the next task; run the full per-task pipeline (sections 1–8).
   - On `done` + commit: refresh BOARD; add any newly unblocked tasks to the queue.
   - On `blocked` / `awaiting_operator` / Validator `fail` / missing commit: **stop the queue** for this board; report what finished and what is blocked. Do not start dependents.
4. Independent tasks with **no** mutual deps **may** run as parallel background pipelines only when safe (no shared files). Default for chained refactors (T01→T02→…) is **sequential** one task at a time.
5. Ask the operator **only** when: no runnable tasks and none `done` this session; multiple boards; explicit task ID requested that is not runnable; or a true product/policy blocker. Do **not** ask which of several already-runnable chained tasks to pick — drain them in order.

### 1. Preconditions (per task)

Do not start a task if:

- Multitask gate failed (operator refused and no Multitask session)
- task status is not `ready` (or operator explicitly overrides in writing)
- blocking questions exist on the task or board
- dependencies are not `done` (check BOARD index / dependency task status headers only)
- board-level Validator for `plan-to-tasks` last failed (fix board first)

### 2. Brief for the lead Task

Pass to the subagent:

- expert prompt from `experts.md`
- **this task file’s full content** (goal, out of scope, AC, notes)
- short board shared-context excerpt if present
- plan synthesis excerpt if needed (not the entire plan dump)
- instruction to return: changes made, verification performed, residual risks, decisions made; open questions only if true blockers

Use `generalPurpose` (or `explore` only for read-only investigation). For shell-heavy ops, `shell` is allowed as a helper under the lead’s direction — still framed as that expert’s work. Always `run_in_background: true`.

### 3. Reviews

After a Programmer lead completes code changes:

1. **Code Reviewer Task** — must review the actual diff; Critical items block `done`.
2. **Tester Task** — when behavior or structure changed: **write and run executable tests** (prefer lasting tests under `tests/` or repo convention; report command + exit code). Narrative gap lists alone are not enough; live Telegram residuals do not replace automatable coverage.
3. **Security Task** — when the task or plan routed Vulnerability Analyst.
4. **Architect Task** — when structure/boundaries changed.

Launch independent reviewers **in parallel** (multiple background Tasks in one turn). Reviewers do not become a second implementer unless the lead is re-launched to apply must-fixes.

### 4. Operator gate

If any expert returns **blocking** product/policy questions or Critical unresolved findings that need a product call → notify operator, update logs, **stop the queue**, wait. Routine tech choices resolved by experts go into the execution log, not the operator queue.

### 5. Update artifacts

In the **task file** (not a monolithic dump):

- append execution log and review log rows
- check off acceptance criteria only when verified
- update `BOARD.md` index status for this ID
- do **not** set `done` yet — run Validator, then commit (steps 6–7)

### 6. Validator gate

Launch a **Validator** Task with the prompt from `experts.md`, plus:

- paths to PLAN, `BOARD.md`, **this task file only**, and evidence pointers
- stage = `task-executor`
- instruction: full three-layer check; AC checked only with evidence; mandatory reviews present; Criticals closed or fail; confirm prompt hygiene (sibling task bodies not required)

Use `run_in_background: true`. Record the return in that task’s **Validation log**.

- `fail` → set `blocked` (or keep `in_progress`), apply required fixes, re-validate; never mark `done` on fail; **do not advance the queue**
- `pass` / `pass_with_notes` → proceed to commit step

### 7. Commit (required unless operator skipped)

After Validator pass:

1. Stage **product** changes for this task only (exclude secrets and `.cursor/plans/` artifacts).
2. Create **one** commit with a Russian `[tag] …` message matching the task outcome (prefer `[refactor]` / `[fix]` / `[update]` / … per repo rules). Split into at most 2–3 commits only when concerns clearly differ.
3. Record SHA + message in the task **Commit log**.
4. If the operator wrote **skip commit** → note that in Commit log and Validation notes; then `done` is allowed without a SHA.

Missing commit without skip → treat as incomplete: do **not** mark `done`; **stop the queue**.

### 8. Status after validation + commit

Set status `done` | `blocked` | `awaiting_operator` per gates above. Sync BOARD index.

If `done` → continue §0c with the next runnable task.

Do not mark done on narrative confidence alone — require verification, Validator pass, and commit policy.

## Anti-patterns

- Orchestrator quietly editing code “to save a round trip”
- Stopping after one successful task when more runnable tasks exist with no blockers
- Asking the operator which chained ready task to run next instead of draining in dependency order
- Running expert Tasks synchronously (`run_in_background: false`) when Multitask/background is available
- Claiming Multitask was enabled without operator `/multitask` / confirmation
- Declaring “no ready tasks” after seeing only `templates/` without Shell-listing `.cursor/plans/*/BOARD.md`
- Gitignoring working plans (breaks discovery)
- Skipping Code Reviewer after programming
- Skipping Tester write/run of executable tests after behavior/structure-changing programming
- Skipping Validator or ignoring `fail`
- Starting a dependent task while its dependency is not `done`
- Marking done with failing or unrun critical checks
- Marking done without commit (unless operator skip)
- Committing `.cursor/plans/` working artifacts or secrets
- Feeding the full multi-task dump into a subagent prompt
- Expanding into adjacent tasks without operator approval
- Parking on routine design questions experts should decide from repo + rules

## Done criteria (session)

- Multitask gate satisfied; expert Tasks launched with `run_in_background: true`
- Every runnable task either `done` (AC + Validator + commit) or queue stopped on a documented blocker
- BOARD index updated for all touched tasks
- Operator given a short summary: completed IDs + commits, remaining/blocked IDs, next action if any
