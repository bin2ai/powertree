# PowerTree — 5-minute Quick Start

PowerTree budgets power from source to load with min/typ/max corners and tells
you where margins break. Everything runs locally — no account, no internet.

## 1. Launch

- Installed: Start Menu → **PowerTree** (or `PowerTree.exe`)
- From repo: double-click `PowerTree.bat`

The app opens with the **Zynq Carrier demo** — a realistic 12 V → Zynq-7000
board. Two findings are built in on purpose (a wrong ferrite bead and a
too-small core regulator) so you can see how problems surface: red badges on
cards, the **Findings** panel at the bottom, and red rows in every report.

## 2. Read the flowchart

- **Amber card** = source (one per tree) · **blue** = converter · **green** =
  load · **grey** = series element (fuse / ferrite / resistor…)
- Every card shows its live **power, current, voltage** — recomputed on every
  edit (bottom-up, min/typ/max corners).
- Dashed containers are **blocks** (one IC or regulator and its sub-loads)
  with the block's total power.
- Dots on the wires are **junctions** where a rail branches.
- **Legend** bottom-left. `Ctrl+0` fits the view. Mouse wheel zooms.
- Try the toolbar: **🔥 Heat** (tint by power draw), **🖨 Print style**
  (white, printable), **Layout** (top-down / left-right / drag-to-place),
  **− / +N chips** on cards collapse/expand branches.

## 3. Build your own tree

1. **＋ Tree** in the left panel, then **⊕ Source** — fill the form in the
   right panel and press **Save** (nothing is added until you Save).
2. Select the source, add **⊞ Converters** / **≡ Series** / **◎ Loads** the
   same way. Loads take a current or power value plus an allowed
   input-voltage window — that window powers the margin analysis.
3. Faster: **Ctrl+T** adds a whole device from the template library
   (Zynq SoC, DDR3, PHYs, regulator-as-block with its own Iq…): map its
   rails to your converters and done.
4. Group related elements into a **▣ Block** so they read as one device.

## 4. States, nets, search

- **Project → Manage operating states…** creates named states (Low Power,
  Performance…). Any element can override values per state (Properties →
  Operating states). The toolbar **State** selector re-solves live;
  **Project → Materialize** bakes a state into its own tree.
- **Ctrl+G** shows the global net registry (signal names are project-wide;
  conflicts are flagged).
- **Ctrl+F** searches names / refdes / signals / parts across the tree.

## 5. Document and share

- Click any element → **📝 Edit documentation…** — markdown notes with
  images, kept in the central searchable vault (right dock, second tab).
- **File → Export**: full **PDF report** (flowcharts, tables, margins, notes
  appendix), **Excel** macro-enabled workbook, **HD PNG** flowchart,
  notes as Markdown / HTML / PDF.
- Save your work as a `.ptproj` file (`Ctrl+S`) — one file holds every tree,
  state, note and image.

## Command line & AI

```bat
powertree-cli info MyBoard.ptproj
powertree-cli validate MyBoard.ptproj      :: exit 1 on violations (CI gate)
powertree-cli solve MyBoard.ptproj --state "Low Power" --json
powertree-cli export pdf MyBoard.ptproj -o report.pdf
```

AI assistants connect through MCP: see `examples/mcp.json.example`.
