"""Operating states (scenarios).

A project defines named states ("Low Power", "High Power", …). Any element can
override selected numeric fields per state (a load draws less in sleep, a
battery sags, a regulator's efficiency shifts). Solving against a state
applies the overrides on a copy — element ids are preserved, so results map
straight back onto the canvas/list — and a state can also be MATERIALIZED as
a standalone tree for side-by-side comparison or archival.
"""

from __future__ import annotations

import copy

from .elements import PowerTree, Project, ElementKind

# fields an element may override per state, by kind
SCENARIO_FIELDS = {
    ElementKind.SOURCE: ("v_min", "v_typ", "v_max"),
    ElementKind.CONVERTER: ("efficiency_pct", "quiescent_ma"),
    ElementKind.LOAD: ("value_typ", "value_max"),
    ElementKind.SERIES: ("resistance_ohm",),
}

FIELD_LABELS = {
    "v_min": "V min (V)", "v_typ": "V typ (V)", "v_max": "V max (V)",
    "efficiency_pct": "Efficiency (%)", "quiescent_ma": "Iq (mA)",
    "value_typ": "Value typ", "value_max": "Value peak",
    "resistance_ohm": "Resistance (Ω)",
}


def clone_tree(tree: PowerTree) -> PowerTree:
    """Deep copy preserving all ids."""
    new = PowerTree(tree.name, tree_id=tree.id)
    new.description = tree.description
    new.orientation = tree.orientation
    new.elements = {eid: copy.deepcopy(el) for eid, el in tree.elements.items()}
    new.blocks = {bid: copy.deepcopy(b) for bid, b in tree.blocks.items()}
    return new


def apply_scenario(tree: PowerTree, scenario: str) -> PowerTree:
    """Copy of `tree` with the state's overrides applied (ids preserved)."""
    out = clone_tree(tree)
    for el in out.elements.values():
        overrides = (el.scenario_overrides or {}).get(scenario, {})
        allowed = SCENARIO_FIELDS.get(el.kind, ())
        for field_name, value in overrides.items():
            if field_name in allowed and value is not None:
                setattr(el, field_name, float(value))
    return out


def scenario_of_tree(tree: PowerTree, scenario: str | None) -> PowerTree:
    return apply_scenario(tree, scenario) if scenario else tree


def elements_with_overrides(tree: PowerTree, scenario: str) -> list:
    return [el for el in tree.elements.values()
            if (el.scenario_overrides or {}).get(scenario)]


def materialize_scenario(project: Project, tree: PowerTree,
                         scenario: str) -> PowerTree:
    """Bake a state into a standalone tree added to the project."""
    baked = apply_scenario(tree, scenario)
    # fresh identity so both trees can coexist
    import uuid
    baked.id = uuid.uuid4().hex[:12]
    baked.name = f"{tree.name} [{scenario}]"
    baked.description = (f"Auto-generated from '{tree.name}' with state "
                         f"'{scenario}' applied. {tree.description}").strip()
    for el in baked.elements.values():
        el.scenario_overrides = {}
    project.trees.append(baked)
    return baked


def rename_scenario(project: Project, old: str, new: str) -> None:
    project.scenarios = [new if s == old else s for s in project.scenarios]
    for tree in project.trees:
        for el in tree.elements.values():
            if old in (el.scenario_overrides or {}):
                el.scenario_overrides[new] = el.scenario_overrides.pop(old)


def delete_scenario(project: Project, name: str) -> None:
    project.scenarios = [s for s in project.scenarios if s != name]
    for tree in project.trees:
        for el in tree.elements.values():
            (el.scenario_overrides or {}).pop(name, None)
