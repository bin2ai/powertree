# PowerTree User Guide

Complete reference for the concepts and workflows. For the 5-minute tour see
[QUICKSTART.md](QUICKSTART.md).

---

## 1. Concepts

### Project → trees → elements
A **project** (`.ptproj` file, versioned JSON, fully self-contained) holds any
number of **power trees**, the hierarchical **documentation notes** (with
embedded images), and the project's **operating states**. Each tree starts at
exactly **one source** and fans out through converters and series elements to
loads.

### Element types

| Type | Electrical model | Key fields |
|---|---|---|
| **Source** | V min/typ/max; optional current *or* power limit | limit type + value |
| **Converter** | Regulates Vout (min/typ/max corners); input power = output/η + Iq·Vin | topology, efficiency %, quiescent I, optional output limit; its output rail is the pass-through terminal for children |
| **Load** | Current-type (I fixed) or power-type (P fixed, I = P/V) | typ + optional peak value, allowed Vin window |
| **Series element** | DC resistance in the path (V drop = I·R, loss = I²R) | subtype (resistor / ferrite bead / inductor / fuse / cable / connector / switch), DCR, informational inductance, free-text rating, optional Vin window + current + dissipation ratings |

All elements share metadata: name, **signal (net) name**, ref des, part
number, pin(s), datasheet link, free notes, linked documentation.

### Modelling conventions (industry practice)
- **Ferrite beads / inductors** are series elements: the DC solver uses their
  DCR; inductance is displayed for AC awareness only.
- **Any IC** (Zynq, PHY, DDR…) is a **block** containing one load per supply
  rail/bank, each with its true datasheet input-voltage window.
- **Any regulator** is a block too: the converter itself plus its own
  controller Iq as a separate load on the input rail.
- Use **templates** (Ctrl+T) to instantiate these patterns correctly.

### Blocks
Blocks visually group elements into one device with an aggregate power label.
A block's members can sit on different rails — the canvas outlines each
cluster and marks continuations with "⋯".

**Collapsed blocks**: right-click a member → *Collapse block* (or View →
Collapse all blocks) and the whole block becomes ONE summary card showing
summed P in, internal dissipation (loads + series I²R + converter losses)
and pass-through power — with labeled **input pins** for every rail feeding
the block and **output pins** for rails leaving it, so common vs unique
paths stay explicit. Expand again via the card's ⤢ chip or right-click.
Collapse state saves with the project and applies to every export.

**Block Designer**: right-click a block or its summary node → *Design
block…* to customize the collapsed card: put any pin on any side
(top/bottom/left/right), reorder pins, set card width/height, add custom
info lines, toggle the stats and pick the accent color.

### Component library
Save any block as a reusable part: right-click → *Save block to library*
(captures members, internal topology, electrical parameters, efficiency
curves and the designer style). Manage parts in **Project → Component
library (Ctrl+L)**: place into the current tree, **import/export parts as
.json files** to share with teammates, delete. Library parts show up next
to the built-in templates in the template dialog (Ctrl+T), the CLI
(`powertree templates`) and MCP. Storage:
`%APPDATA%\PowerTree\library.json` (override with the `POWERTREE_LIBRARY`
environment variable).

### Right-click settings
Right-click anywhere on the canvas for **View settings** (legend, heat map,
print style, layout, default card detail, collapse/expand all blocks);
right-click **on an element** for item actions plus **Item settings**
(per-element card detail); right-click a collapsed block node to expand or
rename it.

### Nets are global
The `signal name` of a source / converter output / series output **defines a
net for the whole project**. Loads consume the nearest named ancestor rail.
`Ctrl+G` opens the registry; defining the same net at two different voltages,
or driving it from two regulators in one tree, is flagged as a conflict (also
in `validate` and the PDF).

### The solver
Runs automatically on every edit, bottom-up, in three corners:
- **min** — V min everywhere, typ loads
- **typ** — nominal
- **max** — V max corners and peak load values

Series resistance × power-load coupling is solved by damped fixed-point
iteration; rails are floored at 1 mV so pathological input warns
("rail collapsed") instead of crashing.

### Margin analysis
Findings appear as card badges, the Findings dock, list Status column and
report sections — **the tree still solves; you are made aware**:
- source/converter limit exceeded (error) or ≤10 % margin left (warning)
- load or series element outside its allowed Vin window (error)
- series element beyond its current/dissipation rating (error; >90 % warning)
- buck/LDO with Vout > Vin, boost with Vout < Vin (warning)
- collapsed rail, non-convergence, net conflicts
- rails loaded beyond the **derating policy** (`Project → Derating policy…`,
  default 80 % of the hard limit)

**Waivers**: right-click a finding → *Waive with justification*. Waived
findings stop counting (status bar, validate, PASS/FAIL) but remain visible
greyed-out in the GUI and every report with the justification — a proper
review audit trail. Right-click again to un-waive.

### Efficiency curves
A converter can carry a datasheet **efficiency-vs-load curve**
(`η curve` field in Properties, e.g. `0.1:85, 0.5:91, 1:93, 3:90` as
`Iout(A):η(%)` pairs). The solver interpolates at the solved output current
per corner; cards show the effective η marked `*`. Without a curve the flat
efficiency applies.

### Analytics
Every surface exposes decision-grade analytics: end-to-end efficiency and
total loss (status bar, overviews), **top consumers with % of source
budget**, and **rail budgets** — remaining headroom per limited rail and the
extra load it could still accept (`headroom` CLI command, PDF/HTML tables,
MCP `rail_headroom`).

### Operating states
`Project → Manage operating states…` defines named states. Element
properties then expose per-state overrides (loads: typ/peak value;
converters: efficiency/Iq; sources: voltage corners; series: resistance).
The toolbar **State** selector re-solves the whole tree in that state;
`Project → Materialize` bakes the current state into a standalone tree.
`validate` (CLI/MCP) gates **every** state.

---

## 2. GUI reference

| Area | What it does |
|---|---|
| Left dock | trees in the project; ＋/✕; double-click renames |
| Center | Flowchart tab (canvas) and List view tab (sortable columns) |
| Right dock | Properties (edit selected element / tree) and Documentation Notes (searchable vault) |
| Bottom dock | Findings — click one to jump to the element |
| Toolbar | add element drafts (Save/Cancel), template (Ctrl+T), delete, State selector, layout TD/LR/custom, fit (Ctrl+0), collapse/expand all, legend, 🔥 heat map, 🖨 print style |
| Search | Ctrl+F — name/refdes/signal/part/pins/description |

**Display detail** cascades app → tree → element (`minimal`, `standard`,
`exhaustive`) — set the app default in `View → Settings…`, per-tree in tree
properties, per-element in element properties. Exhaustive cards add
min-corner values, ratings, part numbers, pins and state lists.

**Custom layout**: choose "Custom (drag)" and drag cards; positions are saved
in the project.

---

## 3. Exports

| Export | Contents |
|---|---|
| **PDF report** | executive summary (KPIs, health verdict, top consumers), global nets, per-tree flowchart + hierarchy table, rail budgets, blocks, per-state comparison, margin findings incl. waivers, full notes appendix |
| **HTML report** | the same content as ONE self-contained file (images embedded) — mail it, no install needed |
| **CSV** | the fully-solved element table (all trees or one) for scripts and spreadsheets |
| **Excel (.xlsm)** | Overview, one sheet per tree with Excel outline collapse (+/−), live P=V·I formulas, kind/severity coloring, Warnings sheet, VBA navigation macros (needs "Trust access to the VBA project object model"; otherwise .xlsx + importable .bas) |
| **Flowchart PNG** | HD render at the configured scale, honoring current style (dark/print), heat mode and detail level |
| **Notes → MD / HTML / PDF** | the entire vault (hierarchy preserved, images embedded, element links listed) |

---

## 4. CLI

```
powertree info <p.ptproj>                    project summary + analytics
powertree solve <p> [--tree N] [--state S] [--json]
powertree validate <p> [--strict] [--json]   exit 1 on violations (CI gate;
                                             --strict fails on warnings too)
powertree nets <p>                           net registry + conflicts
powertree headroom <p> [--tree N]            remaining budget per limited rail
powertree growth <p> [--tree N]              max load growth before violation
powertree bom <p>                            parts list by part number
powertree search <p> <query>
powertree templates
powertree export pdf|html|png|csv|xlsx|xlsm|notes-md|notes-html|notes-pdf|bundle
               <p> -o out [--tree N] [--style dark|print]
powertree demo -o Demo.ptproj
powertree gui [p]                            (or the powertree-gui command)
```
(pip install exposes `powertree` / `powertree-gui` / `powertree-mcp`; from a
repo checkout, `PowerTree.bat <args>` is the same CLI and no args opens the
GUI; the frozen build ships `powertree-cli.exe`)

## 5. MCP (AI integration)

`python -m powertree.mcp_server` starts a stdio MCP server with 15 tools:
open/new/save project, summary, solve (per state), validate, nets, search,
get element, set field, set state override, templates + apply, export.
Register with Claude Code / Desktop via `examples/mcp.json.example`.

## 6. CI

`.github/workflows/ci.yml` runs the full pytest suite offscreen on every
push/PR, exercises the CLI gate, and packages the Windows installer from
`main`. Use `powertree-cli validate` in **your own** hardware repo's CI to
block merges that break power margins.

## 7. File format

`.ptproj` = versioned JSON (`"format": "powertree-project"`). Everything —
trees, elements, blocks, states, notes, base64 images, layout positions — is
in the one file: diff-able, review-able, email-able. Newer-version files are
refused with a clear message rather than mis-read.
