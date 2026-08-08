"""Tests for v0.9.0: SI unit parsing, cost/area rollups, tree comparison,
PMIC template pattern."""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from powertree import api  # noqa: E402
from powertree.units import parse_si, si_text  # noqa: E402
from powertree.model.elements import (  # noqa: E402
    PowerTree, Source, ElementKind,
)
from powertree.model import serialization  # noqa: E402
from powertree.model.calc import solve_tree  # noqa: E402
from powertree.templates import template_by_key, instantiate_template  # noqa: E402


# ------------------------------------------------------------------- units
@pytest.mark.parametrize("text,expected", [
    ("100m", 0.1), ("100 m", 0.1), ("100mA", 0.1), ("100 mA", 0.1),
    ("4.7u", 4.7e-6), ("4.7µ", 4.7e-6), ("2.2k", 2200.0), ("2.2K", 2200.0),
    ("1M", 1e6), ("3.3", 3.3), ("3.3V", 3.3), ("50 mΩ", 0.05),
    ("0.05", 0.05), ("1e-3", 1e-3), ("-12", -12.0), ("0", 0.0),
    ("330n", 3.3e-7), ("10p", 1e-11), ("5G", 5e9), ("1,5", 1.5),
])
def test_parse_si(text, expected):
    value = parse_si(text)
    assert value is not None, text
    assert math.isclose(value, expected, rel_tol=1e-9), (text, value)


@pytest.mark.parametrize("text", ["", "abc", "m", "1.2.3", None, "--5"])
def test_parse_si_rejects(text):
    assert parse_si(text) is None


def test_si_text_roundtrip():
    for value in (0.1, 4.7e-6, 2200.0, 3.3, 0.05, 1e6, 0.0, 1.5e-9):
        text = si_text(value)
        back = parse_si(text)
        assert back is not None
        if value == 0:
            assert back == 0
        else:
            assert math.isclose(back, value, rel_tol=1e-6), (value, text)


# -------------------------------------------------------------- cost/area
def test_cost_area_rollups_and_roundtrip(tmp_path):
    p = api.demo_project()
    tree = p.trees[0]
    conv = api.find_element(tree, "U11")
    conv.cost = 2.50
    conv.area_mm2 = 120.0
    load = api.find_element(tree, "J1")
    load.cost = 1.25
    m = api.tree_metrics(tree)
    assert math.isclose(m["cost_total"], 3.75)
    assert m["cost_items"] == 2
    assert math.isclose(m["area_total_mm2"], 120.0)
    assert m["area_items"] == 1
    # trees without entries report None, not 0 (absence != zero)
    m2 = api.tree_metrics(p.trees[1])
    assert m2["cost_total"] is None and m2["area_total_mm2"] is None
    path = os.path.join(tmp_path, "ca.ptproj")
    serialization.save_project(p, path)
    p2 = serialization.load_project(path)
    c2 = api.find_element(p2.trees[0], "U11")
    assert c2.cost == 2.50 and c2.area_mm2 == 120.0


# ----------------------------------------------------------------- compare
def test_compare_trees_shape():
    p = api.demo_project()
    rows = api.compare_trees(p)
    assert len(rows) == 2
    zynq = rows[0]
    assert zynq["tree"] == "Zynq Carrier 12V"
    assert zynq["errors"] == 3                 # deliberate VDDA violation
    assert zynq["growth_pct"] == 0.0           # violating at nominal
    battery = rows[1]
    assert battery["errors"] == 0
    assert battery["growth_pct"] and battery["growth_pct"] > 100
    import json
    json.dumps(rows)


# -------------------------------------------------------------------- pmic
def test_pmic_template_pattern():
    tree = PowerTree("t")
    src = tree.add_element(Source(v_min=4.5, v_typ=5, v_max=5.5,
                                  signal_name="VIN"))
    created = instantiate_template(
        tree, template_by_key("pmic_quad"), {"VIN": src.id},
        block_name="PMIC (U1)", refdes="U1")
    assert len(created) == 5
    convs = [e for e in created if e.kind == ElementKind.CONVERTER]
    assert len(convs) == 4
    assert all(e.refdes == "U1" for e in created)      # one physical part
    assert len({e.block_id for e in created}) == 1     # one block
    # solves cleanly; four independent rails from one "device"
    r = solve_tree(tree)
    assert not [w for w in r.warnings if w.severity == "error"]
    vouts = sorted(round(r.get(c.id, "typ").v_out, 2) for c in convs)
    assert vouts == [1.0, 1.2, 1.8, 3.3]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
