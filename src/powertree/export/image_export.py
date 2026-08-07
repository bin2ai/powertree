"""HD flowchart image export (PNG)."""

from __future__ import annotations

from ..model.calc import solve_tree
from ..model.elements import PowerTree
from ..ui.canvas import render_tree_image


def export_tree_png(tree: PowerTree, path: str, orientation: str | None = None,
                    scale: float = 3.0, style: str | None = None,
                    detail_default: str = "standard",
                    heat: bool = False) -> str:
    """Render `tree` to a high-resolution PNG. Returns the path written.
    style: None/'dark' or 'print' for a white printable image."""
    results = solve_tree(tree)
    img = render_tree_image(tree, results, orientation=orientation,
                            scale=scale, style=style,
                            detail_default=detail_default, heat=heat)
    if not img.save(path, "PNG"):
        raise IOError(f"Could not write image to {path}")
    return path


def tree_png_bytes(tree: PowerTree, orientation: str | None = None,
                   scale: float = 2.5, style: str | None = None) -> bytes:
    """PNG bytes of the rendered tree (for embedding into PDF/HTML reports)."""
    from PySide6.QtCore import QBuffer, QIODevice
    results = solve_tree(tree)
    img = render_tree_image(tree, results, orientation=orientation,
                            scale=scale, style=style)
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())
