"""Tests for operating states (scenarios) and series-element ratings."""

import math
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from powertree.model.elements import (   # noqa: E402
    Project, PowerTree, Source, Load, SeriesElement, LoadType,
)
from powertree.model.calc import solve_tree  # noqa: E402
from powertree.model.scenarios import (  # noqa: E402
    apply_scenario, materialize_scenario, rename_scenario, delete_scenario)
from powertree.model import serialization  # noqa: E402
from powertree.sampledata import build_sample_project  # noqa: E402
from powertree import api  # noqa: E402


def simple_tree():
    t = PowerTree("t")
    src = t.add_element(Source(v_min=5, v_typ=5, v_max=5))
    ld = t.add_element(Load(load_type=LoadType.CURRENT, value_typ=1.0),
                       parent_id=src.id)
    return t, src, ld


# ------------------------------------------------------------ series ratings
def test_series_current_rating_flags():
    t = PowerTree("t")
    src = t.add_element(Source(v_min=5, v_typ=5, v_max=5))
    fuse = t.add_element(SeriesElement(resistance_ohm=0.01, i_max=0.5),
                         parent_id=src.id)
    t.add_element(Load(load_type=LoadType.CURRENT, value_typ=1.0),
                  parent_id=fuse.id)
    r = solve_tree(t)
    assert any("current rating exceeded" in w.message for w in r.warnings)


def test_series_dissipation_and_window_flags():
    t = PowerTree("t")
    src = t.add_element(Source(v_min=5, v_typ=5, v_max=5))
    se = t.add_element(SeriesElement(resistance_ohm=1.0, p_max=0.5,
                                     v_in_min=6.0), parent_id=src.id)
    t.add_element(Load(load_type=LoadType.CURRENT, value_typ=1.0),
                  parent_id=se.id)
    r = solve_tree(t)
    msgs = " | ".join(w.message for w in r.warnings)
    assert "dissipation rating exceeded" in msgs      # 1 W loss > 0.5 W
    assert "input undervoltage" in msgs               # 5 V < required 6 V


def test_series_rating_healthy_is_silent():
    t = PowerTree("t")
    src = t.add_element(Source(v_min=5, v_typ=5, v_max=5))
    se = t.add_element(SeriesElement(resistance_ohm=0.01, i_max=5.0,
                                     p_max=1.0, v_in_min=4.5, v_in_max=5.5),
                       parent_id=src.id)
    t.add_element(Load(load_type=LoadType.CURRENT, value_typ=1.0),
                  parent_id=se.id)
    r = solve_tree(t)
    assert not r.warnings


# ---------------------------------------------------------------- scenarios
def test_apply_scenario_overrides_load():
    t, src, ld = simple_tree()
    ld.scenario_overrides["Low"] = {"value_typ": 0.1}
    r_base = solve_tree(t)
    r_low = solve_tree(t, "Low")
    assert math.isclose(r_base.get(src.id).p_out, 5.0, rel_tol=1e-6)
    assert math.isclose(r_low.get(src.id).p_out, 0.5, rel_tol=1e-6)
    # original untouched
    assert ld.value_typ == 1.0


def test_scenario_ignores_disallowed_fields():
    t, src, ld = simple_tree()
    ld.scenario_overrides["X"] = {"parent_id": "hack", "value_typ": 0.5}
    applied = apply_scenario(t, "X")
    el = applied.elements[ld.id]
    assert el.parent_id == src.id          # structural fields never overridden
    assert el.value_typ == 0.5


def test_materialize_rename_delete():
    p = Project("x")
    t = p.new_tree("Main")
    src = t.add_element(Source(v_min=5, v_typ=5, v_max=5))
    ld = t.add_element(Load(value_typ=1.0), parent_id=src.id)
    p.scenarios = ["Sleep"]
    ld.scenario_overrides["Sleep"] = {"value_typ": 0.01}
    baked = materialize_scenario(p, t, "Sleep")
    assert baked.name == "Main [Sleep]" and len(p.trees) == 2
    assert baked.elements[ld.id].value_typ == 0.01
    assert baked.elements[ld.id].scenario_overrides == {}
    rename_scenario(p, "Sleep", "Standby")
    assert p.scenarios == ["Standby"]
    assert "Standby" in ld.scenario_overrides
    delete_scenario(p, "Standby")
    assert p.scenarios == [] and ld.scenario_overrides == {}


def test_scenarios_roundtrip():
    p = build_sample_project()
    assert p.scenarios == ["Low Power", "Performance"]
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "s.ptproj")
        serialization.save_project(p, path)
        p2 = serialization.load_project(path)
    assert p2.scenarios == ["Low Power", "Performance"]
    assert serialization.project_to_dict(p2) == serialization.project_to_dict(p)


def test_demo_states_change_power_sensibly():
    p = build_sample_project()
    tree = p.trees[0]
    src = tree.source
    base = solve_tree(tree).get(src.id, "typ").p_out
    low = solve_tree(tree, "Low Power").get(src.id, "typ").p_out
    perf = solve_tree(tree, "Performance").get(src.id, "typ").p_out
    assert low < base < perf, (low, base, perf)


def test_api_solve_with_state_and_validate_states():
    p = build_sample_project()
    r = api.solve(p, None, "Low Power")
    assert r["scenario"] == "Low Power"
    with pytest.raises(ValueError, match="Unknown state"):
        api.solve(p, None, "Nope")
    v = api.validate(p)
    states = {f["state"] for f in v["findings"]}
    assert "Base" in states      # per-state findings are labelled


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
