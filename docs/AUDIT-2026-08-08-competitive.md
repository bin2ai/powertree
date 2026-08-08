# PowerTree v0.8.0 — competitive audit vs. industry tools

Date: 2026-08-08. Benchmark: **ADI LTpowerPlanner III** (the de-facto free
system-level power-tree tool, shipped inside LTpowerCAD), with notes on TI
WEBENCH-class tools and the true incumbent — Excel. Guiding constraint from
the project owner: **do not over-engineer what already works simply.**

---

## 1. Where PowerTree already leads

| Capability | PowerTree v0.8.0 | LTpowerPlanner III |
|---|---|---|
| Corner analysis | min/typ/max solved simultaneously | single operating point |
| Margin analysis | voltage windows, limits, derating policy, series ratings, sequencing — flagged live | none (numbers only, you eyeball them) |
| Operating states | named states w/ per-element overrides, per-state validation | none |
| Findings workflow | waivers with justification (audit trail) | none |
| Efficiency model | flat % **or** datasheet η-vs-load curve, interpolated | fixed efficiency per converter |
| Duty cycle / avg-vs-peak | yes | no |
| Documentation | markdown notes vault w/ images, linked to elements, exported into reports | text annotations on the canvas |
| Reports | PDF w/ exec summary + verdict, single-file HTML, Excel (macros/outline), CSV, PNG, bundle | on-screen summary report; copy diagram to clipboard |
| Automation | CLI with CI gate (`validate --strict`), JSON everywhere, MCP for AI assistants | none |
| Version control | diff-friendly JSON project file, git-ready; project-local part library | binary-ish save files |
| Extensibility | user/project template & part libraries (JSON) | fixed element set (links into ADI part ecosystem instead) |
| Analytics | rail headroom, load-growth capacity, top consumers, heat map | system totals + efficiency |
| Platform | Windows-first, runs on Linux (CI-proven), pip + installer | Windows only |

For review culture (corners, margins, waivers, states, CI) PowerTree is
already ahead of the industry baseline — that is the moat; keep sharpening it.

## 2. Where LTpowerPlanner leads — the honest gaps

1. **Multi-output converters & multi-input loads (PMICs!).** LTpowerPlanner
   models a PMIC as one block with several outputs, and parallel outputs
   with current sharing. PowerTree's strict tree cannot; today a PMIC is
   several converter elements sharing a refdes/block. *Disposition:* the
   block/refdes workaround is genuinely adequate for budgeting (loss per
   rail is per-rail anyway) — document the pattern and ship a PMIC template
   demonstrating it. Full multi-output/DAG stays on the roadmap; do NOT
   half-build it.
2. **Cost and PCB-area rollups.** LTpowerPlanner sums converter board area
   (and cost) so architectures can be compared on more than efficiency.
   These are two optional floats per element plus summation — high value,
   trivially simple. *Recommend implementing.*
3. **Architecture comparison as a first-class flow.** Their core pitch is
   "draw two trees, compare." We have the data (trees + analytics) but no
   side-by-side view. A compare table (P/η/loss/cost/area/findings per tree,
   GUI + report section) is simple and closes the pitch gap.
   *Recommend implementing.*
4. **Vendor part ecosystem.** LTpowerPlanner links converters into
   LTpowerCAD/LTspice for real ADI part design; WEBENCH picks TI parts.
   *Disposition: anti-goal.* A parts database is a maintenance treadmill and
   vendor tools already do it well. PowerTree's vendor-neutral answer is the
   datasheet link + η-curve + template library. Add only a one-click "open
   datasheet" button.

## 3. Usability audit — friction an EE feels in the first hour

1. **Unit entry (top friction).** Values are entered in base units with
   decimal spinboxes: a 100 mA load is typed `0.1`, a 50 mΩ bead `0.05`.
   Engineers think in mA/mΩ/µA. Fix simply: unit-aware entry accepting SI
   suffixes (`100m`, `4.7u`, `2.2k`) in every electrical field, displayed
   back in engineering notation. One parser, applied everywhere. *This is
   the single highest-leverage UX improvement available.*
2. **Inline rename.** Renaming means opening Properties; F2 / double-click
   rename on the canvas card and list row is expected behavior.
3. **Datasheet link is dead text.** Make it clickable (open URL/file).
4. **Block collapse discoverability.** The ⤢ chip and context menu work,
   but double-clicking a block outline/header should toggle collapse — the
   gesture everyone tries first.
5. **New-tree emptiness.** A brand-new tree shows an empty canvas; a
   centered ghost hint ("⊕ Add a source to begin — or Ctrl+T for a
   template") costs nothing and orients non-EE users.
6. Nice-but-optional polish (defer freely): edge hover highlighting,
   Esc-to-clear-search, remembering per-tree zoom.

## 4. For "others alike" (managers, reviewers, adjacent disciplines)

Already strong: executive PDF page with a plain-language verdict, one-file
HTML report, heat map, growth capacity ("+N % headroom"), copy-image for
slides. The two additions above (cost/area rollups, tree comparison) are
exactly the artifacts non-EE stakeholders ask for in architecture reviews.
No "simple mode" needed — the detail cascade already serves both audiences;
adding modes would be over-engineering.

## 5. Anti-goals — things that work simply today; leave them alone

- **No SPICE/simulation.** DC budgeting is the job; LTspice exists.
- **No vendor part database.** Datasheet links + η curves + user templates.
- **No cloud/accounts/collaboration server.** The git-friendly single-file
  format IS the collaboration story.
- **No plugin architecture.** The JSON template/library covers extension.
- **No general DAG editor until multi-output demand is proven.** The
  block-with-shared-refdes pattern covers PMIC budgeting today.
- **No mode switches / workspace layouts.** Detail cascade + settings are
  enough knobs.
- The solver, file format, undo model and four-surface API are stable and
  simple — resist rewrites.

## 6. Recommended work, in order (all deliberately small)

| # | Item | Size | Why |
|---|---|---|---|
| 1 | SI-suffix unit entry in every electrical field | S | kills the #1 daily friction |
| 2 | Cost ($) + area (mm²) optional fields with tree/exec rollups | S | matches LTpowerPlanner's compare axes |
| 3 | "Compare trees" table (GUI dialog + PDF/HTML section) | S–M | first-class architecture comparison |
| 4 | Clickable datasheet links; F2/double-click rename; double-click block collapse; empty-canvas hint | S | expected gestures |
| 5 | PMIC modeling pattern: doc section + shipped multi-rail PMIC template | S | closes the perception gap honestly |

Everything above is additive UI/fields — no solver, format-breaking, or
architectural change. Deferred items remain in ROADMAP.md unchanged.

### Sources
- [LTpowerCAD and LTpowerPlanner — Analog Devices](https://www.analog.com/en/lp/ltpowercad.html)
- [AN-164: LTpowerPlanner, A System-Level Power Architecture Design Tool](https://www.analog.com/en/resources/app-notes/an-164.html)
- [Introduction of LTpowerPlanner Program — Analog Devices](https://www.analog.com/en/resources/technical-articles/introduction-of-ltpowerplanner-program-a-system-level-power-architecture-design-tool.html)
- [LTpowerPlanner III Quick Start Guide (Digi-Key mirror)](https://www.digikey.com/htmldatasheets/production/3264161/0/0/1/ltpowerplanner-iii-quick-start-guide.html)
- [LTpowerPlanner: A system-level power architecture design tool — EDN](https://www.edn.com/ltpowerplanner-a-system-level-power-architecture-design-tool/)
