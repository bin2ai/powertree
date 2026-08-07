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
| **PDF report** | cover + per-tree overview, global nets, embedded flowchart, hierarchy table (typ + max corners, losses, status colors), blocks, per-state comparison, margin findings, full notes appendix |
| **Excel (.xlsm)** | Overview, one sheet per tree with Excel outline collapse (+/−), live P=V·I formulas, kind/severity coloring, Warnings sheet, VBA navigation macros (needs "Trust access to the VBA project object model"; otherwise .xlsx + importable .bas) |
| **Flowchart PNG** | HD render at the configured scale, honoring current style (dark/print), heat mode and detail level |
| **Notes → MD / HTML / PDF** | the entire vault (hierarchy preserved, images embedded, element links listed) |

---

## 4. CLI

```
powertree-cli info <p.ptproj>                     project summary
powertree-cli solve <p> [--tree N] [--state S] [--json]
powertree-cli validate <p> [--json]               exit 1 on violations (CI gate)
powertree-cli nets <p>                            net registry + conflicts
powertree-cli search <p> <query>
powertree-cli templates
powertree-cli export pdf|png|xlsx|xlsm|notes-md|notes-html|notes-pdf <p> -o out
powertree-cli demo -o Demo.ptproj
powertree-cli gui [p]
```
(from the repo, `PowerTree.bat <args>` is the same CLI; no args opens the GUI)

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
