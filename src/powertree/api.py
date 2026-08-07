"""Headless project API — the single backend shared by the CLI and the MCP
server (and usable directly from any Python script).

Every function is plain-Python in/out (dicts, lists, strings) so it can be
serialized to JSON for scripting or exposed as AI tool calls unchanged.
Qt is only imported for image-bearing exports, with offscreen fallbacks set
automatically when no GUI is present.
"""

from __future__ import annotations

import os

from .model.elements import Project, PowerTree, ElementKind
from .model.calc import solve_tree, fmt_si
from .model import serialization
from .model.nets import collect_nets
from .sampledata import build_sample_project
from .templates import TEMPLATES, template_by_key, instantiate_template

SEARCH_FIELDS = ("name", "signal_name", "refdes", "part_number", "pins",
                 "description")


def _ensure_headless_qt():
    """Allow Qt-based exports without a display."""
    if "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    if os.name == "nt" and "QT_QPA_FONTDIR" not in os.environ:
        fontdir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                               "Fonts")
        os.environ["QT_QPA_FONTDIR"] = fontdir
    from PySide6.QtWidgets import QApplication
    if QApplication.instance() is None:
        QApplication([])


def load(path: str) -> Project:
    return serialization.load_project(path)


def save(project: Project, path: str | None = None) -> str:
    target = path or project.file_path
    if not target:
        raise ValueError("No path given and project has no file path yet.")
    serialization.save_project(project, target)
    return target


def demo_project() -> Project:
    return build_sample_project()


def find_tree(project: Project, name_or_id: str | None) -> PowerTree:
    if not name_or_id:
        if not project.trees:
            raise ValueError("Project has no power trees.")
        return project.trees[0]
    for t in project.trees:
        if t.id == name_or_id or t.name.lower() == name_or_id.lower():
            return t
    raise ValueError(f"No power tree named '{name_or_id}'. "
                     f"Available: {[t.name for t in project.trees]}")


def find_element(tree: PowerTree, ident: str):
    ident_l = ident.lower()
    for el in tree.elements.values():
        if el.id == ident or el.name.lower() == ident_l or \
                (el.refdes and el.refdes.lower() == ident_l) or \
                (el.signal_name and el.signal_name.lower() == ident_l):
            return el
    raise ValueError(f"No element '{ident}' in tree '{tree.name}' "
                     "(match by id, name, refdes or signal name).")


# ------------------------------------------------------------------ queries
def project_summary(project: Project) -> dict:
    trees = []
    total_findings = {"error": 0, "warn": 0}
    for tree in project.trees:
        r = solve_tree(tree)
        src = tree.source
        errs = sum(1 for w in r.warnings if w.severity == "error")
        warns = sum(1 for w in r.warnings if w.severity == "warn")
        total_findings["error"] += errs
        total_findings["warn"] += warns
        typ = r.get(src.id, "typ") if src else None
        mx = r.get(src.id, "max") if src else None
        trees.append({
            "name": tree.name, "id": tree.id,
            "elements": len(tree.elements), "blocks": len(tree.blocks),
            "source": src.name if src else None,
            "p_typ_w": round(typ.p_out, 6) if typ else None,
            "p_max_w": round(mx.p_out, 6) if mx else None,
            "errors": errs, "warnings": warns})
    return {"name": project.name, "description": project.description,
            "file": project.file_path, "trees": trees,
            "notes": len(project.notes), "findings": total_findings}


def element_dict(tree: PowerTree, el, results=None) -> dict:
    out = {"id": el.id, "kind": el.kind, "name": el.name,
           "refdes": el.refdes, "signal_name": el.signal_name,
           "part_number": el.part_number, "pins": el.pins,
           "parent_id": el.parent_id,
           "block": (tree.blocks[el.block_id].name
                     if el.block_id and el.block_id in tree.blocks else None),
           "description": el.description}
    for attr in ("v_min", "v_typ", "v_max", "limit_type", "limit_value",
                 "topology", "efficiency_pct", "vout_min", "vout_typ",
                 "vout_max", "quiescent_ma", "load_type", "value_typ",
                 "value_max", "v_in_min", "v_in_max", "series_type",
                 "resistance_ohm", "inductance_uh", "rating"):
        if hasattr(el, attr):
            out[attr] = getattr(el, attr)
    if results is not None:
        out["operating_points"] = {
            corner: {
                "v_in": res.v_in, "i_in": res.i_in, "p_in": res.p_in,
                "v_out": res.v_out, "i_out": res.i_out, "p_out": res.p_out,
                "p_loss": res.p_loss}
            for corner in ("min", "typ", "max")
            for res in [results.get(el.id, corner)]}
    return out


def solve(project: Project, tree_name: str | None = None) -> dict:
    tree = find_tree(project, tree_name)
    r = solve_tree(tree)

    def walk(el, depth):
        rows.append({**element_dict(tree, el, r), "depth": depth})
        for c in tree.children_of(el.id):
            walk(c, depth + 1)

    rows: list = []
    if tree.source:
        walk(tree.source, 0)
    return {
        "tree": tree.name,
        "converged": r.converged,
        "elements": rows,
        "warnings": [{"severity": w.severity, "corner": w.corner,
                      "element_id": w.element_id, "message": w.message}
                     for w in r.warnings]}


def validate(project: Project) -> dict:
    """CI-style gate: all trees + net conflicts. ok=False on any violation."""
    findings = []
    for tree in project.trees:
        r = solve_tree(tree)
        for w in r.warnings:
            el = tree.elements.get(w.element_id) if w.element_id else None
            findings.append({"tree": tree.name, "severity": w.severity,
                             "corner": w.corner,
                             "element": el.name if el else None,
                             "message": w.message})
    _nets, conflicts = collect_nets(project)
    for c in conflicts:
        findings.append({"tree": None, "severity": "error", "corner": "-",
                         "element": None, "message": c})
    errors = [f for f in findings if f["severity"] == "error"]
    return {"ok": not errors, "errors": len(errors),
            "warnings": len(findings) - len(errors), "findings": findings}


def nets_report(project: Project) -> dict:
    nets, conflicts = collect_nets(project)
    return {"nets": [{
        "name": name, "v_typ": info.v_typ, "consumers": info.consumers,
        "definers": [f"{d.element_name} ({d.tree_name})"
                     for d in info.definers]}
        for name, info in sorted(nets.items())],
        "conflicts": conflicts}


def search(project: Project, query: str) -> list:
    q = query.strip().lower()
    hits = []
    for tree in project.trees:
        for el in tree.elements.values():
            for f in SEARCH_FIELDS:
                if q in str(getattr(el, f, "")).lower():
                    hits.append({"tree": tree.name, "id": el.id,
                                 "kind": el.kind, "name": el.name,
                                 "refdes": el.refdes,
                                 "signal_name": el.signal_name,
                                 "matched_field": f})
                    break
    return hits


def list_templates() -> list:
    return [{"key": t.key, "name": t.name, "category": t.category,
             "part_number": t.part_number, "rails": t.rails,
             "items": [i.name for i in t.items],
             "description": t.description} for t in TEMPLATES]


def apply_template(project: Project, tree_name: str | None, template_key: str,
                   rail_map: dict, block_name: str = "",
                   refdes: str = "") -> dict:
    tree = find_tree(project, tree_name)
    template = template_by_key(template_key)
    if template is None:
        raise ValueError(f"Unknown template '{template_key}'. "
                         f"Available: {[t.key for t in TEMPLATES]}")
    resolved = {}
    for rail, ident in rail_map.items():
        resolved[rail] = find_element(tree, ident).id
    created = instantiate_template(tree, template, resolved,
                                   block_name=block_name, refdes=refdes)
    return {"created": [e.name for e in created], "tree": tree.name}


def set_element_field(project: Project, tree_name: str | None, element: str,
                      field: str, value) -> dict:
    tree = find_tree(project, tree_name)
    el = find_element(tree, element)
    if not hasattr(el, field):
        raise ValueError(f"{el.kind} '{el.name}' has no field '{field}'.")
    current = getattr(el, field)
    if isinstance(current, float) and value is not None:
        value = float(value)
    setattr(el, field, value)
    r = solve_tree(tree)
    return {"element": el.name, "field": field, "value": value,
            "tree_errors": sum(1 for w in r.warnings
                               if w.severity == "error"),
            "tree_warnings": sum(1 for w in r.warnings
                                 if w.severity == "warn")}


# ------------------------------------------------------------------ exports
def export(project: Project, kind: str, out_path: str,
           tree_name: str | None = None) -> str:
    kind = kind.lower()
    if kind in ("png", "pdf"):
        _ensure_headless_qt()
    if kind == "pdf":
        from .export.pdf_report import export_pdf_report
        return export_pdf_report(project, out_path)
    if kind == "png":
        from .export.image_export import export_tree_png
        tree = find_tree(project, tree_name)
        return export_tree_png(tree, out_path, scale=3.0)
    if kind == "xlsx":
        from .export.excel_export import export_excel_xlsx
        return export_excel_xlsx(project, out_path)
    if kind == "xlsm":
        from .export.excel_export import export_excel_xlsm
        path, msg = export_excel_xlsm(project, out_path)
        return f"{path} ({msg})"
    if kind == "notes-md":
        from .export.notes_export import export_notes_markdown
        return export_notes_markdown(project, out_path)
    if kind == "notes-html":
        from .export.notes_export import export_notes_html
        return export_notes_html(project, out_path)
    if kind == "notes-pdf":
        from .export.notes_export import export_notes_pdf
        return export_notes_pdf(project, out_path)
    raise ValueError(
        f"Unknown export kind '{kind}'. Use pdf, png, xlsx, xlsm, "
        "notes-md, notes-html or notes-pdf.")
