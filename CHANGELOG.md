# Changelog

## 0.8.0 — 2026-08-08

Implements every actionable finding of the v0.7.0 audit
(docs/AUDIT-2026-08-07.md); deferred architecture items are designed in
docs/ROADMAP.md.

### Scale & responsiveness (P0)
- Rail-grid wrapping: many leaf loads on one rail lay out as a compact grid
  with a single bus edge — a 501-element board is 7.4× narrower (135k px →
  18k px). Threshold configurable (Settings / per view), off in custom mode.
- Click-to-navigate minimap overlay (toggleable).
- Exports run in worker threads with a busy dialog — no more 8-second GUI
  freezes; renders cap their longest side (16k px) by auto-reducing scale.
- Jump-to-finding / search-Enter now auto-expands collapsed branches and
  blocks hiding the target.
- Editing: drag-drop re-parenting in the list view (model-validated),
  multi-select delete, and subtree copy/paste (Ctrl+Alt+C/V) via the OS
  clipboard — works across trees, projects and app instances.

### Model depth (P1)
- Resistive loads (I = V/R, solved in the corner fixed-point).
- Load duty cycle: min/typ corners budget the duty-weighted average draw;
  the max corner keeps the full peak.
- Unregulated converter topology: Vout = ratio × Vin, tracking per corner.
- Power-up sequencing: converters carry a sequence step; a rail enabling
  before its input rail is flagged.
- Library maturity: parts stamped with version/author/date (version bumps
  on overwrite), import-conflict handling (overwrite/rename/skip), export
  the whole library, and a project-local library (powertree_library.json
  next to the .ptproj — commit it with the design).
- Reports: embedded project logo on PDF/HTML titles, pre-export tree
  selection, include/exclude waived findings.
- Nets view/report now state their scope explicitly (name registry;
  cross-tree merged solving is a roadmap item).

### Usability (P2)
- Command palette (Ctrl+K) searching every menu action.
- Message log dock — status messages persist with timestamps.
- Arrow-key navigation on the canvas (parent/child/siblings).
- Print style now applies a light theme to the whole app window.

### Process (P3)
- CI: ruff lint gate, coverage floor, and a Linux test leg.
- Version single-sourced from powertree.__version__.
- Releases: the publish workflow now creates the GitHub Release with the
  Windows installer zip and wheels attached, notes taken from this file.
- CONTRIBUTING.md + issue templates.
- Rotating file log (%APPDATA%/PowerTree/powertree.log) + GUI crash dialog.
- .ptproj migration framework (versioned upgrade registry).
- Autosave now also protects never-saved projects (startup recovery).
- README gained screenshots.

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
