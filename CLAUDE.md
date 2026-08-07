# CLAUDE.md - PowerTree

Read this first. Project-local guidance for how to work here.

## Project
- **What:** Local Windows Python app for electronic circuit power tree analysis - sources, converters, loads, series elements, blocks; bottom-up power calc; list + flowchart views; PDF/Excel/image/markdown exports.
- **Started:** 2026-08-06
- **Status:** v0.1 working app. `main.py` launches the PySide6 GUI (or `PowerTree.bat`).
  14 pytest tests in `tests/` cover solver math + serialization. Demo file at
  `examples/DemoBoard.ptproj`.

## Architecture (read before editing)
- `src/powertree/model/elements.py` — dataclasses (Source/Converter/Load/SeriesElement/
  Block/Note), tree constraints (ONE source per tree, loads are leaves).
- `src/powertree/model/calc.py` — bottom-up solver, 3 corners (min/typ/max), damped
  fixed-point for series-R × power-load; margin warnings. ALL electrical math lives here.
- `src/powertree/model/serialization.py` — `.ptproj` versioned JSON (self-contained,
  notes + base64 images embedded).
- `src/powertree/ui/layout.py` — pure-Python tidy-tree layout + orthogonal edge routing
  (no Qt). `canvas.py` — QGraphicsScene flowchart + headless `render_tree_image()` used
  by exports. `mainwindow.py` — all wiring; `refresh()` is the auto-refresh funnel.
- `src/powertree/export/` — pdf_report, excel_export (openpyxl + COM .xlsm), image,
  notes MD/HTML/PDF, md_render (shared markdown→flowables/HTML).
- Run tests: `.venv\Scripts\python.exe -m pytest tests -q`.
- Headless GUI/render testing: set `QT_QPA_PLATFORM=offscreen` **and**
  `QT_QPA_FONTDIR=C:\Windows\Fonts` (else text renders as tofu boxes).

## Folder structure
```
CLAUDE.md     # this file - how Claude should work here
MEMORY.md     # running log: status, decisions, deliverables, open threads
README.md     # human-facing overview (what / why / how to run)
.obsidian/    # makes this folder an Obsidian vault (notes are .md)
.claude/      # settings.local.json (permissions) + hooks/
notes/        # Obsidian knowledge base - link with [[wikilinks]]
research/     # gathered sources, raw findings, agent dumps
artifacts/    # deliverables: reports, PDFs, exports, builds
scratch/      # throwaway / working files (safe to delete; gitignored)
```

## Conventions
- **MEMORY.md is the running log.** Update it as work progresses - status, key decisions
  (with the *why*), finished deliverables, and open threads. A SessionStart hook prints it
  into context each session, so keep it current and concise.
- **notes/ is the Obsidian brain.** Durable knowledge goes here as markdown with
  [[wikilinks]]; notes/index.md is the home note. Link liberally.
- **artifacts/ holds deliverables**, scratch/ holds disposable work. Don't pollute the root.
- **Durable, cross-session facts** (user preferences, hard-won methodology) also go to the
  global memory dir: %USERPROFILE%\.claude\projects\<slug>\memory\ (one fact per file).
- **Build -> verify -> report.** Don't claim done without checking. For visual/PDF/UI work,
  render and actually look at the output before reporting.

## Working style
- Be opinionated and concrete; lead with a recommendation, not a survey.
- Use the dedicated tools (Read/Edit/Grep/Glob) over shell for files.
- Shell here is **PowerShell-primary** (Windows); a Bash tool is also available - each takes
  its own syntax. Open artifacts with `start <file>`.
- For "understand X thoroughly" tasks, fan out parallel research agents (see Playbooks).

## Playbooks (general - trim or extend per project)

### A. Parallel deep research
Launch multiple background agents in ONE message, each owning a distinct angle. Demand
primary sources + dates + verbatim quotes, and adversarial verification of high-stakes
claims. Resume rate-limited agents via SendMessage (keeps context). Synthesize into an
actionable answer; persist durable facts to notes/ and the global memory dir.

### B. Dense single-page PDF / cheat sheet
HTML + Chrome headless print-to-pdf, then screenshot-verify and iterate.
- PDF (full bleed): chrome --headless --disable-gpu --no-sandbox --no-pdf-header-footer
  "--user-data-dir=<temp>" --virtual-time-budget=3000 --print-to-pdf="<out>" "file:///<html>"
  (plain --headless, NOT =new, which silently failed to write).
- Verify: screenshot at --window-size=816,1056 --force-device-scale-factor=2, then Read it.
- Page count (pypdf installed): regex /Type\s*/Page[^s] over the bytes - expect 1.
- Layout that fills a page with zero whitespace: @page{margin:0}; header/footer OUTSIDE the
  grid; grid = display:flex; height:~9in of 4 .col flex columns with
  justify-content:space-between; tune one global font-size so columns fill without spilling.
- Expect ~5-7 render -> look -> adjust loops.

## Pitfalls log
- Windows PowerShell 5.1 reads no-BOM .ps1 as ANSI (Windows-1252), corrupting non-ASCII
  chars in the script. Keep generator scripts ASCII-only, or save them UTF-8 with BOM.
- Qt offscreen platform on Windows finds no fonts (tofu boxes in renders) — set
  `QT_QPA_FONTDIR=C:\Windows\Fonts` alongside `QT_QPA_PLATFORM=offscreen`.
- Rebuilding a panel of nested QFormLayouts: removing only top-level widgets leaks the
  nested layouts' widgets → ghost overlapping labels. Recursively wipe AND
  `setParent(None)` immediately (deleteLater alone defers past the repaint).
- Excel `.xlsm` with real VBA needs COM + "Trust access to the VBA project object model";
  code falls back to `.xlsx` + `PowerTree_Macros.bas` — that's by design, not a bug.
- (add more hard-won gotchas here as you hit them, so they aren't repeated)