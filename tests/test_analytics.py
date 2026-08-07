"""Tests for tree analytics (efficiency/loss/top consumers) and CSV export."""

import csv
import math
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from powertree import api  # noqa: E402
from powertree.model.elements import (  # noqa: E402
    PowerTree, Project, Source, Converter, Load, LoadType,
)
from powertree.model.calc import solve_tree  # noqa: E402


def test_tree_metrics_simple_converter_chain():
    t = PowerTree("t")
    src = t.add_element(Source(v_min=10, v_typ=10, v_max=10))
    c = t.add_element(Converter(efficiency_pct=80, vout_min=5, vout_typ=5,
                                vout_max=5), parent_id=src.id)
    t.add_element(Load(load_type=LoadType.CURRENT, value_typ=1.0),
                  parent_id=c.id)
    m = api.tree_metrics(t)
    # loads get 5 W, source delivers 6.25 W, loss 1.25 W, eff 80 %
    assert math.isclose(m["p_loads_typ"], 5.0, rel_tol=1e-6)
    assert math.isclose(m["p_source_typ"], 6.25, rel_tol=1e-6)
    assert math.isclose(m["p_loss_typ"], 1.25, rel_tol=1e-6)
    assert math.isclose(m["efficiency_pct"], 80.0, abs_tol=0.1)
    assert m["top_consumers"][0]["pct_of_source"] == 80.0


def test_tree_metrics_demo_consistency():
    p = api.demo_project()
    tree = p.trees[0]
    r = solve_tree(tree)
    m = api.tree_metrics(tree, r)
    # energy conservation: loads + losses ≈ source output
    assert math.isclose(m["p_loads_typ"] + m["p_loss_typ"],
                        m["p_source_typ"], rel_tol=1e-6)
    assert 0 < m["efficiency_pct"] < 100
    assert len(m["top_consumers"]) == 5
    pcts = [c["pct_of_source"] for c in m["top_consumers"]]
    assert pcts == sorted(pcts, reverse=True)


def test_project_summary_includes_metrics():
    s = api.project_summary(api.demo_project())
    t0 = s["trees"][0]
    assert t0["efficiency_pct"] is not None
    assert t0["top_consumers"]


def test_export_csv_roundtrips():
    p = api.demo_project()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "table.csv")
        api.export_csv(p, path)
        with open(path, newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
    trees = {r["tree"] for r in rows}
    assert "Zynq Carrier 12V" in trees and "Battery Backup" in trees
    total_elements = sum(len(t.elements) for t in p.trees)
    assert len(rows) == total_elements
    vdda = next(r for r in rows if r["name"] == "VDDA 1.8V")
    assert vdda["status"] == "VIOLATION"
    src = next(r for r in rows if r["name"] == "12V DC Input")
    assert abs(float(src["pct_of_source_typ"]) - 100.0) < 0.1


def test_export_csv_via_generic_export():
    p = api.demo_project()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "one.csv")
        api.export(p, "csv", path, "Battery Backup")
        with open(path, newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
    assert {r["tree"] for r in rows} == {"Battery Backup"}
    assert len(rows) == 3


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
