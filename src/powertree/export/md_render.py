"""Markdown rendering helpers shared by the PDF / HTML note exports."""

from __future__ import annotations

import base64
import html
import io
import re

import markdown as md_lib

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle, Image as RLImage, Preformatted,
)

_MD = md_lib.Markdown(extensions=["tables", "fenced_code", "sane_lists"])


def build_styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("PTBody", parent=ss["BodyText"], fontSize=9, leading=13))
    ss.add(ParagraphStyle("PTH1", parent=ss["Heading1"], fontSize=16, spaceBefore=10,
                          textColor=colors.HexColor("#1a2030")))
    ss.add(ParagraphStyle("PTH2", parent=ss["Heading2"], fontSize=13, spaceBefore=8,
                          textColor=colors.HexColor("#1a2030")))
    ss.add(ParagraphStyle("PTH3", parent=ss["Heading3"], fontSize=11, spaceBefore=6,
                          textColor=colors.HexColor("#33415c")))
    ss.add(ParagraphStyle("PTBullet", parent=ss["PTBody"], leftIndent=14,
                          bulletIndent=4))
    ss.add(ParagraphStyle("PTCode", parent=ss["Code"], fontSize=8, leading=10,
                          backColor=colors.HexColor("#f1f3f8"), leftIndent=6))
    ss.add(ParagraphStyle("PTMeta", parent=ss["PTBody"], fontSize=8,
                          textColor=colors.HexColor("#667085")))
    return ss


_INLINE_RE = [
    (re.compile(r"\*\*(.+?)\*\*"), r"<b>\1</b>"),
    (re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)"), r"<i>\1</i>"),
    (re.compile(r"`([^`]+)`"), r"<font face='Courier'>\1</font>"),
    (re.compile(r"\[([^\]]+)\]\(([^)]+)\)"), r"<u>\1</u> (\2)"),
]


def _inline(text: str) -> str:
    out = html.escape(text, quote=False)
    for rx, rep in _INLINE_RE:
        out = rx.sub(rep, out)
    return out


def md_to_flowables(md_text: str, images: dict, styles, max_img_w: float = 160 * mm):
    """Convert a markdown note body into reportlab flowables (headings,
    paragraphs, bullets, tables, fenced code, embedded images)."""
    flow = []
    lines = (md_text or "").splitlines()
    i = 0
    para: list = []
    while i <= len(lines):
        line = lines[i] if i < len(lines) else ""
        stripped = line.strip()
        is_last = i == len(lines)

        m_img = re.match(r"!\[([^\]]*)\]\(([^)]+)\)\s*$", stripped)
        m_head = re.match(r"(#{1,6})\s+(.*)", stripped)
        m_bullet = re.match(r"[-*+]\s+(.*)", stripped)
        m_num = re.match(r"\d+[.)]\s+(.*)", stripped)
        is_table = stripped.startswith("|") and stripped.endswith("|")
        is_fence = stripped.startswith("```")
        breaker = (is_last or not stripped or m_head or m_bullet or m_num
                   or is_table or is_fence or m_img)

        if breaker:
            if para:
                flow.append(Paragraph(_inline(" ".join(para)), styles["PTBody"]))
                para = []
            if is_last:
                break
            if m_head:
                level = min(len(m_head.group(1)), 3)
                flow.append(Paragraph(_inline(m_head.group(2)),
                                      styles[f"PTH{level}"]))
            elif m_bullet or m_num:
                text = (m_bullet or m_num).group(1)
                bullet = "•" if m_bullet else stripped.split(None, 1)[0]
                flow.append(Paragraph(f"{bullet} {_inline(text)}",
                                      styles["PTBullet"]))
            elif m_img:
                img_flow = _image_flowable(m_img.group(2), images, max_img_w)
                flow.append(img_flow if img_flow is not None else Paragraph(
                    _inline(f"[image: {m_img.group(2)}]"), styles["PTMeta"]))
            elif is_table:
                rows = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                    if not all(re.fullmatch(r":?-{2,}:?", c or "-") for c in cells):
                        rows.append([Paragraph(_inline(c), styles["PTBody"])
                                     for c in cells])
                    i += 1
                if rows:
                    t = Table(rows, hAlign="LEFT")
                    t.setStyle(TableStyle([
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c3ccdd")),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8ecf5")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ]))
                    flow.append(t)
                    flow.append(Spacer(1, 4))
                continue
            elif is_fence:
                code = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code.append(lines[i])
                    i += 1
                flow.append(Preformatted("\n".join(code), styles["PTCode"]))
                flow.append(Spacer(1, 4))
            elif not stripped:
                pass
        else:
            para.append(stripped)
        i += 1
    return flow


def _image_flowable(src: str, images: dict, max_w: float):
    data = images.get(src)
    if data is None:
        return None
    try:
        raw = base64.b64decode(data)
        img = RLImage(io.BytesIO(raw))
        if img.drawWidth > max_w:
            ratio = max_w / img.drawWidth
            img.drawWidth = max_w
            img.drawHeight *= ratio
        img.hAlign = "LEFT"
        return img
    except Exception:
        return None


def md_to_html_body(md_text: str, images: dict) -> str:
    """Markdown -> HTML with note-embedded images inlined as data URIs."""
    _MD.reset()
    body = _MD.convert(md_text or "")
    for name, b64 in (images or {}).items():
        mime = "image/png"
        low = name.lower()
        if low.endswith((".jpg", ".jpeg")):
            mime = "image/jpeg"
        elif low.endswith(".gif"):
            mime = "image/gif"
        elif low.endswith(".svg"):
            mime = "image/svg+xml"
        body = body.replace(f'src="{name}"', f'src="data:{mime};base64,{b64}"')
    return body
