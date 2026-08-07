# Changelog

## 0.7.0 — 2026-08-07

### Block Designer
- Right-click a block (or its summary node) → *Design block*: place every
  input/output pin on any card side (top/bottom/left/right), reorder pins,
  set the card width/height, add custom info lines, hide/show the power
  stats, and pick the accent color. Edges route to the designed pin
  positions; everything persists in the project file and applies to all
  exports.

### Component library
- Save any block — members, internal topology, electrical parameters and
  the designer style — as a reusable part: right-click → *Save block to
  library*, or manage everything in Project → *Component library*
  (Ctrl+L): place parts into trees, import/export parts as .json files to
  share, delete. Library parts appear alongside built-in templates
  everywhere (template dialog, CLI `templates`, MCP). The library lives in
  %APPDATA%/PowerTree/library.json (POWERTREE_LIBRARY overrides).

### Undo/redo
- (shipped in 0.5.0, now discoverable) Edit-menu entries show live step
  counts and disable when empty; covered by tests for designer edits.

## 0.6.0 — 2026-08-07

### Collapsed block summary nodes
- Any block can collapse into ONE summary card: summed **P in**, internal
  **dissipation** (loads consumed + series I²R + converter losses) and
  **pass-through** power, member count, and a worst-severity badge.
- The card carries labeled **input pins** (every distinct rail feeding the
  block — common vs unique paths are explicit) and **output pins** (rails
  leaving the block); edges land on the pins, multi-rail feeds route as
  cross-edges, and collapsed blocks can feed other collapsed blocks
  pin-to-pin. Works in TD/LR/custom layouts and all exports; collapse
  state persists in the project file.
- Toggle via the card's ⤢ chip, right-click menus, or View → Collapse/
  Expand all blocks.

### Right-click settings, two levels
- Background right-click → **View settings** submenu: legend / heat map /
  print style, layout, app-default card detail, collapse/expand all
  blocks, full Settings dialog.
- Right-click on an element → **Item settings** (per-element card detail
  override) plus add-under/duplicate/collapse/docs/delete; on a block
  summary node → expand/rename; View settings available everywhere.

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
