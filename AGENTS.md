## Local-First Application Runtime

- This project is a local-first desktop application. By default, run the
  frontend, backend API, SQLite runtime database, MediaCrawler processes, and
  browser/CDP integration on the user's local machine.
- Use the local machine for development previews, debugging, and application
  validation. Browser-dependent collection and platform-login flows must run on
  the same local machine as the user's browser.
- Do not rsync this project to Centaurus, start application services there, or
  use Centaurus for validation unless the user explicitly requests Centaurus in
  the current task. Do not infer permission from workload size or tool
  availability.
- This local-first policy overrides older Trellis specs, task artifacts, or
  verification notes that prescribe Centaurus; treat those references as
  historical unless the user explicitly opts into Centaurus again.
- If the user explicitly requests Centaurus for a specific task, keep the local
  repository as the source of truth and apply the Centaurus workflow only to
  that task.

<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->
