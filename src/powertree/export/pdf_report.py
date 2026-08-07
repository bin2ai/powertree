"""Full project PDF report (reportlab).

Per tree: description, embedded HD flowchart, hierarchy table with typ / max
operating points, block summary, margin & warning analysis. Optionally a full
notes appendix so one PDF carries the entire design record.
"""

from __future__ import annotations

import html
import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, PageBreak,
)

from ..model.elements import Project, PowerTree, ElementKind, LimitType
from ..model.calc import solve_tree, TreeResults, block_power, fmt_si
from .md_render import build_styles, md_to_flowables
from .notes_export import collect_notes, _element_links_line
from .image_export import tree_png_bytes

KIND_FILL = {
    ElementKind.SOURCE: colors.HexColor("#fdf1dc"),
    ElementKind.CONVERTER: colors.HexColor("#e2edfd"),
    ElementKind.LOAD: colors.HexColor("#e0f5ec"),
    ElementKind.SERIES: colors.HexColor("#eef1f6"),
}
SEV_FILL = {"error": colors.HexColor("#fde3e8"), "warn": colors.HexColor("#fdf3d7")}


def _esc(text: str) -> str:
    return html.escape(text or "")


def _hierarchy_rows(tree: PowerTree, results: TreeResults, styles):
    header = ["Element", "Type", "RefDes / Signal",
              "Vin typ", "Iin typ", "Pin typ", "Pout typ",
              "Pin max", "Loss typ", "Status"]
    rows = [header]
    meta_rows = []

    def status_text(el):
        warns = results.warnings_for(el.id)
        if not warns:
            return "OK"
        worst = results.worst_severity(el.id)
        return f"{'VIOLATION' if worst == 'error' else 'LOW MARGIN'} ({len(warns)})"

    def add(el, depth):
        typ = results.get(el.id, "typ")
        mx = results.get(el.id, "max")
        indent = " " * depth + ("└ " if depth else "")
        rows.append([
            Paragraph(f"{indent}<b>{_esc(el.name)}</b>", styles["PTBody"]),
            el.kind, _esc(" / ".join(x for x in (el.refdes, el.signal_name) if x)),
            fmt_si(typ.v_in, "V"), fmt_si(typ.i_in, "A"), fmt_si(typ.p_in, "W"),
            fmt_si(typ.p_out, "W") if el.kind != ElementKind.LOAD else "—",
            fmt_si(mx.p_in, "W"),
            fmt_si(typ.p_loss, "W") if typ.p_loss > 1e-12 else "—",
            status_text(el),
        ])
        meta_rows.append((len(rows) - 1, el, results.worst_severity(el.id)))
        for child in tree.children_of(el.id):
            add(child, depth + 1)

    if tree.source:
        add(tree.source, 0)
    return rows, meta_rows


def _tree_flowables(tree: PowerTree, results: TreeResults, styles,
                    include_image: bool = True):
    flow = [Paragraph(_esc(tree.name), styles["PTH1"])]
    if tree.description:
        flow.append(Paragraph(_esc(tree.description), styles["PTBody"]))
    src = tree.source
    if src is None:
        flow.append(Paragraph("This tree has no source yet.", styles["PTMeta"]))
        return flow

    typ = results.get(src.id, "typ")
    mx = results.get(src.id, "max")
    limit = ""
    if src.limit_type != LimitType.NONE and src.limit_value > 0:
        unit = "A" if src.limit_type == LimitType.CURRENT else "W"
        used = mx.i_out if src.limit_type == LimitType.CURRENT else mx.p_out
        limit = (f" · limit {src.limit_value:g} {unit} "
                 f"({used / src.limit_value * 100:.0f} % used worst-case)")
    flow.append(Paragraph(
        f"Source <b>{_esc(src.name)}</b>: {src.v_min:g} / {src.v_typ:g} / "
        f"{src.v_max:g} V — delivers {fmt_si(typ.p_out, 'W')} typ / "
        f"{fmt_si(mx.p_out, 'W')} max{limit}", styles["PTBody"]))
    flow.append(Spacer(1, 4))

    if include_image:
        try:
            png = tree_png_bytes(tree, scale=2.5)
            img = RLImage(io.BytesIO(png))
            max_w, max_h = 174 * mm, 120 * mm
            ratio = min(max_w / img.drawWidth, max_h / img.drawHeight, 1.0)
            img.drawWidth *= ratio
            img.drawHeight *= ratio
            img.hAlign = "CENTER"
            flow += [img, Spacer(1, 6)]
        except Exception as exc:      # image export must never sink the report
            flow.append(Paragraph(f"(flowchart image unavailable: {_esc(str(exc))})",
                                  styles["PTMeta"]))

    rows, meta = _hierarchy_rows(tree, results, styles)
    table = Table(rows, hAlign="LEFT", repeatRows=1,
                  colWidths=[46 * mm, 15 * mm, 24 * mm, 13 * mm, 14 * mm, 14 * mm,
                             14 * mm, 14 * mm, 14 * mm, 18 * mm])
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 6.6),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a2030")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c3ccdd")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    for row_idx, el, severity in meta:
        fill = SEV_FILL.get(severity) or KIND_FILL.get(el.kind)
        if fill:
            style.append(("BACKGROUND", (0, row_idx), (-1, row_idx), fill))
    table.setStyle(TableStyle(style))
    flow += [table, Spacer(1, 6)]

    # block summary
    if tree.blocks:
        flow.append(Paragraph("Blocks", styles["PTH3"]))
        brows = [["Block", "Members", "P typ", "P max"]]
        for bid, block in tree.blocks.items():
            members = tree.block_members(bid)
            brows.append([
                _esc(block.name), str(len(members)),
                fmt_si(block_power(tree, results, bid, "typ"), "W"),
                fmt_si(block_power(tree, results, bid, "max"), "W")])
        bt = Table(brows, hAlign="LEFT",
                   colWidths=[70 * mm, 20 * mm, 25 * mm, 25 * mm])
        bt.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8ecf5")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c3ccdd")),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ]))
        flow += [bt, Spacer(1, 6)]

    # warnings
    flow.append(Paragraph("Margin analysis", styles["PTH3"]))
    if not results.warnings:
        flow.append(Paragraph(
            "All margins healthy: no limit, voltage-window or convergence issues "
            "in any corner.", styles["PTBody"]))
    else:
        wrows = [["Severity", "Corner", "Message"]]
        for w in results.warnings:
            wrows.append([w.severity.upper(), w.corner,
                          Paragraph(_esc(w.message), styles["PTBody"])])
        wt = Table(wrows, hAlign="LEFT", colWidths=[18 * mm, 14 * mm, 140 * mm])
        wstyle = [
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8ecf5")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c3ccdd")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ]
        for i, w in enumerate(results.warnings, start=1):
            fill = SEV_FILL.get(w.severity)
            if fill:
                wstyle.append(("BACKGROUND", (0, i), (-1, i), fill))
        wt.setStyle(TableStyle(wstyle))
        flow.append(wt)
    return flow


def export_pdf_report(project: Project, path: str, include_notes: bool = True,
                      include_images: bool = True) -> str:
    styles = build_styles()
    doc = SimpleDocTemplate(
        path, pagesize=A4, topMargin=14 * mm, bottomMargin=14 * mm,
        leftMargin=16 * mm, rightMargin=16 * mm,
        title=f"{project.name} — Power Tree Report", author="PowerTree")

    flow = [Spacer(1, 40 * mm),
            Paragraph(_esc(project.name), styles["Title"]),
            Paragraph("Power Tree Analysis Report", styles["PTH2"]),
            Spacer(1, 6)]
    if project.description:
        flow.append(Paragraph(_esc(project.description), styles["PTBody"]))
    author = f" · {project.author}" if project.author else ""
    flow.append(Paragraph(f"Generated {date.today().isoformat()} by PowerTree"
                          f"{author}", styles["PTMeta"]))
    flow.append(Spacer(1, 10))
    orows = [["Power tree", "Elements", "Source", "P typ", "P max", "Findings"]]
    all_results = {}
    for tree in project.trees:
        results = solve_tree(tree)
        all_results[tree.id] = results
        src = tree.source
        typ = results.get(src.id, "typ") if src else None
        mx = results.get(src.id, "max") if src else None
        errs = sum(1 for w in results.warnings if w.severity == "error")
        warns = sum(1 for w in results.warnings if w.severity == "warn")
        orows.append([
            _esc(tree.name), str(len(tree.elements)),
            _esc(src.name) if src else "—",
            fmt_si(typ.p_out, "W") if typ else "—",
            fmt_si(mx.p_out, "W") if mx else "—",
            f"{errs} errors, {warns} warnings" if (errs or warns) else "clean"])
    ot = Table(orows, hAlign="LEFT",
               colWidths=[45 * mm, 18 * mm, 40 * mm, 20 * mm, 20 * mm, 30 * mm])
    ot.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a2030")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c3ccdd")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]))
    flow.append(ot)

    for tree in project.trees:
        flow.append(PageBreak())
        flow += _tree_flowables(tree, all_results[tree.id], styles,
                                include_image=include_images)

    if include_notes and project.notes:
        flow.append(PageBreak())
        flow.append(Paragraph("Appendix — Design Notes", styles["PTH1"]))
        for note, depth in collect_notes(project):
            level = min(depth + 2, 3)
            flow.append(Paragraph(_esc(note.title), styles[f"PTH{level}"]))
            links = _element_links_line(project, note)
            if links:
                flow.append(Paragraph(f"Linked elements: {_esc(links)}",
                                      styles["PTMeta"]))
            flow.extend(md_to_flowables(note.body_md, note.images, styles))
            flow.append(Spacer(1, 5))

    doc.build(flow)
    return path
