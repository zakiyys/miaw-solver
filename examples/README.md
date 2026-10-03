# Examples

Runnable snippets. Each one assumes the package is importable
(`pip install -e .` or running from the repo root with `venv` active).

| File | Shows |
|---|---|
| `python_library.py` | the four engines via the library API |
| `cli.sh` | every CLI subcommand |
| `api_curl.sh` | native + 2captcha-compatible HTTP endpoints |
| `custom_engine.py` | plugging your own solver into the core |

All examples use `testdata/` fixtures that ship with the repo, so they run
without network access (except `prove_grid.py`, which needs Google).
