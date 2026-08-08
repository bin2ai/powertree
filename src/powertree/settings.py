"""Application settings (QSettings-backed, persisted per user).

Three levels of display configuration cascade:
  app default  ->  per-tree default  ->  per-element override
(the most specific wins). `resolve_detail()` implements the cascade.
"""

from __future__ import annotations

DETAIL_LEVELS = ("minimal", "standard", "exhaustive")

DEFAULTS = {
    "canvas_style": "dark",          # dark | print (white, printable)
    "heat_mode": False,              # tint cards by power consumption
    "detail_default": "standard",    # minimal | standard | exhaustive
    "legend": True,
    "autofit_on_switch": True,
    "default_orientation": "TD",     # for new trees
    "png_scale": 3.0,                # HD image export scale
    "pdf_include_images": True,
    "pdf_include_notes": True,
    "si_digits": 3.0,                # significant digits in displayed values
    "minimap": True,                 # navigation minimap overlay
    "grid_threshold": 7.0,           # wrap >=N leaf loads into a rail grid
}


class AppSettings:
    """Thin typed wrapper over QSettings with defaults."""

    def __init__(self):
        from PySide6.QtCore import QSettings
        self._qs = QSettings("PowerTree", "PowerTree")

    def get(self, key: str):
        default = DEFAULTS[key]
        value = self._qs.value(key, default)
        if isinstance(default, bool):
            return value in (True, "true", "True", 1, "1")
        if isinstance(default, float):
            try:
                return float(value)
            except (TypeError, ValueError):
                return default
        return value if value else default

    def set(self, key: str, value) -> None:
        self._qs.setValue(key, value)

    def as_dict(self) -> dict:
        return {k: self.get(k) for k in DEFAULTS}

    # ---- recent projects (most recent first, max 8) ----
    def recent_files(self) -> list:
        raw = self._qs.value("recent_files", "")
        return [p for p in str(raw or "").split("|") if p]

    def push_recent(self, path: str) -> None:
        items = [path] + [p for p in self.recent_files() if p != path]
        self._qs.setValue("recent_files", "|".join(items[:8]))


def resolve_detail(app_default: str, tree, element=None) -> str:
    """app default -> tree.detail_default -> element.display_detail."""
    detail = app_default if app_default in DETAIL_LEVELS else "standard"
    if tree is not None and getattr(tree, "detail_default", "") in DETAIL_LEVELS:
        detail = tree.detail_default
    if element is not None and \
            getattr(element, "display_detail", None) in DETAIL_LEVELS:
        detail = element.display_detail
    return detail
