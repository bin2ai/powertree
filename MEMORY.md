# MEMORY.md - PowerTree

Running log. Keep current; this is printed into context at session start.

## Status
- 2026-08-06: project scaffolded; v0.1 app built same night.
- 2026-08-07 (overnight, hourly iterations 1-6, each git-committed with a PDF
  in artifacts/reports/): PowerTree is now a full product:
  - Model: sources / converters / loads / series elements (subtypes: ferrite
    bead, fuse, inductor... with DCR + informational inductance + optional
    Vin window / current / dissipation ratings), blocks, GLOBAL net registry
    with conflict detection, device TEMPLATE library (Zynq XC7Z020, DDR3,
    PHYs, regulator-as-block with own Iq), OPERATING STATES (per-element
    overrides, live State selector, materialize-as-tree, validate gates all).
  - Demo: realistic Zynq carrier (12V -> fuse/ferrite -> 5V bus -> POL bucks
    -> Zynq/DDR3/PHY/clock; 38 elements) with 2 deliberate findings (FB3 bead
    undervoltage, core buck <10% margin) + Low Power / Performance states.
  - GUI: bus-routed edges with junction dots, heat map (cold/hot power tint),
    print style (white), display-detail cascade app->tree->element
    (minimal/standard/exhaustive), settings dialog (QSettings), draft
    Save/Cancel element creation, per-element markdown docs dialog with
    image import, searchable notes vault, F1 quick-start.
  - Interfaces: GUI + CLI (powertree info/solve/validate/nets/search/export/
    templates/demo, --json, exit-code CI gate) + MCP server (15 tools, SDK
    2.0, handshake-verified) + Excel.
  - Ship: PyInstaller dist (PowerTree.exe + powertree-cli.exe, verified),
    zip installer w/ shortcuts + uninstall (installer/build_installer.ps1),
    Inno .iss, GitHub Actions CI (pytest offscreen + CLI gate + installer
    artifact). Docs: QUICKSTART + USER_GUIDE.
  - Tests: 47 pytest + 14-step GUI smoke, all green.

## Deliverables
- Repo is git-controlled: v0.1-baseline tag + one commit per iteration.
- artifacts/reports/iteration_0N_report.pdf + flowchart PNG per iteration.
- dist/PowerTree-Setup.zip (80 MB portable installer).
- examples/DemoBoard.ptproj (Zynq demo).

## Decisions
- PySide6 + QGraphicsScene; one headless renderer shared by GUI and exports.
- .ptproj = versioned self-contained JSON (notes + base64 images embedded).
- Solver: damped fixed-point (0.7, 80 iter), 1 mV rail floor -> warns, never
  crashes; three corners min/typ/max; states solved by cloning + overrides
  (ids preserved so results map onto views).
- Excel .xlsm via COM VBA injection; falls back to .xlsx + .bas when the
  VBA-project trust setting is off (it is off on this machine).
- Regulators/ICs modelled as blocks via templates (converter + own Iq load).
- Theme is a mutable singleton (set_style dark/print) so all drawing code
  reads Theme.<attr>.

## Open threads
- User returns 6am 2026-08-07; wants hourly self-eval iterations (ongoing).
- Roadmap: undo/redo, temperature derating, CSV/BOM import, part library
  expansion, rail sequencing checks, per-state Excel sheets, list-view state
  column.
- If Excel VBA trust gets enabled, re-verify true .xlsm path.
- Inno Setup not installed here; .iss ships untested against real ISCC.
