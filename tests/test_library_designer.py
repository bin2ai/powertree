"""Tests for the component library and the block designer model/layout."""

import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from powertree import api, library  # noqa: E402
from powertree.model.elements import (  # noqa: E402
    PowerTree, Project, Source, Converter, Load, LoadType,
)
from powertree.model.calc import solve_tree  # noqa: E402
from powertree.model import serialization  # noqa: E402
from powertree.templates import all_templates, template_by_key  # noqa: E402
from powertree.ui.layout import (  # noqa: E402
    compute_layout, block_pins, BLOCK_PREFIX)


@pytest.fixture()
def temp_library(tmp_path, monkeypatch):
    path = tmp_path / "library.json"
    monkeypatch.setenv(library.LIBRARY_ENV, str(path))
    return path


# ------------------------------------------------------------------ library
def test_block_to_part_regulator(temp_library):
    p = api.demo_project()
    tree = p.trees[0]
    block = next(b for b in tree.blocks.values()
                 if "5V Intermediate" in b.name)
    part = library.block_to_part(tree, block.id)
    assert part["rails"] == ["VIN_FLT"]
    assert len(part["items"]) == 2
    conv = next(i for i in part["items"] if i["kind"] == "converter")
    assert conv["rail"] == "VIN_FLT"
    assert conv["params"]["efficiency_pct"] == 93.0
    assert conv["params"]["eff_points"]          # curve captured
    assert conv["params"]["signal_name"] == "VCC_5V0"


def test_block_to_part_internal_topology(temp_library):
    """A block containing a converter WITH a member child keeps the '@'
    parent reference so the internal topology re-instantiates."""
    tree = PowerTree("t")
    src = tree.add_element(Source(v_min=5, v_typ=5, v_max=5))
    block = tree.add_block("Sub")
    conv = tree.add_element(Converter(name="LDO", signal_name="V1",
                                      vout_min=1.8, vout_typ=1.8,
                                      vout_max=1.8), parent_id=src.id)
    load = tree.add_element(Load(name="Core", value_typ=0.1),
                            parent_id=conv.id)
    conv.block_id = block.id
    load.block_id = block.id
    part = library.block_to_part(tree, block.id)
    item_load = next(i for i in part["items"] if i["name"] == "Core")
    assert item_load["rail"] == "@LDO"
    # instantiate into a fresh tree
    t2 = PowerTree("t2")
    s2 = t2.add_element(Source(v_min=5, v_typ=5, v_max=5,
                               signal_name="VIN"))
    created = library.instantiate_part(t2, part, {part["rails"][0]: s2.id})
    assert len(created) == 2
    new_load = next(e for e in created if e.kind == "load")
    new_conv = next(e for e in created if e.kind == "converter")
    assert new_load.parent_id == new_conv.id
    solve_tree(t2)


def test_library_add_remove_export_import(temp_library, tmp_path):
    p = api.demo_project()
    tree = p.trees[0]
    block = next(b for b in tree.blocks.values() if "Zynq" in b.name)
    part = library.block_to_part(tree, block.id, key="my_zynq",
                                 name="My Zynq Budget")
    library.add_part(part)
    assert any(x["key"] == "my_zynq" for x in library.load_library())
    # merged into the template system
    keys = [t.key for t in all_templates()]
    assert "my_zynq" in keys
    tpl = template_by_key("my_zynq")
    assert len(tpl.items) == 9 and len(tpl.rails) == 4
    # export / import roundtrip
    out = tmp_path / "part.json"
    library.export_part(part, str(out))
    library.remove_part("my_zynq")
    assert not any(x["key"] == "my_zynq" for x in library.load_library())
    parts = library.import_part(str(out))
    assert parts[0]["key"] == "my_zynq"
    assert any(x["key"] == "my_zynq" for x in library.load_library())


def test_instantiate_part_applies_block_style(temp_library):
    p = api.demo_project()
    tree = p.trees[0]
    block = next(b for b in tree.blocks.values() if "Zynq" in b.name)
    block.info_text = "XC7Z020 rev C"
    block.pin_side = {"VCC_1V8": "left"}
    block.width = 420
    part = library.block_to_part(tree, block.id, key="styled_zynq")
    assert part["block_style"]["info_text"] == "XC7Z020 rev C"
    t2 = PowerTree("t2")
    s2 = t2.add_element(Source(v_min=5, v_typ=5, v_max=5))
    rails = {}
    for r in part["rails"]:
        c = t2.add_element(Converter(name=r, signal_name=r), parent_id=s2.id)
        rails[r] = c.id
    created = library.instantiate_part(t2, part, rails)
    new_block = t2.blocks[created[0].block_id]
    assert new_block.info_text == "XC7Z020 rev C"
    assert new_block.pin_side == {"VCC_1V8": "left"}
    assert new_block.width == 420


def test_invalid_part_rejected(temp_library):
    with pytest.raises(ValueError, match="missing"):
        library.add_part({"key": "x", "name": ""})
    with pytest.raises(ValueError, match="kind"):
        library.add_part({"key": "x", "name": "X",
                          "items": [{"kind": "source", "name": "s",
                                     "rail": "VIN"}]})


# ------------------------------------------------------------ block designer
def test_block_pins_helper():
    p = api.demo_project()
    tree = p.trees[0]
    zynq = next(b for b in tree.blocks.values() if "Zynq" in b.name)
    ins, outs = block_pins(tree, zynq.id)
    assert len(ins) == 4 and outs == []
    reg = next(b for b in tree.blocks.values() if "5V Intermediate" in b.name)
    ins, outs = block_pins(tree, reg.id)
    assert ins == ["VIN_FLT"] and outs == ["VCC_5V0"]


def test_designer_pin_side_order_and_size():
    p = api.demo_project()
    tree = p.trees[0]
    zynq = next(b for b in tree.blocks.values() if "Zynq" in b.name)
    zynq.collapsed = True
    zynq.pin_side = {"VCC_1V8": "left", "VCC_3V3": "right"}
    zynq.pin_order = {"in": ["VCC_1V5", "VCCINT_FLT"]}
    zynq.width = 500
    zynq.height = 200
    lay = compute_layout(tree, "TD")
    rid = BLOCK_PREFIX + zynq.id
    assert lay.sizes[rid] == (500.0, 200.0)
    info = lay.block_nodes[rid]
    # order: listed nets first
    nets = [n for n, _ in info.inputs]
    assert nets[0] == "VCC_1V5" and nets[1] == "VCCINT_FLT"
    sides = {net: info.pin_geom[("in", feeder)][0]
             for net, feeder in info.inputs}
    assert sides["VCC_1V8"] == "left"
    assert sides["VCC_3V3"] == "right"
    assert sides["VCC_1V5"] == "top"          # default
    # pin_point lands on the correct card edge
    feeder_1v8 = next(f for n, f in info.inputs if n == "VCC_1V8")
    x, y = lay.pin_point(rid, "in", feeder_1v8)
    cx, cy = lay.positions[rid]
    assert math.isclose(x, cx - 250.0, abs_tol=0.5)   # left edge
    # edges still route (endpoint = pin point)
    feeds = [e for e in lay.edges if e[1] == rid]
    assert len(feeds) == 4


def test_designer_fields_roundtrip(tmp_path):
    p = api.demo_project()
    tree = p.trees[0]
    zynq = next(b for b in tree.blocks.values() if "Zynq" in b.name)
    zynq.pin_side = {"VCC_1V8": "left"}
    zynq.pin_order = {"in": ["VCC_1V8"], "out": []}
    zynq.info_text = "line1\nline2"
    zynq.show_stats = False
    zynq.width = 333
    path = os.path.join(tmp_path, "d.ptproj")
    serialization.save_project(p, path)
    p2 = serialization.load_project(path)
    z2 = next(b for b in p2.trees[0].blocks.values() if "Zynq" in b.name)
    assert z2.pin_side == {"VCC_1V8": "left"}
    assert z2.pin_order == {"in": ["VCC_1V8"], "out": []}
    assert z2.info_text == "line1\nline2"
    assert z2.show_stats is False and z2.width == 333


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
