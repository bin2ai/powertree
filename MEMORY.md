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

## Improvement loop (hourly cron @ :52, session job f2afe364 — still armed)
- Cycle 1 (it7): efficiency/loss/top-consumer analytics everywhere, PDF exec
  summary + health verdict, CSV export, %-of-tree column.
- Cycle 2 (it8): rail headroom budgets (CLI/MCP/PDF), undo/redo (Ctrl+Z/Y),
  Excel States sheet, copy-flowchart-image + copy-table to clipboard.
- Cycle 3 (it9): single-file HTML share report (export html), derating
  policy (80% default, project-level, validate + dialog), recent-projects
  menu, duplicate subtree (Ctrl+D), canvas right-click context menu.
- Cycle 4 (it10): converter efficiency-vs-load CURVES (interpolated in the
  solver), BOM/parts list (Excel sheet + CLI bom), GUI Validate dialog
  (Ctrl+Shift+V), autosave + crash recovery, significant-digits knob.
- Cycle 5 (it11): finding WAIVERS w/ justification (audit trail through GUI/
  PDF/validate/MCP), project-properties dialog, demo eta curve, installer
  rebuilt (verified), USER_GUIDE refresh.
- Cycle 6 (it12): export bundle (all formats one shot), validate --strict,
  Ctrl+=/- zoom, first-run welcome, v0.5.0 version stamping.
- Tests grew 14 -> 69 (+14-step GUI smoke); every cycle committed + PDF in
  artifacts/reports (iteration_01..12).

## Publication (2026-08-07)
- History REWRITTEN with git-filter-repo before publishing: all commits
  re-authored to bin2ai <bin2ai@users.noreply.github.com>, personal paths/
  strings scrubbed (0 hits verified), .claude/.obsidian dropped from history
  (still on disk, now gitignored). Pre-rewrite backup bundle in scratchpad.
- Public repo: https://github.com/bin2ai/powertree (main + v0.1-baseline,
  v0.5.0 tags). CI runs on push.
- PyPI: name `powertree` free; pyproject/LICENSE(MIT)/CHANGELOG added; wheel
  built + verified in clean venv (powertree / powertree-gui / powertree-mcp
  entry points). publish.yml uses PyPI Trusted Publishing on v* tags —
  ONE-TIME USER STEP: on pypi.org add pending publisher (project powertree,
  owner bin2ai, repo powertree, workflow publish.yml, environment pypi),
  then re-run the v0.5.0 publish workflow (gh run rerun) to go live.

## v0.8.0 (2026-08-08) — full audit implementation
- Audit written to docs/AUDIT-2026-08-07.md (every finding tracked to a
  disposition); deferred architecture in docs/ROADMAP.md (DAG sources,
  temp-derating curves, cross-tree net solving, code signing, i18n).
- Implemented: rail-grid wrapping (7.4x narrower at 501 elements), minimap,
  threaded exports + render size cap, reveal-on-jump, drag-drop reparent,
  multi-delete, subtree copy/paste; resistive loads, duty cycle, unregulated
  topology, sequencing checks; library versioning/conflicts/project-lib;
  report logo/tree-picker/waived toggle; command palette, message log,
  arrow-key nav, light print theme; ruff+cov+linux CI, dynamic version,
  release assets, CONTRIBUTING/templates, file log + crash dialog,
  migrations, unsaved autosave, README screenshots.
- 96 tests + 16-group GUI smoke; ruff clean.

## v0.9.0 (2026-08-08) — competitive audit slate
- Competitive audit vs LTpowerPlanner in docs/AUDIT-2026-08-08-competitive.md
  (comparison matrix, anti-over-engineering list). All 5 recommended items
  shipped: SI-suffix entry (units.py + SIEdit), cost/area rollups, Compare
  architectures (GUI/CLI/MCP), gesture polish (datasheet ↗, F2 rename,
  dbl-click collapse, empty-canvas hint), PMIC block-pattern template.
- 126 tests + 17-group smoke; ruff clean.

## Open threads
- User returns 6am 2026-08-07; wants hourly self-eval iterations (ongoing).
- Roadmap: undo/redo, temperature derating, CSV/BOM import, part library
  expansion, rail sequencing checks, per-state Excel sheets, list-view state
  column.
- If Excel VBA trust gets enabled, re-verify true .xlsm path.
- Inno Setup not installed here; .iss ships untested against real ISCC.
