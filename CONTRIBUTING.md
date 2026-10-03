# Contributing

Thanks for considering a contribution. This project is deliberately small and
CPU-first — please keep it that way.

## Ground rules

1. **CPU must work.** Every feature has to run on a plain GitHub Actions runner.
   GPU support is a bonus path, never a requirement.
2. **No new heavy dependencies for core.** The core (`ddddocr` + Pillow + numpy)
   stays lean. Audio and grid extras are opt-in via separate requirement files.
3. **No secrets in the tree.** Never commit API keys, tokens, cookies, or
   absolute paths that reveal a machine. Use environment variables.
4. **Tests are mandatory.** A change without a test that fails before it and
   passes after it will not be merged.

## Setup

```bash
git clone <your-fork>
cd miaw-solver
python -m venv venv && . venv/bin/activate

pip install -r requirements-all.txt   # or the minimal set:
# pip install -r requirements.txt
```

## Running the checks

```bash
pytest tests/ -q            # all offline tests
python scripts/prove_grid.py  # live grid proof (needs network + Chromium)
```

Tests must be **offline and deterministic**. Anything that touches the network
belongs in `scripts/`, not in `tests/`.

## Code style

- Python 3.10+, type hints on public functions.
- Docstrings in the imperative mood, explaining *why* not *what*.
- Comments only where the logic is non-obvious.
- Keep functions small; prefer composition over inheritance.
- `from __future__ import annotations` at the top of every module.

## Adding a captcha engine

1. Create `captcha_solver/workers/<name>.py` exposing a class with a
   `solve(...)` method that raises `SolverError` on failure.
2. Wire it into `captcha_solver/core.py` behind a clear entry point.
3. Expose it through the CLI and the HTTP API if it maps to a 2captcha method.
4. Add offline tests in `tests/` using a local fixture — never a live service.
5. Add a requirement file if the engine needs new dependencies.
6. Document it in `docs/engines.md`.

## Pull requests

- One logical change per PR.
- Describe the failure mode you fixed or the capability you added, with evidence.
- Update `CHANGELOG.md` under an `Unreleased` heading.
- Do not bump the version — maintainers do that at release time.

## Reporting bugs

Include: what you ran, what you expected, what happened, and the raw error output.
A reproducible command beats a description.
