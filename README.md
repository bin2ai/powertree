# PowerTree

**Electronic circuit power tree analysis** — a fully offline desktop app for
budgeting power from source to load with min/typ/max corners, margin analysis, a live
flowchart, and report-grade exports (PDF / HTML / Excel / CSV / PNG).

![version](https://img.shields.io/badge/version-0.5.0-blue)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)
— PySide6 · Windows-first · no accounts, no internet.

```bat
pip install powertree
powertree-gui                      :: desktop app (opens with a Zynq demo board)
powertree --help                   :: full CLI
```

## What it does

- **Projects hold many power trees** (`.ptproj`, versioned JSON, self-contained).
- **Elements**: one **Source** per tree (V min/typ/max + current *or* power limit),
  **Converters** (efficiency %, Vout corners, quiescent current, optional output limit,
  pass-through output rail for sub-loads), **Loads** (current- or power-type, typ/peak
  value, allowed input-voltage window for margin checks), **Series elements**
  (resistance, bounded so the math never breaks). Every element carries the same
  metadata: name, signal name, ref des, part number, pin(s), datasheet link, notes.
- **Blocks** group elements visually (e.g. one IC with Icc + Iq loads) and show
  aggregate power.
- **Bottom-up solver, auto-refresh**: every edit re-solves all three corners
  (damped fixed-point for series-R × power-load interaction) and repaints instantly.
- **Margin analysis**: source/converter limit usage, load under/over-voltage vs its
  allowed window, step-down/boost sanity, collapsed-rail detection — surfaced as
  findings, node badges, list statuses, and report sections.
- **Views**: color-coded flowchart (90° routed arrows with rail labels, legend,
  collapse/expand chips, no overlaps, power text on every card) + hierarchical list
  view. Layouts: top-down, left-right, or custom drag-to-place.
- **Search** (Ctrl+F) across name/signal/refdes/part/pins/notes — highlights the
  canvas and filters the list.
- **Documentation notes**: hierarchical markdown notes with embedded images, linked
  to elements — capture *where every number came from*.
- **Exports**: PDF report (flowcharts + tables + margins + full notes appendix),
  macro-enabled Excel report (`.xlsm` with outline collapse + VBA navigation macros;
  falls back to `.xlsx` + importable `.bas` when VBA trust is off), HD PNG flowchart,
  notes → Markdown / HTML / PDF.

## Install & run

**From PyPI** (recommended):

```bat
pip install powertree            :: add powertree[mcp] for the AI/MCP server
powertree-gui                    :: GUI
powertree info my.ptproj         :: CLI (same entry: powertree --help)
```

**From source:**

```bat
git clone https://github.com/bin2ai/powertree
cd powertree
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python.exe main.py         :: or double-click PowerTree.bat
```

**Standalone Windows installer** (no Python needed) — build
`dist\PowerTree-Setup.zip` with `installer\build_installer.ps1`, unzip, run
`install.bat` (per-user install, Start-Menu/Desktop shortcuts, uninstaller;
`installer\PowerTree.iss` builds a setup.exe when Inno Setup is present).

**Onboarding**: press **F1** in the app (Quick start), or read
[docs/QUICKSTART.md](docs/QUICKSTART.md) and
[docs/USER_GUIDE.md](docs/USER_GUIDE.md). A full feature tour with
screenshots: `artifacts/PowerTree_Feature_Overview.pdf`.

The app opens with a built-in demo (a realistic Zynq-7000 carrier board) so every
feature is visible immediately.

## Four ways to use it

| Mode | How |
|---|---|
| **GUI** | `powertree-gui` — flowchart, list, properties, states, notes, search, waivers |
| **CLI** | `powertree info\|solve\|validate\|nets\|headroom\|growth\|bom\|search\|export\|templates\|demo …` — JSON with `--json`; `validate` exits non-zero on violations (`--strict` fails on warnings too) |
| **Excel** | macro-enabled report export, native outline collapse, live formulas, States/Parts sheets |
| **AI / MCP** | `powertree-mcp` — 16 tools (open/solve/validate/edit/waive/export); see `examples/mcp.json.example` for Claude Code / Desktop registration |

```bat
powertree info examples\DemoBoard.ptproj
powertree validate examples\DemoBoard.ptproj --strict   && echo margins clean
powertree growth examples\DemoBoard.ptproj              :: +N% load headroom
powertree export bundle examples\DemoBoard.ptproj -o out\   :: all formats
```

## Tests

```bat
.venv\Scripts\python.exe -m pytest tests -q
```

14 tests cover the solver math (hand-checked corner cases incl. the series-R +
power-load fixed point), model constraints, and file-format round-tripping.

## Layout

```
main.py                  launcher
src/powertree/
  model/    elements, bottom-up solver (calc.py), .ptproj serialization
  ui/       main window, flowchart canvas, tidy-tree layout, list view,
            properties, notes, dark theme
  export/   PDF report, Excel (.xlsm/COM + .xlsx), HD PNG, notes MD/HTML/PDF
  sampledata.py  demo project
tests/       pytest suite
examples/    DemoBoard.ptproj
notes/       Obsidian knowledge base (project docs, not app data)
```

## Excel macros note

`.xlsm` export embeds VBA (expand/collapse outline, next-finding navigation) through
Excel COM, which requires *File → Options → Trust Center → Trust Center Settings →
Macro Settings → “Trust access to the VBA project object model”*. Without it you get
an identical `.xlsx` plus `PowerTree_Macros.bas` to import manually (Alt+F11 →
File → Import).

## Roadmap ideas

Resistive loads · operating modes / duty-cycle scenarios · undo-redo · temperature
derating · CSV/BOM import · converter component library · rail sequencing checks ·
per-corner load values.

---
Scaffolded 2026-08-06. See `CLAUDE.md` for how Claude works in this project.
