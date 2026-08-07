# Changelog

## 0.5.0 — 2026-08-07

First public release. Built and hardened across 13 tracked iterations
(see git history for the full trail); 72 unit/integration tests plus a
scripted GUI smoke suite.

### Modelling
- Sources (V corners, current/power limits), converters (Vout corners,
  quiescent current, output limits, **efficiency-vs-load curves**), loads
  (current/power type, peak values, allowed Vin windows), series elements
  (resistor/ferrite/inductor/fuse/cable/connector/switch with DCR,
  inductance, ratings and Vin windows).
- Blocks (device grouping with aggregate power), device **template library**
  (Zynq-7000, DDR3, PHYs, clock gen, regulator-as-block) plus **user JSON
  templates**, project-global **net registry** with conflict detection,
  named **operating states** with per-element overrides.

### Analysis
- Automatic bottom-up solve, three corners, damped fixed-point, bounded math.
- Margin analysis, **derating policy**, **rail headroom budgets**,
  **load-growth capacity**, efficiency/loss/top-consumer analytics,
  finding **waivers** with justification (audit trail).

### Interfaces
- PySide6 GUI: flowchart (bus routing, junction dots, heat map, print style,
  detail cascade, drag layout), list view, properties with draft-create,
  searchable markdown notes vault with per-element docs and image import,
  undo/redo, autosave/recovery, settings, onboarding.
- CLI: info / solve / validate (`--strict` CI gate) / nets / headroom /
  growth / bom / search / templates / export / demo / gui, all with `--json`.
- MCP server (16 tools) for AI assistants.
- Reports: PDF (executive summary + engineering detail), single-file HTML,
  Excel (.xlsm macros / outline / states / parts), CSV, HD PNG, notes
  exports, one-click bundle.
- Windows installer (PyInstaller + zip/Inno), GitHub Actions CI.
