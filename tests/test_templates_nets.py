"""Tests for device templates, the global net registry and the Zynq demo."""

import math
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from powertree.model.elements import (   # noqa: E402
    Project, PowerTree, Source, Converter, SeriesElement, SeriesType,
    ElementKind,
)
from powertree.model.calc import solve_tree  # noqa: E402
from powertree.model.nets import collect_nets, input_net  # noqa: E402
from powertree.model import serialization  # noqa: E402
from powertree.templates import (  # noqa: E402
    TEMPLATES, template_by_key, instantiate_template)
from powertree.sampledata import build_sample_project  # noqa: E402


def test_templates_have_consistent_rails():
    for t in TEMPLATES:
        external = {i.rail for i in t.items if not i.rail.startswith("@")}
        assert external <= set(t.rails), \
            f"{t.key}: items use unmapped rails {external - set(t.rails)}"
        names = [i.name for i in t.items]
        assert len(names) == len(set(names)), f"{t.key}: duplicate item names"
        for i in t.items:
            if i.rail.startswith("@"):
                assert i.rail[1:] in names, \
                    f"{t.key}: '{i.name}' references unknown sibling"


def test_instantiate_zynq_template():
    tree = PowerTree("t")
    src = tree.add_element(Source(v_min=11.4, v_typ=12, v_max=12.6))
    rails = {}
    for key, vout in (("1.0V", 1.0), ("1.8V", 1.8), ("3.3V", 3.3),
                      ("1.5V (DDR IO)", 1.5)):
        c = tree.add_element(Converter(
            name=f"{vout}V reg", vout_min=vout * 0.99, vout_typ=vout,
            vout_max=vout * 1.01), parent_id=src.id)
        rails[key] = c.id
    created = instantiate_template(tree, template_by_key("zynq7020"), rails,
                                   block_name="Zynq U1", refdes="U1")
    assert len(created) == 9
    assert all(e.refdes == "U1" for e in created)
    assert all(e.part_number == "XC7Z020-1CLG484" for e in created)
    block_ids = {e.block_id for e in created}
    assert len(block_ids) == 1 and None not in block_ids
    r = solve_tree(tree)     # solves cleanly with all windows satisfied
    assert not [w for w in r.warnings if w.severity == "error"]


def test_instantiate_regulator_block_sibling_reference():
    tree = PowerTree("t")
    src = tree.add_element(Source(v_min=11.4, v_typ=12, v_max=12.6))
    created = instantiate_template(
        tree, template_by_key("buck_block"), {"VIN": src.id}, refdes="U10")
    kinds = sorted(e.kind for e in created)
    assert kinds == [ElementKind.CONVERTER, ElementKind.LOAD]
    conv = next(e for e in created if e.kind == ElementKind.CONVERTER)
    iq = next(e for e in created if e.kind == ElementKind.LOAD)
    assert conv.parent_id == src.id and iq.parent_id == src.id


def test_instantiate_missing_rail_raises():
    tree = PowerTree("t")
    tree.add_element(Source())
    with pytest.raises(ValueError, match="not mapped"):
        instantiate_template(tree, template_by_key("qspi_flash"), {})


def test_series_type_fields_roundtrip():
    tree = PowerTree("t")
    src = tree.add_element(Source())
    tree.add_element(SeriesElement(
        series_type=SeriesType.FERRITE_BEAD, resistance_ohm=0.05,
        inductance_uh=2.2, rating="600R@100MHz"), parent_id=src.id)
    p = Project("x")
    p.trees.append(tree)
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "x.ptproj")
        serialization.save_project(p, path)
        p2 = serialization.load_project(path)
    se = next(e for e in p2.trees[0].elements.values()
              if e.kind == ElementKind.SERIES)
    assert se.series_type == SeriesType.FERRITE_BEAD
    assert se.inductance_uh == 2.2
    assert se.rating == "600R@100MHz"


def test_net_registry_and_conflicts():
    p = Project("x")
    t1 = p.new_tree("A")
    s1 = t1.add_element(Source(signal_name="VCC_5V0", v_typ=5.0,
                               v_min=4.9, v_max=5.1))
    t1.add_element(Converter(signal_name="VCC_3V3", vout_typ=3.3),
                   parent_id=s1.id)
    t2 = p.new_tree("B")
    t2.add_element(Source(signal_name="VCC_3V3", v_typ=5.0,   # wrong voltage!
                          v_min=4.9, v_max=5.1))
    nets, conflicts = collect_nets(p)
    assert "VCC_5V0" in nets and "VCC_3V3" in nets
    assert any("VCC_3V3" in c for c in conflicts), \
        "same net at 3.3 V and 5 V must conflict"


def test_input_net_walks_ancestors():
    tree = PowerTree("t")
    src = tree.add_element(Source(signal_name="VIN"))
    se = tree.add_element(SeriesElement(signal_name=""), parent_id=src.id)
    from powertree.model.elements import Load
    ld = tree.add_element(Load(), parent_id=se.id)
    assert input_net(tree, ld) == "VIN"    # unnamed series is transparent
    se.signal_name = "VIN_F"
    assert input_net(tree, ld) == "VIN_F"


def test_zynq_demo_has_expected_findings():
    p = build_sample_project()
    tree = p.trees[0]
    assert tree.source is not None
    assert len(tree.elements) > 30, "demo should be a complex topology"
    r = solve_tree(tree)
    msgs = [w.message for w in r.warnings]
    # deliberate violation: clock gen VDDA undervoltage behind FB3
    assert any("undervoltage" in m and "VDDA" in m for m in msgs), msgs
    # deliberate low margin: 1.0 V core buck near its current limit
    assert any("margin below 10" in m and "1.0V Core Buck" in m
               for m in msgs), msgs
    # and no *unintended* extra errors beyond the clock-gen one
    errors = [w for w in r.warnings if w.severity == "error"]
    assert all("VDDA" in w.message or "Core 1.2V" not in w.message
               for w in errors)


def test_zynq_demo_roundtrip_and_nets():
    p = build_sample_project()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "z.ptproj")
        serialization.save_project(p, path)
        p2 = serialization.load_project(path)
    assert serialization.project_to_dict(p2) == serialization.project_to_dict(p)
    nets, conflicts = collect_nets(p2)
    assert "VCC_5V0" in nets and "VCC_1V0" in nets
    assert conflicts == [], f"demo must have no net conflicts: {conflicts}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
