# Contributing to PowerTree

Thanks for helping make PowerTree better. Ground rules keep the project's
"deliberate and verified" culture intact.

## Setup

```bat
git clone https://github.com/bin2ai/powertree
cd powertree
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install -e .[dev,mcp]
```

## Before every PR

```bat
.venv\Scripts\ruff check src tests        :: lint must be clean
.venv\Scripts\pytest tests -q             :: all tests must pass
```

Headless GUI/render testing on Windows needs `QT_QPA_PLATFORM=offscreen` and
`QT_QPA_FONTDIR=C:\Windows\Fonts`.

## Rules of the road

- **Every behavior change ships with a test.** Solver changes need
  hand-checkable math in the test (see tests/test_model.py for the style).
- **Visual changes need visual proof** — render the affected view (offscreen
  PNG) and eyeball it before pushing; attach the render to the PR.
- **Electrical math lives in `src/powertree/model/calc.py` only.** GUI and
  exports consume results; they never compute power themselves.
- **The four surfaces stay in parity**: a new analysis should reach the GUI,
  CLI, MCP server and reports (see `api.py` — one backend, four fronts).
- **File-format changes** bump `FILE_FORMAT_VERSION` and add a migration in
  `serialization.MIGRATIONS` plus a round-trip test.
- Keep lines ≤100 chars; follow the existing comment style (explain
  constraints, not restatements).

## Releasing (maintainers)

1. Bump `src/powertree/__init__.py:__version__` (single source of truth).
2. Add a CHANGELOG.md section for the version.
3. `git tag vX.Y.Z && git push origin main --tags` — CI publishes to PyPI
   (trusted publishing) and creates the GitHub Release with the installer.
