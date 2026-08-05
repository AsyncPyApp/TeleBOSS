# Plans

Working plans and task boards for the idea → plan → tasks → execute workflow.

**Commit policy:** commit `README.md` + `templates/` + `BACKLOG.md` when changing orchestration docs. Do **not** stage working `*-plan.md` or `{{PLAN_ID}}/` boards/tasks in product commits (skills enforce this). Keep them on disk so agents can discover them — do **not** gitignore working plans (gitignore hides them from Cursor Glob/index and breaks `task-executor`).

- **Backlog / Future:** [BACKLOG.md](BACKLOG.md) — всё, что не делаем прямо сейчас; правила добавления и статусы в файле + `.cursor/rules/backlog.mdc`
- Templates: [templates/PLAN.template.md](templates/PLAN.template.md), [templates/BOARD.template.md](templates/BOARD.template.md), [templates/TASK.template.md](templates/TASK.template.md)
- Skills: `.cursor/skills/idea-to-plan`, `plan-to-tasks`, `task-executor`
- Shared rules: `.cursor/skills/shared/agent-tuning.md`, `experts.md`
- Versioning / changelog: `.cursor/rules/versioning-changelog.mdc` — conscious `VERSION` bumps only; root `CHANGELOG.md` mandatory on release (synced with `ConfigData` + release commit)
- **Validator** (mandatory stage gate): after each skill; `fail` blocks the next skill and task `done`.
- **Layout:** `.cursor/plans/{{PLAN_ID}}-plan.md` + `.cursor/plans/{{PLAN_ID}}/BOARD.md` + `.cursor/plans/{{PLAN_ID}}/T01-slug.md` (one file per task — never one monolithic tasks dump).
- **Commits:** one product commit per completed task after Validator pass (see task-executor); do not include working plan/task files in that commit.
- **task-executor entry:** prefer `/multitask` then `/task-executor` (skill cannot flip Multitask Mode via API; experts run as background Tasks).
- **Discovery:** enumerate `.cursor/plans/*/BOARD.md` (Shell/`dir` ok). Ready tasks have status `ready` and dependencies `done`.
- **task-executor default:** drain the whole runnable queue in dependency order until empty or a true blocker; do not stop after one task to ask “which next?”.

