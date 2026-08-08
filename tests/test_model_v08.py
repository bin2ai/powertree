"""Tests for v0.8.0 model depth: resistive loads, duty cycle, unregulated
stages, power-up sequencing."""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from powertree.model.elements import (  # noqa: E402
    PowerTree, Project, Source, Converter, Load, SeriesElement, LoadType,
)
from powertree.model.calc import solve_tree  # noqa: E402
from powertree.model import serialization  # noqa: E402


def test_resistive_load_ohms_law():
    t = PowerTree("t")
    src = t.add_element(Source(v_min=4.5, v_typ=5.0, v_max=5.5))
    ld = t.add_element(Load(load_type=LoadType.RESISTIVE,
                            resistance_ohm=10.0), parent_id=src.id)
    r = solve_tree(t)
    # I = V/R, P = V^2/R at each corner
    for corner, v in (("min", 4.5), ("typ", 5.0), ("max", 5.5)):
        res = r.get(ld.id, corner)
        assert math.isclose(res.i_in, v / 10.0, rel_tol=1e-6), corner
        assert math.isclose(res.p_in, v * v / 10.0, rel_tol=1e-6), corner


def test_resistive_load_behind_series_r_converges():
    # voltage divider: 10 V source, 5 ohm series into 5 ohm load -> 5 V, 1 A
    t = PowerTree("t")
    src = t.add_element(Source(v_min=10, v_typ=10, v_max=10))
    se = t.add_element(SeriesElement(resistance_ohm=5.0), parent_id=src.id)
    ld = t.add_element(Load(load_type=LoadType.RESISTIVE, resistance_ohm=5.0),
                       parent_id=se.id)
    r = solve_tree(t)
    assert r.converged
    assert math.isclose(r.get(ld.id, "typ").v_in, 5.0, rel_tol=1e-3)
    assert math.isclose(r.get(ld.id, "typ").i_in, 1.0, rel_tol=1e-3)


def test_duty_cycle_average_vs_peak():
    t = PowerTree("t")
    src = t.add_element(Source(v_min=5, v_typ=5, v_max=5))
    ld = t.add_element(Load(load_type=LoadType.CURRENT, value_typ=1.0,
                            value_max=2.0, duty_cycle_pct=25.0),
                       parent_id=src.id)
    r = solve_tree(t)
    # typ corner: duty-weighted average 0.25 A; max corner: full 2 A peak
    assert math.isclose(r.get(ld.id, "typ").i_in, 0.25, rel_tol=1e-6)
    assert math.isclose(r.get(ld.id, "max").i_in, 2.0, rel_tol=1e-6)
    assert math.isclose(r.get(src.id, "typ").p_out, 1.25, rel_tol=1e-6)


def test_unregulated_converter_tracks_vin():
    t = PowerTree("t")
    src = t.add_element(Source(v_min=10, v_typ=12, v_max=14))
    c = t.add_element(Converter(topology="unregulated", ratio=0.5,
                                efficiency_pct=90.0), parent_id=src.id)
    ld = t.add_element(Load(load_type=LoadType.CURRENT, value_typ=1.0),
                       parent_id=c.id)
    r = solve_tree(t)
    for corner, vin in (("min", 10.0), ("typ", 12.0), ("max", 14.0)):
        res = r.get(c.id, corner)
        assert math.isclose(res.v_out, vin * 0.5, rel_tol=1e-6), corner
        assert math.isclose(r.get(ld.id, corner).v_in, vin * 0.5,
                            rel_tol=1e-6)
    # load voltage window catches the tracking rail going out of range
    ld.v_in_min = 5.5
    r2 = solve_tree(t)
    assert any("undervoltage" in w.message and w.corner == "min"
               for w in r2.warnings)


def test_unregulated_behind_series_drop():
    t = PowerTree("t")
    src = t.add_element(Source(v_min=10, v_typ=10, v_max=10))
    se = t.add_element(SeriesElement(resistance_ohm=1.0), parent_id=src.id)
    c = t.add_element(Converter(topology="unregulated", ratio=2.0,
                                efficiency_pct=100.0), parent_id=se.id)
    t.add_element(Load(load_type=LoadType.CURRENT, value_typ=0.5),
                  parent_id=c.id)
    r = solve_tree(t)
    assert r.converged
    vin = r.get(c.id, "typ").v_in
    assert math.isclose(r.get(c.id, "typ").v_out, vin * 2.0, rel_tol=1e-4)


def test_sequencing_violation_flagged():
    t = PowerTree("t")
    src = t.add_element(Source(v_min=12, v_typ=12, v_max=12))
    up = t.add_element(Converter(name="5V", seq_order=3, vout_min=5,
                                 vout_typ=5, vout_max=5), parent_id=src.id)
    down = t.add_element(Converter(name="1V", seq_order=1, vout_min=1,
                                   vout_typ=1, vout_max=1), parent_id=up.id)
    t.add_element(Load(value_typ=0.1), parent_id=down.id)
    r = solve_tree(t)
    assert any("Sequencing" in w.message and w.element_id == down.id
               for w in r.warnings)
    # fixing the order clears the finding
    down.seq_order = 4
    r2 = solve_tree(t)
    assert not any("Sequencing" in w.message for w in r2.warnings)
    # unspecified (0) never flags
    down.seq_order = 0
    r3 = solve_tree(t)
    assert not any("Sequencing" in w.message for w in r3.warnings)


def test_new_fields_roundtrip(tmp_path):
    p = Project("x")
    t = p.new_tree("m")
    src = t.add_element(Source())
    t.add_element(Converter(topology="unregulated", ratio=0.5, seq_order=2),
                  parent_id=src.id)
    t.add_element(Load(load_type=LoadType.RESISTIVE, resistance_ohm=22.0,
                       duty_cycle_pct=30.0), parent_id=src.id)
    path = os.path.join(tmp_path, "v08.ptproj")
    serialization.save_project(p, path)
    p2 = serialization.load_project(path)
    t2 = p2.trees[0]
    c2 = next(e for e in t2.elements.values() if e.kind == "converter")
    l2 = next(e for e in t2.elements.values() if e.kind == "load")
    assert c2.topology == "unregulated" and c2.ratio == 0.5 \
        and c2.seq_order == 2
    assert l2.load_type == LoadType.RESISTIVE and l2.resistance_ohm == 22.0 \
        and l2.duty_cycle_pct == 30.0


def test_migration_framework():
    # a version-0 payload (no version field) upgrades on load
    p = Project("m")
    t = p.new_tree("t")
    t.add_element(Source())
    data = serialization.project_to_dict(p)
    data.pop("version")
    upgraded = serialization.project_from_dict(dict(data))
    assert upgraded.trees[0].source is not None
    # future versions are refused with a clear message
    data["version"] = 999
    with pytest.raises(ValueError, match="newer than this app"):
        serialization.project_from_dict(data)
    # a gap in the migration chain fails loudly, not silently
    data["version"] = -1
    with pytest.raises(ValueError, match="migration path"):
        serialization.migrate(dict(data))


def test_subtree_copy_paste_roundtrip():
    src_tree = PowerTree("a")
    s = src_tree.add_element(Source(v_min=5, v_typ=5, v_max=5))
    c = src_tree.add_element(Converter(name="LDO", vout_typ=1.8,
                                       vout_min=1.8, vout_max=1.8),
                             parent_id=s.id)
    src_tree.add_element(Load(name="Core", value_typ=0.1), parent_id=c.id)
    dicts = serialization.subtree_to_dicts(src_tree, c.id)
    dst = PowerTree("b")
    s2 = dst.add_element(Source(v_min=5, v_typ=5, v_max=5))
    root = serialization.dicts_to_subtree(dst, dicts, s2.id)
    assert root.name == "LDO" and root.id != c.id
    kids = dst.children_of(root.id)
    assert len(kids) == 1 and kids[0].name == "Core"
    solve_tree(dst)
    # pasting a load under a load rolls back atomically
    load_dicts = serialization.subtree_to_dicts(dst, kids[0].id)
    n = len(dst.elements)
    with pytest.raises(ValueError):
        serialization.dicts_to_subtree(dst, load_dicts, kids[0].id)
    assert len(dst.elements) == n


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
