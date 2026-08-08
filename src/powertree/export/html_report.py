"""Single-file HTML report — the zero-install share format.

Everything is inlined (CSS, base64 flowchart images), so the one .html file
can be mailed or dropped on a wiki and opens in any browser: executive
summary with health verdict, per-tree flowchart, top consumers, rail
budgets, per-state comparison and the full findings list.
"""

from __future__ import annotations

import base64
import html
from datetime import date

from ..model.elements import Project
from ..model.calc import solve_tree, fmt_si
from ..model.nets import collect_nets
from ..api import tree_metrics, rail_headroom
from .image_export import tree_png_bytes

_CSS = """
body { font-family: 'Segoe UI', system-ui, sans-serif; max-width: 1080px;
       margin: 1.5rem auto; padding: 0 1rem; color: #1a2030; }
h1 { border-bottom: 3px solid #7c5cff; padding-bottom: .3rem; }
h2 { border-bottom: 1px solid #d7dcea; padding-bottom: .2rem;
     margin-top: 2.2rem; }
table { border-collapse: collapse; margin: .6rem 0; font-size: .86rem; }
th, td { border: 1px solid #c3ccdd; padding: .3rem .55rem; text-align: left; }
th { background: #1a2030; color: #fff; }
tr.err td { background: #fde3e8; }
tr.warn td { background: #fdf3d7; }
img.tree { max-width: 100%; border-radius: 8px; border: 1px solid #d7dcea; }
.verdict { font-weight: 700; padding: .6rem .9rem; border-radius: 8px;
           display: inline-block; margin: .4rem 0; }
.v-err { background: #fde3e8; color: #b91c1c; }
.v-warn { background: #fdf3d7; color: #92400e; }
.v-ok { background: #dcfce7; color: #166534; }
.meta { color: #667085; font-size: .85rem; }
.kpi { display: inline-block; background: #f6f7fb; border: 1px solid #e2e6f0;
       border-radius: 8px; padding: .5rem .9rem; margin: .2rem .3rem .2rem 0; }
.kpi b { font-size: 1.1rem; }
"""


def _e(text) -> str:
    return html.escape(str(text or ""))


def export_html_report(project: Project, path: str,
                       image_style: str | None = None) -> str:
    from .. import __version__
    author = f" · {_e(project.author)}" if project.author else ""
    parts = []
    if getattr(project, "logo_b64", ""):
        parts.append(f"<img alt='logo' style='max-height:64px' "
                     f"src='data:image;base64,{project.logo_b64}'>")
    parts += [f"<h1>{_e(project.name)} — Power Tree Report</h1>",
             f"<p class='meta'>Generated {date.today().isoformat()} by "
             f"PowerTree v{__version__}{author} · fully self-contained "
             f"file</p>"]
    if project.description:
        parts.append(f"<p>{_e(project.description)}</p>")

    total_errs = total_warns = 0
    solved = {}
    for tree in project.trees:
        r = solve_tree(tree)
        solved[tree.id] = r
        total_errs += sum(1 for w in r.warnings if w.severity == "error")
        total_warns += sum(1 for w in r.warnings if w.severity == "warn")
    cls, verdict = ("v-ok", "✅ HEALTHY — every rail meets its limits and "
                    "voltage windows.")
    if total_errs:
        cls, verdict = "v-err", (f"⛔ ATTENTION — {total_errs} margin "
                                 f"violation(s), {total_warns} warning(s).")
    elif total_warns:
        cls, verdict = "v-warn", (f"⚠ CAUTION — {total_warns} low-margin "
                                  "warning(s).")
    parts.append(f"<div class='verdict {cls}'>{verdict}</div>")

    # KPI strip
    for tree in project.trees:
        m = tree_metrics(tree, solved[tree.id])
        eff = f"{m['efficiency_pct']:g} %" if m["efficiency_pct"] is not None \
            else "—"
        parts.append(
            f"<div class='kpi'>{_e(tree.name)}<br>"
            f"<b>{fmt_si(m['p_source_typ'], 'W')}</b> typ · "
            f"<b>{fmt_si(m['p_source_max'], 'W')}</b> max · η <b>{eff}</b>"
            f"</div>")

    for tree in project.trees:
        r = solved[tree.id]
        m = tree_metrics(tree, r)
        parts.append(f"<h2>⚡ {_e(tree.name)}</h2>")
        if tree.description:
            parts.append(f"<p>{_e(tree.description)}</p>")
        try:
            png = tree_png_bytes(tree, scale=2.0, style=image_style)
            b64 = base64.b64encode(png).decode("ascii")
            parts.append(f"<img class='tree' alt='{_e(tree.name)} flowchart' "
                         f"src='data:image/png;base64,{b64}'>")
        except Exception:
            parts.append("<p class='meta'>(flowchart image unavailable)</p>")

        if m["top_consumers"]:
            parts.append("<h3>Top consumers</h3><table><tr><th>#</th>"
                         "<th>Load</th><th>Block</th><th>P typ</th>"
                         "<th>% of source</th></tr>")
            for i, c in enumerate(m["top_consumers"], start=1):
                parts.append(
                    f"<tr><td>{i}</td><td>{_e(c['name'])}</td>"
                    f"<td>{_e(c['block'])}</td>"
                    f"<td>{fmt_si(c['p_typ_w'], 'W')}</td>"
                    f"<td>{c['pct_of_source']:g} %</td></tr>")
            parts.append("</table>")

        rows = rail_headroom(tree, r)
        if rows:
            parts.append("<h3>Rail budget (worst-case corner)</h3><table>"
                         "<tr><th>Rail / regulator</th><th>Net</th>"
                         "<th>Limit</th><th>Used</th><th>Headroom</th>"
                         "<th>≈ extra load</th></tr>")
            for h in rows:
                klass = " class='err'" if h["headroom_pct"] < 0 else \
                    (" class='warn'" if h["headroom_pct"] < 100 -
                     (project.derating_pct or 100) or h["headroom_pct"] < 10
                     else "")
                parts.append(
                    f"<tr{klass}><td>{_e(h['name'])}</td>"
                    f"<td><code>{_e(h['rail'])}</code></td>"
                    f"<td>{h['limit']}</td><td>{h['used_pct']:g} %</td>"
                    f"<td>{h['headroom_pct']:g} %</td>"
                    f"<td>{fmt_si(h['extra_load_w'], 'W')}</td></tr>")
            parts.append("</table>")

        if project.scenarios and tree.source:
            parts.append("<h3>Operating states</h3><table><tr><th>State</th>"
                         "<th>P min</th><th>P typ</th><th>P max</th>"
                         "<th>Findings</th></tr>")
            for label, scenario in [("Base", None)] + \
                    [(s, s) for s in project.scenarios]:
                sr = solve_tree(tree, scenario)
                errs = sum(1 for w in sr.warnings if w.severity == "error")
                warns = sum(1 for w in sr.warnings if w.severity == "warn")
                klass = " class='err'" if errs else \
                    (" class='warn'" if warns else "")
                src = tree.source
                parts.append(
                    f"<tr{klass}><td>{_e(label)}</td>"
                    f"<td>{fmt_si(sr.get(src.id, 'min').p_out, 'W')}</td>"
                    f"<td>{fmt_si(sr.get(src.id, 'typ').p_out, 'W')}</td>"
                    f"<td>{fmt_si(sr.get(src.id, 'max').p_out, 'W')}</td>"
                    f"<td>{errs} err / {warns} warn</td></tr>")
            parts.append("</table>")

        if r.warnings:
            parts.append("<h3>Findings</h3><table><tr><th>Severity</th>"
                         "<th>Corner</th><th>Message</th></tr>")
            for w in r.warnings:
                klass = " class='err'" if w.severity == "error" else \
                    " class='warn'"
                parts.append(f"<tr{klass}><td>{w.severity.upper()}</td>"
                             f"<td>{w.corner}</td><td>{_e(w.message)}</td>"
                             f"</tr>")
            parts.append("</table>")

    nets, conflicts = collect_nets(project)
    if nets:
        parts.append("<h2>Global nets</h2><table><tr><th>Net</th>"
                     "<th>V typ</th><th>Defined by</th><th>Loads fed</th>"
                     "</tr>")
        for name in sorted(nets):
            info = nets[name]
            definers = "; ".join(f"{d.element_name} ({d.tree_name})"
                                 for d in info.definers)
            v = fmt_si(info.v_typ, "V") if info.v_typ is not None else "—"
            parts.append(f"<tr><td><code>{_e(name)}</code></td><td>{v}</td>"
                         f"<td>{_e(definers)}</td><td>{info.consumers}</td>"
                         f"</tr>")
        parts.append("</table>")
        for c in conflicts:
            parts.append(f"<p class='verdict v-err'>⚠ {_e(c)}</p>")

    doc = (f"<!doctype html><html><head><meta charset='utf-8'>"
           f"<title>{_e(project.name)} — Power Tree Report</title>"
           f"<style>{_CSS}</style></head><body>{''.join(parts)}"
           f"</body></html>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return path
