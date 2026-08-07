"""Tests for the headless API, CLI and MCP tool layer."""

import json
import os
import subprocess
import sys
import tempfile

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from powertree import api  # noqa: E402
from powertree.model.elements import ElementKind  # noqa: E402


@pytest.fixture(scope="module")
def demo_path():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "demo.ptproj")
        api.save(api.demo_project(), path)
        yield path


def run_cli(*args):
    env = dict(os.environ, PYTHONPATH=SRC, QT_QPA_PLATFORM="offscreen",
               QT_QPA_FONTDIR=r"C:\Windows\Fonts")
    return subprocess.run(
        [sys.executable, "-m", "powertree", *args],
        capture_output=True, text=True, env=env, cwd=ROOT, timeout=180)


# ------------------------------------------------------------------- api ---
def test_api_summary_and_solve():
    p = api.demo_project()
    s = api.project_summary(p)
    assert s["trees"][0]["elements"] > 30
    assert s["findings"]["error"] == 3          # the deliberate VDDA violation
    result = api.solve(p, "Zynq Carrier 12V")
    assert result["converged"]
    names = [r["name"] for r in result["elements"]]
    assert "12V DC Input" in names and any("VCCINT" in n for n in names)
    json.dumps(result)                           # fully JSON-serializable


def test_api_validate_flags_demo():
    v = api.validate(api.demo_project())
    assert v["ok"] is False and v["errors"] == 3
    json.dumps(v)


def test_api_find_element_by_refdes_and_signal():
    p = api.demo_project()
    t = api.find_tree(p, None)
    assert api.find_element(t, "J1").kind == ElementKind.SOURCE
    assert api.find_element(t, "VCC_5V0").name == "5V Buck"
    with pytest.raises(ValueError, match="No element"):
        api.find_element(t, "nonexistent")


def test_api_set_field_resolves_violation():
    p = api.demo_project()
    r = api.set_element_field(p, None, "FB3", "resistance_ohm", 0.05)
    assert r["tree_errors"] == 0, "fixing the bead should clear the violation"


def test_api_apply_template():
    p = api.demo_project()
    r = api.apply_template(p, None, "qspi_flash", {"3.3V": "U11"},
                           block_name="Second flash", refdes="U8")
    assert r["created"] == ["VCC"]
    hits = api.search(p, "Second flash")
    assert not hits    # block name is not element name
    assert any(e.refdes == "U8"
               for e in api.find_tree(p, None).elements.values())


def test_api_search():
    hits = api.search(api.demo_project(), "zynq")
    assert hits == [] or all("tree" in h for h in hits)
    hits = api.search(api.demo_project(), "VCCINT")
    assert len(hits) >= 2      # bead + load


# ------------------------------------------------------------------- cli ---
def test_cli_info(demo_path):
    r = run_cli("info", demo_path)
    assert r.returncode == 0, r.stderr
    assert "Zynq Carrier 12V" in r.stdout


def test_cli_validate_exit_code(demo_path):
    r = run_cli("validate", demo_path)
    assert r.returncode == 1        # demo deliberately contains violations
    assert "FAIL" in r.stdout and "VDDA" in r.stdout


def test_cli_solve_json(demo_path):
    r = run_cli("solve", demo_path, "--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["tree"] == "Zynq Carrier 12V"
    assert len(data["elements"]) > 30


def test_cli_nets(demo_path):
    r = run_cli("nets", demo_path)
    assert "VCC_5V0" in r.stdout
    assert r.returncode == 0        # no conflicts in demo


def test_cli_templates():
    r = run_cli("templates", "--json")
    data = json.loads(r.stdout)
    assert any(t["key"] == "zynq7020" for t in data)


def test_cli_export_png_and_pdf(demo_path):
    with tempfile.TemporaryDirectory() as td:
        png = os.path.join(td, "t.png")
        r = run_cli("export", "png", demo_path, "-o", png)
        assert r.returncode == 0, r.stderr
        assert os.path.getsize(png) > 50_000
        pdf = os.path.join(td, "t.pdf")
        r = run_cli("export", "pdf", demo_path, "-o", pdf)
        assert r.returncode == 0, r.stderr
        assert os.path.getsize(pdf) > 100_000


def test_cli_error_paths():
    r = run_cli("info", "does_not_exist.ptproj")
    assert r.returncode == 2 and "error:" in r.stderr


# ------------------------------------------------------------------- mcp ---
def test_mcp_tools_roundtrip(tmp_path):
    from powertree import mcp_server as srv
    srv._state["project"] = None
    with pytest.raises(ValueError, match="No project loaded"):
        srv._project()
    def call(tool, *a, **k):        # SDK returns plain fn or a wrapper
        return getattr(tool, "fn", tool)(*a, **k)

    summary = call(srv.open_demo_project)
    assert summary["trees"]
    v = call(srv.validate)
    assert v["errors"] == 3
    r = call(srv.set_element_field, "FB3", "resistance_ohm", "0.05")
    assert r["tree_errors"] == 0
    out = tmp_path / "saved.ptproj"
    assert call(srv.save_project, str(out)) == str(out)
    assert out.exists()


def test_mcp_server_lists_all_tools():
    from powertree import mcp_server as srv
    import anyio
    tools = anyio.run(srv.mcp.list_tools)
    names = {t.name for t in tools}
    assert {"open_project", "solve_tree", "validate", "set_element_field",
            "apply_template", "export_report", "nets",
            "search"} <= names


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
