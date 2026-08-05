# FinanzAPP Agent Notes

This repository is a personal finance NiceGUI app. Before making non-trivial
changes, read [docs/REPO_CONTEXT.md](docs/REPO_CONTEXT.md).

Keep `docs/REPO_CONTEXT.md` current. Update it in the same change whenever you
alter important behavior, database schema, environment variables, dependencies,
startup/maintenance commands, data paths, or user-facing workflows.

Private finance and auth data live under `private/` and are ignored by Git.
Inspect private data only when it is necessary for the task, and prefer schema,
counts, and integrity checks over exposing transaction-level personal details.

