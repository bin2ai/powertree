# MEMORY.md - PowerTree

Running log. Keep current; this is printed into context at session start.

## Status
- 2026-08-06: project scaffolded.
- 2026-08-07: **v0.1 fully working.** PySide6 desktop app implementing every requirement
  from the original goal: multi-tree projects (.ptproj), one-source-per-tree constraint,
  converters (η %, Vout corners, pass-through rail, quiescent I), current/power loads
  (typ/peak + allowed Vin window), bounded series-R elements, blocks with aggregate
  power, bottom-up auto-refresh solver (min/typ/max corners), margin/warning analysis,
  flowchart (TD/LR/custom drag, 90° edges, legend, collapse/expand, power text, search
  highlight) + list view, hierarchical markdown notes w/ images + element links,
  exports: PDF report, .xlsm Excel (COM VBA; .xlsx+.bas fallback), HD PNG, notes
  MD/HTML/PDF. 14 pytest tests green; GUI smoke-tested offscreen + native launch OK.

## Deliverables
- Working app: `main.py` / `PowerTree.bat` (venv `.venv`, Python 3.12).
- `examples/DemoBoard.ptproj` demo project (loads on startup by default).
- Test suite `tests/test_model.py` (14 passing).

## Decisions
- PySide6 + QGraphicsScene (not web/Electron): offline requirement, HD render reuse
  between GUI and exports via headless `render_tree_image()`.
- `.ptproj` = versioned JSON, fully self-contained (notes + base64 images embedded) —
  diff-friendly and future-proof (`version` gate in serialization.py).
- Solver: damped fixed-point (0.7 gain, 80 iters) handles series-R × power-load
  coupling; rails floored at 1 mV so pathological inputs warn instead of crash.
- Excel macros via COM injection at export time (no vbaProject.bin shipped); graceful
  documented fallback when VBA trust is disabled (was the case on this machine).

## Open threads
- Roadmap candidates (user asked for ideas; also in README): resistive loads, operating
  modes/scenarios, undo-redo, temperature derating, CSV/BOM import, part library,
  rail sequencing checks, per-corner load values.
- If the user enables Excel VBA trust, re-test true `.xlsm` path end-to-end.
