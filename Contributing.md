# Contributing

## Quick start
1. **Clone** the repo and create a virtual env.
2. **Install deps**: `pip install -r requirements.txt`
3. **Install dev tools** (optional but recommended): `pip install ruff mypy pre-commit`
4. **Enable pre-commit**: `pre-commit install`
5. **Create a branch**: `git checkout -b feat/your-thing`
6. **Run locally**:
   - API: `python -m uvicorn app.main:app --reload --port 8001`
   - Auto runner: `python run_auto_guarded.py`
7. **Commit** early/often. The hooks will auto-format & lint.

> Keep `.env` **out of git**. In production the CI writes it from GitHub Secrets.

## Code style
- **Formatting**: `ruff format` (Black-style)
- **Lint**: `ruff check --fix`
- **Typing**: use type hints; run `mypy` occasionally (best-effort)
- **Imports**: standard → third-party → local, with blank lines between groups

## Commit messages
- Conventional-ish:
  - `feat: add xau momentum thresholds`
  - `fix: correct SL/TP pip conversion for gold`
  - `chore: bump deps`

## PR checklist
- [ ] CI is green
- [ ] No debug prints left
- [ ] Configurable values come from env (not hardcoded)
- [ ] If touching strategies/execution, include a short test note or log excerpt

## Local tasks
- Format & lint: `ruff format && ruff check --fix`
- Type check: `mypy app` (optional)
- Run unit-ish tests (if any): `pytest -q` (optional)
