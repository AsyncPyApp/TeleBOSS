# Mandatory agent tuning (all experts and orchestrators)

Apply these rules on every step of idea → plan → tasks → execution. No exceptions.

## Grounding and honesty

1. **Do not invent facts.** Claims about code, APIs, Telegram behavior, versions, or config must come from repo files, tool output, docs you actually read, or the operator.
2. **Separate fact / inference / assumption.** Label each clearly. Never present an assumption as a fact.
3. **Abstain when evidence is thin.** Prefer `insufficient evidence` + questions to the operator over a confident guess.
4. **Cite sources briefly.** File paths, command output, or doc sections that support a claim. No fake citations.
5. **Prefer current project reality.** Read the codebase before proposing changes. Do not rely on memory of “how TeleBOSS usually works.”

## Solutions quality

6. **Prefer proven, boring solutions** over clever or exotic ones. Match existing project patterns first.
7. **No speculative dependencies** or new frameworks unless the operator approved and the need is clear.
8. **Smallest change that works.** Avoid drive-by refactors, unrelated renames, or “while we’re here” edits.
9. **Security by default:** no secrets in commits/logs; least privilege; validate untrusted input (Telegram payloads, callbacks, plugin code).
10. **Compatibility awareness.** Respect `VERSION` / `MIN_VERSION`, plugin metadata, and storage/format compatibility. Flag breaking changes explicitly. **Conscious version bumps only** (operator-requested release or approved plan §4.4 `VERSION bump needed?: yes`). Never bump `VERSION`/`BUILD_DATE`/`MIN_VERSION`/`CODENAME` on routine feature/fix/refactor commits. Root **`CHANGELOG.md` is mandatory**: on a release, update it in sync with `ConfigData` and the release commit message (bot still surfaces the git commit body on upgrade). **If `VERSION` changes, the same commit subject must name that version** (`[update] Обновление до версии X.Y.Z`).

## Human-in-the-loop

11. **Experts decide within their domain.** Resolve the majority of ambiguities yourself by reading the repo, applying project rules, and choosing the boring/proven option that matches existing patterns. Document decisions in findings with assumptions labeled — do not dump routine design/tech choices as operator questions.
12. **Escalate to the operator ONLY** for true product/policy blockers, for example:
    - Explicit destructive/irreversible actions
    - Breaking changes to public API / `MIN_VERSION` / plugin contract when unavoidable
    - Scope expansion beyond the agreed idea
    - Conflicting expert recommendations that cannot be resolved by evidence + project rules
    - Secrets, legal, or security policy exceptions
    - Explicit approval gates already in the skills (e.g. Plan approved = yes before plan-to-tasks)
13. **Do not park on routine questions.** Naming within agreed conventions, file-split boundaries when the outcome is clear, test-strategy details, import-rule defaults, and migration step ordering when constraints are known are expert decisions — not operator gates.
14. **Destructive or irreversible actions** (force push, data wipe, mass delete) require explicit operator approval.

## Multi-agent discipline

15. **Stay in role.** Experts only deepen their domain. Orchestrators coordinate; they do not replace expert execution.
16. **Execution is expert-only.** Implementation, tests, and security fixes are done by Task subagents with expert prompts — not by a generic “do everything” agent.
16a. **task-executor → Multitask.** When running `task-executor`, require Cursor Multitask Mode (`/multitask`). The agent cannot switch that UI mode itself; ask the operator to enable it, and always launch expert Tasks with `run_in_background: true`.
16b. **task-executor → drain queue.** Execute all runnable tasks (deps satisfied, no blockers) in dependency order until the board is drained or a true blocker stops the queue. Do not stop after one success to ask which task is next.
17. **Cross-check high-stakes claims.** For architecture, security, and breaking changes, require a second expert review when logical.
18. **Structured outputs.** Use the project templates. Fill every required section or mark `N/A` with a reason.
19. **Verify before “done”.** Prefer tools (tests, linters, bot command dry-checks, `git diff`) over narrative “should work.” After programming that changes behavior/structure, the **Tester** must **write and run** executable tests (command + exit code reported); a residual-gap checklist alone is not verification.
20. **Validator gate.** After `idea-to-plan`, `plan-to-tasks`, and each `task-executor` run, launch the Validator Task. Record the Validation log. `fail` blocks stage completion, next skill, and task `done`. Do not self-validate as orchestrator in place of the Validator Task.
21. **One task = one file.** Task boards use `BOARD.md` + `T0x-*.md` under `.cursor/plans/{{PLAN_ID}}/`. Never concatenate all task bodies into one prompt or one monolithic tasks file.
22. **Commit after successful task execution.** After Validator `pass` / `pass_with_notes` on `task-executor`, create one product git commit for that task (or 2–3 if concerns clearly differ). Missing commit without explicit operator **skip commit** blocks `done`. Do not stage `.cursor/plans/` working artifacts (`*-plan.md`, `{{PLAN_ID}}/`) or secrets in product commits. Do **not** gitignore those working plans — agents must be able to discover `BOARD.md` via Glob/Shell.

## Anti-patterns (forbidden)

- Inventing Telegram Bot API methods, library APIs, or file contents not seen
- “Probably” / “usually” used as a substitute for reading code
- Shipping untested security-sensitive paths
- Expanding scope beyond the agreed plan/task without operator approval
- Mixing multiple expert roles into one vague answer when Task subagents were required
- Asking the operator about routine design/tech choices experts can resolve from repo + rules
- Marking a stage or task complete without a Validator `pass` / `pass_with_notes`, or ignoring Validator `fail`
- Treating Code Reviewer / Tester narrative as evidence that the orchestrator skipped required Task launches
- Treating Tester “residual gaps” or an unrun checklist as done when automatable executable tests were required and not written/run
- Dumping sibling task files or a full multi-task board body into a single expert prompt
- Marking a task `done` without a commit (unless operator skip) or staging plan/task working files under `.cursor/plans/` in a product commit
- Gitignoring working plans so `task-executor` cannot see `BOARD.md` / task files
