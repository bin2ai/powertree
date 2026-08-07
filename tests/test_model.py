"""Unit tests for the model, solver and serialization (hand-checked math)."""

import math
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from powertree.model.elements import (   # noqa: E402
    Project, PowerTree, Source, Converter, Load, SeriesElement,
    LimitType, LoadType,
)
from powertree.model.calc import solve_tree, block_power, fmt_si  # noqa: E402
from powertree.model import serialization  # noqa: E402
from powertree.sampledata import build_sample_project  # noqa: E402


def make_tree():
    return PowerTree("t")


def test_current_load_direct():
    t = make_tree()
    s = t.add_element(Source(v_min=9, v_typ=10, v_max=11))
    t.add_element(Load(load_type=LoadType.CURRENT, value_typ=1.0), parent_id=s.id)
    r = solve_tree(t)
    assert math.isclose(r.get(s.id, "typ").i_out, 1.0, rel_tol=1e-6)
    assert math.isclose(r.get(s.id, "typ").p_out, 10.0, rel_tol=1e-6)
    assert math.isclose(r.get(s.id, "min").p_out, 9.0, rel_tol=1e-6)
    assert math.isclose(r.get(s.id, "max").p_out, 11.0, rel_tol=1e-6)


def test_power_load_direct():
    t = make_tree()
    s = t.add_element(Source(v_min=5, v_typ=5, v_max=5))
    ld = t.add_element(Load(load_type=LoadType.POWER, value_typ=2.5), parent_id=s.id)
    r = solve_tree(t)
    assert math.isclose(r.get(ld.id, "typ").i_in, 0.5, rel_tol=1e-6)
    assert math.isclose(r.get(s.id, "typ").p_out, 2.5, rel_tol=1e-6)


def test_converter_efficiency():
    t = make_tree()
    s = t.add_element(Source(v_min=10, v_typ=10, v_max=10))
    c = t.add_element(Converter(efficiency_pct=90, vout_min=5, vout_typ=5, vout_max=5),
                      parent_id=s.id)
    t.add_element(Load(load_type=LoadType.CURRENT, value_typ=1.0), parent_id=c.id)
    r = solve_tree(t)
    cr = r.get(c.id, "typ")
    assert math.isclose(cr.p_out, 5.0, rel_tol=1e-6)
    assert math.isclose(cr.p_in, 5.0 / 0.9, rel_tol=1e-6)
    assert math.isclose(cr.i_in, 5.0 / 0.9 / 10.0, rel_tol=1e-6)
    assert math.isclose(cr.p_loss, 5.0 / 0.9 - 5.0, rel_tol=1e-6)


def test_series_resistance_current_load():
    t = make_tree()
    s = t.add_element(Source(v_min=10, v_typ=10, v_max=10))
    se = t.add_element(SeriesElement(resistance_ohm=1.0), parent_id=s.id)
    ld = t.add_element(Load(load_type=LoadType.CURRENT, value_typ=1.0), parent_id=se.id)
    r = solve_tree(t)
    assert math.isclose(r.get(ld.id, "typ").v_in, 9.0, rel_tol=1e-6)
    assert math.isclose(r.get(se.id, "typ").p_loss, 1.0, rel_tol=1e-6)
    assert math.isclose(r.get(s.id, "typ").p_out, 10.0, rel_tol=1e-6)


def test_series_resistance_power_load_fixed_point():
    # V = 10 - I*1, I = 8/V  ->  V^2 - 10V + 8 = 0 -> V = (10+sqrt(68))/2
    t = make_tree()
    s = t.add_element(Source(v_min=10, v_typ=10, v_max=10))
    se = t.add_element(SeriesElement(resistance_ohm=1.0), parent_id=s.id)
    ld = t.add_element(Load(load_type=LoadType.POWER, value_typ=8.0), parent_id=se.id)
    r = solve_tree(t)
    v_expected = (10 + math.sqrt(100 - 32)) / 2
    assert math.isclose(r.get(ld.id, "typ").v_in, v_expected, rel_tol=1e-4)
    assert r.converged


def test_series_bounding_never_breaks():
    t = make_tree()
    s = t.add_element(Source(v_min=3.0, v_typ=3.3, v_max=3.6))
    se = t.add_element(SeriesElement(resistance_ohm=1e6), parent_id=s.id)
    t.add_element(Load(load_type=LoadType.CURRENT, value_typ=1.0), parent_id=se.id)
    r = solve_tree(t)   # must not raise / divide by zero
    assert any("collapsed" in w.message for w in r.warnings)


def test_single_source_enforced():
    t = make_tree()
    t.add_element(Source())
    with pytest.raises(ValueError):
        t.add_element(Source())


def test_load_is_leaf():
    t = make_tree()
    s = t.add_element(Source())
    ld = t.add_element(Load(), parent_id=s.id)
    with pytest.raises(ValueError):
        t.add_element(Load(), parent_id=ld.id)


def test_source_limit_warning():
    t = make_tree()
    s = t.add_element(Source(v_min=5, v_typ=5, v_max=5,
                             limit_type=LimitType.CURRENT, limit_value=1.0))
    t.add_element(Load(load_type=LoadType.CURRENT, value_typ=1.5), parent_id=s.id)
    r = solve_tree(t)
    assert any(w.severity == "error" and w.element_id == s.id for w in r.warnings)


def test_load_voltage_window_warning():
    t = make_tree()
    s = t.add_element(Source(v_min=3.0, v_typ=3.3, v_max=3.6))
    se = t.add_element(SeriesElement(resistance_ohm=2.0), parent_id=s.id)
    t.add_element(Load(load_type=LoadType.CURRENT, value_typ=0.5,
                       v_in_min=3.0, v_in_max=3.6), parent_id=se.id)
    r = solve_tree(t)   # 1 V drop -> undervoltage
    assert any("undervoltage" in w.message for w in r.warnings)


def test_block_power_no_double_count():
    p = build_sample_project()
    tree = p.trees[0]
    r = solve_tree(tree)
    for bid in tree.blocks:
        assert block_power(tree, r, bid, "typ") > 0
    # Zynq block: every member's parent is outside the block, so the block
    # power must equal the plain sum of member input powers (no double count)
    zynq = next(b for b in tree.blocks.values() if "Zynq" in b.name)
    expected = sum(r.get(e.id, "typ").p_in
                   for e in tree.block_members(zynq.id))
    assert math.isclose(block_power(tree, r, zynq.id, "typ"), expected,
                        rel_tol=1e-9)
    # regulator block: converter + its Iq load; block power counts the
    # converter INPUT power plus the Iq load, not the downstream double
    reg = next(b for b in tree.blocks.values() if "5V Intermediate" in b.name)
    members = tree.block_members(reg.id)
    assert len(members) == 2
    expected = sum(r.get(e.id, "typ").p_in for e in members)
    assert math.isclose(block_power(tree, r, reg.id, "typ"), expected,
                        rel_tol=1e-9)


def test_serialization_roundtrip():
    p = build_sample_project()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "demo.ptproj")
        serialization.save_project(p, path)
        p2 = serialization.load_project(path)
    assert serialization.project_to_dict(p2) == serialization.project_to_dict(p)
    # solver produces identical numbers on the reloaded project
    r1 = solve_tree(p.trees[0])
    r2 = solve_tree(p2.trees[0])
    for el_id in p.trees[0].elements:
        assert math.isclose(r1.get(el_id).p_in, r2.get(el_id).p_in, rel_tol=1e-9)


def test_fmt_si():
    assert fmt_si(0.0123, "A") == "12.3 mA"
    assert fmt_si(1500, "W") == "1.5 kW"
    assert fmt_si(0.0000015, "A") == "1.5 µA"


def test_move_element_validation():
    t = make_tree()
    s = t.add_element(Source())
    c = t.add_element(Converter(), parent_id=s.id)
    ld = t.add_element(Load(), parent_id=s.id)
    t.move_element(ld.id, c.id)
    assert t.elements[ld.id].parent_id == c.id
    with pytest.raises(ValueError):
        t.move_element(c.id, ld.id)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
