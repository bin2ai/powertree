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


def test_rail_headroom_math():
    from powertree.model.elements import LimitType
    t = PowerTree("t")
    src = t.add_element(Source(v_min=10, v_typ=10, v_max=10,
                               limit_type=LimitType.POWER, limit_value=10.0))
    c = t.add_element(Converter(efficiency_pct=100, vout_min=5, vout_typ=5,
                                vout_max=5, limit_type=LimitType.CURRENT,
                                limit_value=2.0), parent_id=src.id)
    t.add_element(Load(load_type=LoadType.CURRENT, value_typ=1.0),
                  parent_id=c.id)
    rows = api.rail_headroom(t)
    assert len(rows) == 2
    conv = next(r for r in rows if r["kind"] == "converter")
    assert math.isclose(conv["used_worst"], 1.0, rel_tol=1e-6)
    assert math.isclose(conv["headroom"], 1.0, rel_tol=1e-6)      # 1 A left
    assert math.isclose(conv["extra_load_w"], 5.0, rel_tol=1e-6)  # at 5 V
    src_row = next(r for r in rows if r["kind"] == "source")
    assert math.isclose(src_row["used_worst"], 5.0, rel_tol=1e-6)
    assert src_row["used_pct"] == 50.0
    # sorted tightest-first
    assert rows[0]["headroom_pct"] <= rows[-1]["headroom_pct"]


def test_rail_headroom_demo_flags_core_buck_tight():
    p = api.demo_project()
    rows = api.rail_headroom(p.trees[0])
    tightest = rows[0]
    assert "1.0V Core Buck" in tightest["name"]
    assert tightest["headroom_pct"] < 10


def test_excel_states_sheet():
    from openpyxl import load_workbook
    from powertree.export.excel_export import export_excel_xlsx
    p = api.demo_project()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "r.xlsx")
        export_excel_xlsx(p, path)
        wb = load_workbook(path)
    assert "States" in wb.sheetnames
    ws = wb["States"]
    labels = [ws.cell(row=r, column=2).value for r in range(2, 10)]
    assert "Base" in labels and "Low Power" in labels \
        and "Performance" in labels
    assert "Efficiency (%)" in [c.value for c in wb["Overview"][5]]


def test_duplicate_subtree():
    p = api.demo_project()
    tree = p.trees[0]
    conv = api.find_element(tree, "U12")           # 1.8V buck w/ children
    n_before = len(tree.elements)
    subtree_size = 1 + len(tree.descendants_of(conv.id))
    dup = tree.duplicate_subtree(conv.id)
    assert len(tree.elements) == n_before + subtree_size
    assert dup.name.endswith("(copy)")
    assert dup.parent_id == conv.parent_id
    dup_desc = tree.descendants_of(dup.id)
    assert len(dup_desc) == subtree_size - 1
    assert {d.id for d in dup_desc}.isdisjoint(
        {d.id for d in tree.descendants_of(conv.id)})
    solve_tree(tree)                               # still solves cleanly
    with pytest.raises(ValueError, match="one source"):
        tree.duplicate_subtree(tree.source.id)


def test_derating_policy_in_validate():
    p = api.demo_project()
    assert p.derating_pct == 80.0
    v = api.validate(p)
    msgs = [f["message"] for f in v["findings"]]
    assert any("derating policy" in m and "1.0V Core Buck" in m
               for m in msgs), "92%-used core buck must trip 80% derating"
    p.derating_pct = 0                             # disable
    v2 = api.validate(p)
    assert not any("derating policy" in f["message"] for f in v2["findings"])


def test_derating_roundtrip():
    from powertree.model import serialization
    p = api.demo_project()
    p.derating_pct = 70.0
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "d.ptproj")
        serialization.save_project(p, path)
        assert serialization.load_project(path).derating_pct == 70.0


def test_html_report_export():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
    p = api.demo_project()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "share.html")
        api.export(p, "html", path)
        with open(path, encoding="utf-8") as fh:
            doc = fh.read()
    assert "data:image/png;base64," in doc          # embedded flowchart
    assert "ATTENTION" in doc                       # verdict from findings
    assert "Rail budget" in doc and "Operating states" in doc
    assert "VDDA" in doc                            # findings listed
    assert len(doc) > 100_000                       # genuinely self-contained


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
