"""PowerTree command-line interface.

Examples:
    powertree info examples\\DemoBoard.ptproj
    powertree solve examples\\DemoBoard.ptproj --tree "Zynq Carrier 12V" --json
    powertree validate examples\\DemoBoard.ptproj        (exit 1 on violations)
    powertree nets examples\\DemoBoard.ptproj
    powertree search examples\\DemoBoard.ptproj zynq
    powertree export pdf examples\\DemoBoard.ptproj -o report.pdf
    powertree export png examples\\DemoBoard.ptproj -o tree.png --tree Battery
    powertree templates
    powertree demo -o MyDemo.ptproj
    powertree gui [project.ptproj]
"""

from __future__ import annotations

import argparse
import json
import sys

from . import api, APP_NAME, __version__
from .model.calc import fmt_si


def _p(data, as_json: bool):
    if as_json:
        print(json.dumps(data, indent=2, default=str))
        return True
    return False


def cmd_info(args):
    summary = api.project_summary(api.load(args.project))
    if _p(summary, args.json):
        return 0
    print(f"Project: {summary['name']}  ({summary['file']})")
    if summary["description"]:
        print(f"  {summary['description']}")
    for t in summary["trees"]:
        state = "clean" if not (t["errors"] or t["warnings"]) else \
            f"{t['errors']} errors / {t['warnings']} warnings"
        eff = f", η {t['efficiency_pct']:g} %" \
            if t.get("efficiency_pct") is not None else ""
        print(f"  ⚡ {t['name']}: {t['elements']} elements, "
              f"{t['blocks']} blocks, source '{t['source']}', "
              f"P {fmt_si(t['p_typ_w'], 'W')} typ / "
              f"{fmt_si(t['p_max_w'], 'W')} max{eff}, "
              f"loss {fmt_si(t.get('p_loss_typ_w'), 'W')} — {state}")
        for c in t.get("top_consumers", [])[:5]:
            where = f" [{c['block']}]" if c["block"] else ""
            print(f"      {c['pct_of_source']:5.1f} %  "
                  f"{fmt_si(c['p_typ_w'], 'W'):>9s}  {c['name']}{where}")
    print(f"  Notes: {summary['notes']}")
    return 0


def cmd_solve(args):
    result = api.solve(api.load(args.project), args.tree, args.state)
    if _p(result, args.json):
        return 0
    print(f"Tree: {result['tree']} · state: {result['scenario']} "
          f"(converged: {result['converged']})")
    for row in result["elements"]:
        op = row["operating_points"]["typ"]
        pad = "  " * row["depth"]
        print(f"  {pad}{row['name']:<32s} [{row['kind']:<9s}] "
              f"Vin {fmt_si(op['v_in'], 'V'):>9s}  "
              f"Iin {fmt_si(op['i_in'], 'A'):>9s}  "
              f"Pin {fmt_si(op['p_in'], 'W'):>9s}")
    for w in result["warnings"]:
        print(f"  {w['severity'].upper():>5s} [{w['corner']}] {w['message']}")
    return 0


def cmd_validate(args):
    result = api.validate(api.load(args.project))
    if not _p(result, args.json):
        for f in result["findings"]:
            where = f"{f['tree']} / {f['element']}" if f["element"] else \
                (f["tree"] or "project")
            print(f"{f['severity'].upper():>5s} [{f['corner']}] {where}: "
                  f"{f['message']}")
        print(f"{'PASS' if result['ok'] else 'FAIL'}: "
              f"{result['errors']} errors, {result['warnings']} warnings")
    return 0 if result["ok"] else 1


def cmd_nets(args):
    result = api.nets_report(api.load(args.project))
    if _p(result, args.json):
        return 0
    for n in result["nets"]:
        v = fmt_si(n["v_typ"], "V") if n["v_typ"] is not None else "—"
        print(f"  {n['name']:<18s} {v:>9s}  loads: {n['consumers']:<3d} "
              f"defined by: {', '.join(n['definers'])}")
    for c in result["conflicts"]:
        print(f"  CONFLICT: {c}")
    return 1 if result["conflicts"] else 0


def cmd_search(args):
    hits = api.search(api.load(args.project), args.query)
    if _p(hits, args.json):
        return 0
    for h in hits:
        print(f"  [{h['tree']}] {h['name']} ({h['kind']}, "
              f"{h['refdes'] or '-'}, {h['signal_name'] or '-'}) "
              f"— matched {h['matched_field']}")
    print(f"{len(hits)} match(es)")
    return 0


def cmd_headroom(args):
    project = api.load(args.project)
    tree = api.find_tree(project, args.tree)
    rows = api.rail_headroom(tree)
    if _p(rows, args.json):
        return 0
    if not rows:
        print("No limited rails in this tree — set current/power limits on "
              "sources and converters to budget them.")
        return 0
    print(f"Rail budget — {tree.name} (worst-case corner):")
    for h in rows:
        rail = f" [{h['rail']}]" if h["rail"] else ""
        print(f"  {h['name']:<24s}{rail:<14s} limit {h['limit']:>8s}  "
              f"used {h['used_pct']:5.1f} %  headroom "
              f"{fmt_si(h['extra_load_w'], 'W'):>9s} of extra load")
    return 0


def cmd_templates(args):
    templates = api.list_templates()
    if _p(templates, args.json):
        return 0
    for t in templates:
        print(f"  {t['key']:<12s} {t['name']} [{t['category']}] "
              f"rails: {', '.join(t['rails'])}")
    return 0


def cmd_export(args):
    project = api.load(args.project)
    written = api.export(project, args.kind, args.output, args.tree,
                         getattr(args, "style", None))
    print(f"Wrote {written}")
    return 0


def cmd_demo(args):
    project = api.demo_project()
    api.save(project, args.output)
    print(f"Demo project written to {args.output}")
    return 0


def cmd_gui(args):
    from .ui.app_entry import run_gui
    return run_gui(args.project)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="powertree",
        description=f"{APP_NAME} {__version__} — power tree analysis "
                    "(GUI, CLI, MCP).")
    parser.add_argument("--version", action="version",
                        version=f"{APP_NAME} {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, project=True):
        if project:
            p.add_argument("project", help="path to .ptproj file")
        p.add_argument("--json", action="store_true",
                       help="machine-readable JSON output")

    p = sub.add_parser("info", help="project summary")
    common(p)
    p.set_defaults(fn=cmd_info)

    p = sub.add_parser("solve", help="solve a tree and print operating points")
    common(p)
    p.add_argument("--tree", help="tree name (default: first)")
    p.add_argument("--state", help="operating state to apply (default: Base)")
    p.set_defaults(fn=cmd_solve)

    p = sub.add_parser("validate",
                       help="margin/net gate for CI — exit 1 on violations")
    common(p)
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("nets", help="global net registry + conflicts")
    common(p)
    p.set_defaults(fn=cmd_nets)

    p = sub.add_parser("headroom",
                       help="remaining budget per limited rail (worst case)")
    common(p)
    p.add_argument("--tree", help="tree name (default: first)")
    p.set_defaults(fn=cmd_headroom)

    p = sub.add_parser("search", help="find elements across all trees")
    common(p)
    p.add_argument("query")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("templates", help="list device templates")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_templates)

    p = sub.add_parser("export", help="export reports/images")
    p.add_argument("kind", choices=["pdf", "html", "png", "csv", "xlsx",
                                    "xlsm", "notes-md", "notes-html",
                                    "notes-pdf"])
    p.add_argument("project")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--tree", help="tree name (png only; default: first)")
    p.add_argument("--style", choices=["dark", "print"],
                   help="flowchart style for pdf/png (print = white)")
    p.set_defaults(fn=cmd_export)

    p = sub.add_parser("demo", help="write the built-in demo project")
    p.add_argument("-o", "--output", default="DemoBoard.ptproj")
    p.set_defaults(fn=cmd_demo)

    p = sub.add_parser("gui", help="launch the desktop app")
    p.add_argument("project", nargs="?", help="optional .ptproj to open")
    p.set_defaults(fn=cmd_gui)
    return parser


def main(argv=None) -> int:
    # never crash on Unicode in legacy Windows consoles (cp1252 etc.)
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (OSError, ValueError):
                pass
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
