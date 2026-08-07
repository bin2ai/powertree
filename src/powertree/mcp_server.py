"""PowerTree MCP server — lets AI assistants (Claude Code, Claude Desktop, or
any MCP client) open, inspect, edit, validate and export power tree projects.

Run (stdio transport):
    .venv\\Scripts\\python.exe -m powertree.mcp_server

Claude Code registration (.mcp.json at your workspace root):
    {
      "mcpServers": {
        "powertree": {
          "command": "C:/code/tool_power_tree/.venv/Scripts/python.exe",
          "args": ["-m", "powertree.mcp_server"],
          "env": {"PYTHONPATH": "C:/code/tool_power_tree/src"}
        }
      }
    }

All tools operate on one project held in memory; call open_project first
(or new_project / open_demo_project), then save_project to persist edits.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import api
from .model.elements import Project

mcp = MCPServer(
    "powertree",
    instructions=(
        "Electronic power tree analysis. Load a .ptproj with open_project "
        "(or open_demo_project), inspect with project_summary / solve_tree / "
        "get_element / nets, edit with set_element_field / apply_template, "
        "gate with validate, persist with save_project, and produce "
        "deliverables with export_report."))

_state: dict = {"project": None}


def _project() -> Project:
    if _state["project"] is None:
        raise ValueError("No project loaded — call open_project(path), "
                         "open_demo_project() or new_project(name) first.")
    return _state["project"]


@mcp.tool()
def open_project(path: str) -> dict:
    """Open a .ptproj project file and make it the active project."""
    _state["project"] = api.load(path)
    return api.project_summary(_state["project"])


@mcp.tool()
def open_demo_project() -> dict:
    """Load the built-in Zynq carrier demo as the active project."""
    _state["project"] = api.demo_project()
    return api.project_summary(_state["project"])


@mcp.tool()
def new_project(name: str) -> dict:
    """Create a new empty project (one empty tree) as the active project."""
    project = Project(name)
    project.new_tree("Power Tree 1")
    _state["project"] = project
    return api.project_summary(project)


@mcp.tool()
def save_project(path: str = "") -> str:
    """Save the active project (to `path`, or its original file)."""
    return api.save(_project(), path or None)


@mcp.tool()
def project_summary() -> dict:
    """Trees, element counts, source power and finding counts."""
    return api.project_summary(_project())


@mcp.tool()
def solve_tree(tree: str = "", state: str = "") -> dict:
    """Solve one tree bottom-up: per-element min/typ/max operating points
    plus margin warnings. `tree` = name or id (default: first tree);
    `state` = named operating state to apply (default: Base)."""
    return api.solve(_project(), tree or None, state or None)


@mcp.tool()
def set_state_override(element: str, state: str, field: str, value: str,
                       tree: str = "") -> dict:
    """Set (or clear with empty value) a per-state override on an element,
    e.g. a load's value_typ in 'Low Power'. Creates the state if new."""
    project = _project()
    t = api.find_tree(project, tree or None)
    el = api.find_element(t, element)
    if state not in project.scenarios:
        project.scenarios.append(state)
    bucket = el.scenario_overrides.setdefault(state, {})
    if value == "":
        bucket.pop(field, None)
    else:
        bucket[field] = float(value)
    return {"element": el.name, "state": state, "overrides": bucket,
            "project_states": project.scenarios}


@mcp.tool()
def validate() -> dict:
    """Margin/net gate across the whole project. ok=false means violations
    (limit exceeded, voltage window broken, collapsed rail, net conflict)."""
    return api.validate(_project())


@mcp.tool()
def nets() -> dict:
    """Global net registry: every named rail, definers, consumers,
    conflicts."""
    return api.nets_report(_project())


@mcp.tool()
def rail_headroom(tree: str = "") -> list:
    """Remaining budget per limited rail (worst-case corner): how much extra
    load each source/converter can still accept before breaking its limit."""
    project = _project()
    t = api.find_tree(project, tree or None)
    return api.rail_headroom(t)


@mcp.tool()
def search(query: str) -> list:
    """Find elements by name / refdes / signal / part number across trees."""
    return api.search(_project(), query)


@mcp.tool()
def get_element(element: str, tree: str = "") -> dict:
    """Full detail + operating points for one element (match by id, name,
    refdes or signal name)."""
    project = _project()
    t = api.find_tree(project, tree or None)
    el = api.find_element(t, element)
    from .model.calc import solve_tree as _solve
    return api.element_dict(t, el, _solve(t))


@mcp.tool()
def set_element_field(element: str, field: str, value: str,
                      tree: str = "") -> dict:
    """Set one field on an element (e.g. value_typ, efficiency_pct,
    resistance_ohm, v_in_min) and report the tree's new finding counts."""
    return api.set_element_field(_project(), tree or None, element, field,
                                 value)


@mcp.tool()
def list_templates() -> list:
    """Device templates (Zynq SoC, DDR3, PHYs, regulator blocks…)."""
    return api.list_templates()


@mcp.tool()
def apply_template(template_key: str, rail_map: dict, tree: str = "",
                   block_name: str = "", refdes: str = "") -> dict:
    """Instantiate a device template. rail_map maps the template's external
    rails to existing elements (by name/refdes/signal), e.g.
    {"3.3V": "U11", "1.8V": "VCC_1V8"}."""
    return api.apply_template(_project(), tree or None, template_key,
                              rail_map, block_name, refdes)


@mcp.tool()
def waive_finding(element: str, message: str, reason: str,
                  tree: str = "") -> dict:
    """Acknowledge a finding with an engineering justification (it stays
    visible in reports as an audit trail but stops counting). `message`
    must match the finding text exactly (see solve_tree/validate)."""
    project = _project()
    t = api.find_tree(project, tree or None)
    el = api.find_element(t, element)
    return api.waive_finding(project, el.id, message, reason)


@mcp.tool()
def export_report(kind: str, out_path: str, tree: str = "") -> str:
    """Export a deliverable: kind = pdf | png | xlsx | xlsm | notes-md |
    notes-html | notes-pdf."""
    return api.export(_project(), kind, out_path, tree or None)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
