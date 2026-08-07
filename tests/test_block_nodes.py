"""Tests for collapsed-block summary nodes (layout render graph + stats)."""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from powertree import api  # noqa: E402
from powertree.model.elements import (  # noqa: E402
    PowerTree, Source, Converter, Load, LoadType,
)
from powertree.model.calc import solve_tree  # noqa: E402
from powertree.ui.layout import compute_layout, BLOCK_PREFIX  # noqa: E402


def _no_overlaps(lay, tol=1.0):
    rids = list(lay.render_nodes)
    for i, a in enumerate(rids):
        ax, ay = lay.positions[a]
        aw, ah = lay.sizes[a]
        for b in rids[i + 1:]:
            bx, by = lay.positions[b]
            bw, bh = lay.sizes[b]
            if abs(ax - bx) * 2 < (aw + bw) - tol and \
                    abs(ay - by) * 2 < (ah + bh) - tol:
                return False, (a, b)
    return True, None


def test_regulator_block_collapses_to_single_node():
    p = api.demo_project()
    tree = p.trees[0]
    block = next(b for b in tree.blocks.values()
                 if "5V Intermediate" in b.name)
    block.collapsed = True
    lay = compute_layout(tree, "TD")
    rid = BLOCK_PREFIX + block.id
    assert rid in lay.render_nodes
    info = lay.block_nodes[rid]
    assert len(info.member_ids) == 2               # converter + Iq load
    # members hidden from the canvas
    for mid in info.member_ids:
        assert mid not in lay.visible
        assert mid not in lay.positions
    # one input rail (filtered 12V), one output rail (VCC_5V0)
    assert len(info.inputs) == 1
    assert info.inputs[0][0] == "VIN_FLT"
    assert [n for n, _ in info.outputs] == ["VCC_5V0"]
    # external children (the POL bucks) re-attach under the block node
    kids = {cid for pid, cid, _pts, _lbl in lay.edges if pid == rid}
    assert len(kids) >= 4                          # 4 POL regulator blocks
    ok, pair = _no_overlaps(lay)
    assert ok, f"overlap: {pair}"


def test_zynq_block_multi_rail_pins_and_cross_edges():
    p = api.demo_project()
    tree = p.trees[0]
    block = next(b for b in tree.blocks.values() if "Zynq" in b.name)
    block.collapsed = True
    lay = compute_layout(tree, "TD")
    rid = BLOCK_PREFIX + block.id
    info = lay.block_nodes[rid]
    assert len(info.member_ids) == 9
    # four distinct input rails feed the Zynq -> four labeled input pins
    in_nets = [n for n, _ in info.inputs]
    assert len(in_nets) == 4
    assert "VCC_1V8" in in_nets and "VCC_3V3" in in_nets
    assert info.outputs == []                      # nothing leaves the SoC
    # ALL four feeds arrive as edges into the block node (1 tree + 3 cross)
    feeds = [(pid, cid) for pid, cid, _p, _l in lay.edges if cid == rid]
    assert len(feeds) == 4, feeds
    ok, pair = _no_overlaps(lay)
    assert ok, f"overlap: {pair}"


def test_block_summary_stats_energy_consistent():
    from powertree.ui.canvas import block_summary_stats  # needs QApplication?
    p = api.demo_project()
    tree = p.trees[0]
    r = solve_tree(tree)
    block = next(b for b in tree.blocks.values()
                 if "5V Intermediate" in b.name)
    block.collapsed = True
    lay = compute_layout(tree, "TD")
    info = lay.block_nodes[BLOCK_PREFIX + block.id]
    stats = block_summary_stats(tree, r, info)
    # regulator block: p_in = converter p_in + Iq load; dissipation =
    # converter loss + Iq load; pass-through = converter p_out
    conv = next(tree.elements[m] for m in info.member_ids
                if tree.elements[m].kind == "converter")
    iq = next(tree.elements[m] for m in info.member_ids
              if tree.elements[m].kind == "load")
    conv_res = r.get(conv.id, "typ")
    iq_res = r.get(iq.id, "typ")
    assert math.isclose(stats["p_in"], conv_res.p_in + iq_res.p_in,
                        rel_tol=1e-9)
    assert math.isclose(stats["dissipation"],
                        conv_res.p_loss + iq_res.p_in, rel_tol=1e-9)
    assert math.isclose(stats["p_through"], conv_res.p_out, rel_tol=1e-6)


def test_chained_collapsed_blocks():
    """Regulator block (collapsed) feeding the Zynq block (collapsed):
    a blk->blk edge from an output pin to an input pin."""
    p = api.demo_project()
    tree = p.trees[0]
    b33 = next(b for b in tree.blocks.values() if "3.3V Buck" in b.name)
    zynq = next(b for b in tree.blocks.values() if "Zynq" in b.name)
    b33.collapsed = True
    zynq.collapsed = True
    lay = compute_layout(tree, "TD")
    r33 = BLOCK_PREFIX + b33.id
    rz = BLOCK_PREFIX + zynq.id
    links = [(p_, c) for p_, c, _pts, _l in lay.edges
             if p_ == r33 and c == rz]
    assert links, "collapsed 3.3V block must feed collapsed Zynq block"
    # Zynq input pin list names the 3.3V rail with the reg block as feeder
    info = lay.block_nodes[rz]
    assert any(feeder == r33 for _n, feeder in info.inputs)
    ok, pair = _no_overlaps(lay)
    assert ok, f"overlap: {pair}"


def test_all_blocks_collapsed_still_routes_and_solves():
    p = api.demo_project()
    tree = p.trees[0]
    for b in tree.blocks.values():
        b.collapsed = True
    lay = compute_layout(tree, "TD")
    blk_nodes = [rid for rid in lay.render_nodes
                 if rid.startswith(BLOCK_PREFIX)]
    assert len(blk_nodes) == len(
        [b for b in tree.blocks.values()
         if any(m.id != tree.source.id for m in tree.block_members(b.id))])
    ok, pair = _no_overlaps(lay)
    assert ok, f"overlap: {pair}"
    # LR orientation works too
    lay_lr = compute_layout(tree, "LR")
    ok, pair = _no_overlaps(lay_lr)
    assert ok, f"LR overlap: {pair}"
    # collapse state round-trips through the file format
    from powertree.model import serialization
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "c.ptproj")
        serialization.save_project(p, path)
        p2 = serialization.load_project(path)
    assert all(b.collapsed for b in p2.trees[0].blocks.values())


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
