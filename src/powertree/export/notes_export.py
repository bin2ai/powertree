"""Export the hierarchical notes vault to Markdown, HTML or PDF.

The whole vault (or any subtree of it) is flattened depth-first into one
document; heading levels follow the hierarchy so the structure survives.
"""

from __future__ import annotations

import base64
import html
import os
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from ..model.elements import Project, Note
from .md_render import md_to_flowables, md_to_html_body, build_styles


def _walk(project: Project, parent_id, depth: int, out: list):
    for note in project.note_children(parent_id):
        out.append((note, depth))
        _walk(project, note.id, depth + 1, out)


def collect_notes(project: Project, root_note_id: str | None = None) -> list:
    """[(note, depth)] depth-first; root_note_id=None exports the whole vault."""
    out: list = []
    if root_note_id is None:
        _walk(project, None, 0, out)
    else:
        root = project.notes.get(root_note_id)
        if root:
            out.append((root, 0))
            _walk(project, root.id, 1, out)
    return out


def _element_links_line(project: Project, note: Note) -> str:
    names = []
    for tree in project.trees:
        for el_id in note.linked_element_ids:
            el = tree.elements.get(el_id)
            if el:
                names.append(f"{el.name} ({tree.name})")
    return ", ".join(names)


# ---------------------------------------------------------------- markdown --
def export_notes_markdown(project: Project, path: str,
                          root_note_id: str | None = None) -> str:
    notes = collect_notes(project, root_note_id)
    assets_dir = os.path.splitext(path)[0] + "_assets"
    lines = [f"# {project.name} — Notes", "",
             f"_Exported {date.today().isoformat()} by PowerTree_", ""]
    wrote_assets = False
    for note, depth in notes:
        lines.append(f"{'#' * min(depth + 2, 6)} {note.title}")
        links = _element_links_line(project, note)
        if links:
            lines.append(f"*Linked elements: {links}*")
        lines.append("")
        body = note.body_md or ""
        for name, b64 in note.images.items():
            os.makedirs(assets_dir, exist_ok=True)
            wrote_assets = True
            with open(os.path.join(assets_dir, name), "wb") as fh:
                fh.write(base64.b64decode(b64))
            rel = f"{os.path.basename(assets_dir)}/{name}"
            body = body.replace(f"]({name})", f"]({rel})")
        lines.append(body)
        lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path if not wrote_assets else f"{path} (+ {os.path.basename(assets_dir)}/)"


# -------------------------------------------------------------------- html --
_HTML_CSS = """
:root { color-scheme: light; }
body { font-family: 'Segoe UI', system-ui, sans-serif; max-width: 880px;
       margin: 2rem auto; padding: 0 1.2rem; color: #1a2030; line-height: 1.55; }
h1 { border-bottom: 3px solid #7c5cff; padding-bottom: .3rem; }
h2 { border-bottom: 1px solid #d7dcea; padding-bottom: .2rem; margin-top: 2rem; }
code, pre { background: #f1f3f8; border-radius: 4px; }
pre { padding: .7rem; overflow-x: auto; }
code { padding: .1rem .3rem; }
table { border-collapse: collapse; margin: .8rem 0; }
th, td { border: 1px solid #c3ccdd; padding: .35rem .6rem; }
th { background: #e8ecf5; }
img { max-width: 100%; border-radius: 6px; }
.meta { color: #667085; font-size: .85rem; }
.links { color: #7c5cff; font-size: .85rem; font-style: italic; }
nav { background: #f6f7fb; border: 1px solid #e2e6f0; border-radius: 8px;
      padding: .8rem 1.2rem; }
nav a { color: #4c3fd4; text-decoration: none; }
"""


def export_notes_html(project: Project, path: str,
                      root_note_id: str | None = None) -> str:
    notes = collect_notes(project, root_note_id)
    toc, sections = [], []
    for idx, (note, depth) in enumerate(notes):
        anchor = f"note-{idx}"
        toc.append(f"<div style='margin-left:{depth * 1.1:.1f}rem'>"
                   f"<a href='#{anchor}'>{html.escape(note.title)}</a></div>")
        level = min(depth + 2, 6)
        links = _element_links_line(project, note)
        links_html = (f"<div class='links'>Linked elements: {html.escape(links)}</div>"
                      if links else "")
        sections.append(
            f"<section id='{anchor}'><h{level}>{html.escape(note.title)}</h{level}>"
            f"{links_html}{md_to_html_body(note.body_md, note.images)}</section>")
    doc = (f"<!doctype html><html><head><meta charset='utf-8'>"
           f"<title>{html.escape(project.name)} — Notes</title>"
           f"<style>{_HTML_CSS}</style></head><body>"
           f"<h1>{html.escape(project.name)} — Notes</h1>"
           f"<p class='meta'>Exported {date.today().isoformat()} by PowerTree</p>"
           f"<nav><b>Contents</b>{''.join(toc)}</nav>"
           f"{''.join(sections)}</body></html>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return path


# --------------------------------------------------------------------- pdf --
def export_notes_pdf(project: Project, path: str,
                     root_note_id: str | None = None) -> str:
    styles = build_styles()
    notes = collect_notes(project, root_note_id)
    doc = SimpleDocTemplate(path, pagesize=A4, topMargin=16 * mm,
                            bottomMargin=16 * mm, leftMargin=18 * mm,
                            rightMargin=18 * mm,
                            title=f"{project.name} — Notes")
    flow = [Paragraph(f"{project.name} — Notes", styles["Title"]),
            Paragraph(f"Exported {date.today().isoformat()} by PowerTree",
                      styles["PTMeta"]),
            Spacer(1, 8)]
    for note, depth in notes:
        level = min(depth + 1, 3)
        flow.append(Paragraph(html.escape(note.title), styles[f"PTH{level}"]))
        links = _element_links_line(project, note)
        if links:
            flow.append(Paragraph(f"Linked elements: {html.escape(links)}",
                                  styles["PTMeta"]))
        flow.extend(md_to_flowables(note.body_md, note.images, styles))
        flow.append(Spacer(1, 6))
    doc.build(flow)
    return path
