---
name: ruff-fix
description: Format and lint the codebase with ruff, auto-fixing what it can and manually resolving the rest. Use when the user asks to "run ruff", "format and lint", "fix lint errors/warnings", clean up style, or before committing. Targets the whole repo by default, or specific paths if given.
allowed-tools: Bash, Read, Edit, Glob, Grep
---

# ruff-fix

Bring the code to a clean ruff state: zero formatting diffs and zero lint
errors/warnings. ruff config lives in `pyproject.toml` (`[tool.ruff]`).

## Scope

- Default target is the whole repo: `.`
- If the user names files or directories, target those instead (pass them in place
  of `.` in every command below).

## Procedure

1. **Format.** Run the formatter first — it resolves layout/whitespace issues so the
   linter sees clean code:
   ```bash
   uv run ruff format .
   ```

2. **Auto-fix lint.** Apply every safe automatic fix:
   ```bash
   uv run ruff check --fix .
   ```
   If you want ruff's normally-unsafe fixes too, use `--fix --unsafe-fixes` — but
   only when the user is okay with potentially behavior-changing edits; review the
   diff afterward.

3. **Inspect what remains.** List the issues ruff could not fix automatically:
   ```bash
   uv run ruff check --output-format=concise .
   ```
   If this prints `All checks passed!`, skip to step 5.

4. **Manually fix the rest.** For each remaining diagnostic:
   - Read the rule code (e.g. `B008`, `N802`, `RUF012`) and the message. Look it up
     with `uv run ruff rule <CODE>` if the fix isn't obvious.
   - Open the file with Read, make the smallest correct Edit that satisfies the rule
     while preserving behavior and matching surrounding style.
   - Prefer fixing the root cause over suppressing. Only add a `# noqa: <CODE>`
     (with the specific code, never a bare `# noqa`) when the warning is a genuine
     false positive — and briefly say why in the final summary.
   - Re-run `uv run ruff format .` after manual edits in case they changed layout.

5. **Verify clean.** Loop steps 1–4 until both commands are clean:
   ```bash
   uv run ruff format --check . && uv run ruff check .
   ```
   Both must report success.

6. **Confirm nothing broke.** If a test suite exists, run it to ensure fixes were
   behavior-preserving:
   ```bash
   uv run pytest -q
   ```

## Report

Summarize: counts of auto-fixed vs manually-fixed issues, any files changed, any
`# noqa` added (with justification), and the final clean/​test status. If a
diagnostic genuinely cannot be resolved without a larger refactor or a decision,
stop and ask rather than forcing a suppression.
