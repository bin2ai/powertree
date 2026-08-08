# Roadmap — deferred architecture items

Items consciously deferred from the 2026-08-07 audit, with enough design to
start when scheduled. Everything else from that audit shipped in v0.8.0
(see docs/AUDIT-2026-08-07.md).

## Parallel / ORed sources (multi-parent DAG)
Diode-OR of two supplies, load switches selecting rails, redundant feeds.
Requires: elements gaining multiple parents (DAG, not tree) with per-edge
metadata (diode drop, switch state); solver distributing load current between
feeds (priority or sharing model); file format v2; layout for reconvergent
paths; per-state feed selection. Suggested model: keep the tree as the
"primary" path and add explicit OR-node elements holding [(feed_element_id,
drop_v, active_in_states)] — solver treats the OR node as a source selector
per state, which avoids general DAG flow while covering the common cases.

## Temperature derating curves
Per-part derating tables (rating vs ambient), project-level ambient
temperature (per state), and margin checks evaluated at derated ratings.
The flat derating policy (Project.derating_pct) remains the interim tool.

## Cross-tree merged net solving
Same-named nets across trees solved as one electrical node (shared battery
between subsystem trees). Requires a project-level solve pass that stitches
per-tree results at shared nets and iterates. The Nets view/report now
labels the current behavior (name registry + conflict detection only).

## Code-signed installer
Needs an OV/EV code-signing certificate (purchase + CI secret). Wire into
installer/build_installer.ps1 (signtool) and the release workflow once a
certificate exists.

## String externalization / i18n
Wrap user-visible strings with Qt translation and ship .ts/.qm files.
