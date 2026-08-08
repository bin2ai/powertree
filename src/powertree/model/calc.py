"""Bottom-up power tree solver.

For each corner (min / typ / max source & converter voltages, typ / max load
demand) the solver runs a damped fixed-point iteration:

  1. top-down: propagate rail voltages (converters regulate to their own Vout,
     series elements drop I*R),
  2. bottom-up: aggregate currents/powers from the leaves to the source.

Series resistances are clamped to sane bounds and rail voltages are floored at
a small epsilon so the math never divides by zero, even for pathological
inputs; a warning is raised instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .elements import (
    PowerTree, Element, Source, Converter, Load, ElementKind, LoadType, LimitType, V_EPS,
)

CORNERS = ("min", "typ", "max")
V_FLOOR = 1e-3           # rail collapse floor for bounded math
MAX_ITER = 80
TOL = 1e-9


@dataclass
class ElementResult:
    """Solved operating point of one element, per corner."""
    v_in: float = 0.0
    i_in: float = 0.0
    p_in: float = 0.0
    v_out: float = 0.0
    i_out: float = 0.0
    p_out: float = 0.0
    p_loss: float = 0.0      # dissipated in this element (converter/series loss)
    collapsed_rail: bool = False


@dataclass
class Warning_:
    severity: str            # "error" | "warn" | "info"
    element_id: Optional[str]
    corner: str
    message: str


@dataclass
class TreeResults:
    results: dict = field(default_factory=dict)   # element_id -> {corner: ElementResult}
    warnings: list = field(default_factory=list)  # list[Warning_]
    converged: bool = True

    def get(self, element_id: str, corner: str = "typ") -> ElementResult:
        return self.results.get(element_id, {}).get(corner, ElementResult())

    def warnings_for(self, element_id: str) -> list:
        return [w for w in self.warnings if w.element_id == element_id]

    def worst_severity(self, element_id: str) -> Optional[str]:
        sevs = {w.severity for w in self.warnings_for(element_id)}
        for s in ("error", "warn", "info"):
            if s in sevs:
                return s
        return None


def _source_v(src: Source, corner: str) -> float:
    return {"min": src.v_min, "typ": src.v_typ, "max": src.v_max}[corner]


def _conv_vout(conv: Converter, corner: str, v_in: float = None) -> float:
    if conv.topology == "unregulated":
        # Vout tracks Vin (transformer / charge pump ratio, pass switch...)
        base = v_in if v_in is not None else conv.vout_typ
        return max(base * conv.ratio, V_EPS)
    return {"min": conv.vout_min, "typ": conv.vout_typ, "max": conv.vout_max}[corner]


def _load_value(load: Load, corner: str) -> float:
    if corner == "max" and load.value_max is not None:
        return load.value_max
    return load.value_typ


def _load_current(load: Load, corner: str, v: float) -> float:
    """Load input current at rail voltage v for a corner. min/typ corners use
    the duty-weighted average draw; the max corner keeps the full peak."""
    duty = load.duty if corner != "max" else 1.0
    if load.load_type == LoadType.RESISTIVE:
        return duty * v / load.resistance
    value = _load_value(load, corner)
    if load.load_type == LoadType.POWER:
        return duty * value / v
    return duty * value          # current-type


def solve_tree(tree: PowerTree, scenario: str | None = None) -> TreeResults:
    if scenario:
        from .scenarios import apply_scenario
        tree = apply_scenario(tree, scenario)
    out = TreeResults()
    src = tree.source
    if src is None:
        out.warnings.append(Warning_(
            "info", None, "typ", "Tree has no source yet — nothing to solve."))
        return out

    for el_id in tree.elements:
        out.results[el_id] = {}

    for corner in CORNERS:
        converged = _solve_corner(tree, src, corner, out)
        out.converged = out.converged and converged

    _check_margins(tree, src, out)
    return out


def _solve_corner(tree: PowerTree, src: Source, corner: str, out: TreeResults) -> bool:
    v_in: dict[str, float] = {}     # element_id -> input rail voltage
    i_in: dict[str, float] = {}     # element_id -> input current drawn

    # initial top-down pass with zero series drop
    def init_v(el: Element, v_rail: float):
        v_in[el.id] = v_rail
        v_next = _conv_vout(el, corner, v_rail) \
            if el.kind == ElementKind.CONVERTER else v_rail
        for child in tree.children_of(el.id):
            init_v(child, v_next)

    init_v(src, _source_v(src, corner))

    converged = False
    for _ in range(MAX_ITER):
        # ---- bottom-up: currents/powers given voltages ----
        def solve_i(el: Element) -> float:
            v = max(v_in[el.id], V_FLOOR)
            if el.kind == ElementKind.LOAD:
                i = _load_current(el, corner, v)
            elif el.kind == ElementKind.CONVERTER:
                p_out = sum(solve_i(c) * max(v_in[c.id], V_FLOOR)
                            for c in tree.children_of(el.id))
                vout = max(_conv_vout(el, corner, v), V_FLOOR)
                eff = el.efficiency_at(p_out / vout)
                i = p_out / (eff * v) + el.quiescent_ma / 1000.0
            else:   # series element or (recursively) source
                i = sum(solve_i(c) for c in tree.children_of(el.id))
            i_in[el.id] = i
            return i

        solve_i(src)

        # ---- top-down: voltages given currents ----
        max_dv = 0.0

        def update_v(el: Element, v_rail: float):
            nonlocal max_dv
            old = v_in[el.id]
            # damped update stabilises power loads behind series resistance
            new = old + 0.7 * (v_rail - old)
            v_in[el.id] = new
            max_dv = max(max_dv, abs(new - old))
            if el.kind == ElementKind.CONVERTER:
                v_next = _conv_vout(el, corner, v_in[el.id])
            elif el.kind == ElementKind.SERIES:
                v_next = v_in[el.id] - i_in.get(el.id, 0.0) * el.resistance
            else:
                v_next = v_in[el.id]
            v_next = max(v_next, V_FLOOR)
            for child in tree.children_of(el.id):
                update_v(child, v_next)

        update_v(src, _source_v(src, corner))
        if max_dv < TOL:
            converged = True
            break

    # ---- final consistent bottom-up with converged voltages ----
    def finalize(el: Element) -> ElementResult:
        raw_v = v_in[el.id]
        v = max(raw_v, V_FLOOR)
        res = ElementResult(v_in=v,
                            collapsed_rail=(raw_v <= V_FLOOR * 1.001 and el is not src))
        children = tree.children_of(el.id)
        child_res = [finalize(c) for c in children]

        if el.kind == ElementKind.LOAD:
            res.i_in = _load_current(el, corner, v)
            res.p_in = res.i_in * v
        elif el.kind == ElementKind.CONVERTER:
            res.v_out = _conv_vout(el, corner, v)
            res.p_out = sum(c.p_in for c in child_res)
            res.i_out = res.p_out / max(res.v_out, V_FLOOR)
            eff = el.efficiency_at(res.i_out)
            res.p_in = res.p_out / eff + (el.quiescent_ma / 1000.0) * v
            res.i_in = res.p_in / v
            res.p_loss = res.p_in - res.p_out
        elif el.kind == ElementKind.SERIES:
            res.i_in = sum(c.i_in for c in child_res)
            res.i_out = res.i_in
            res.p_loss = res.i_in ** 2 * el.resistance
            res.v_out = max(v - res.i_in * el.resistance, V_FLOOR)
            res.p_out = sum(c.p_in for c in child_res)
            res.p_in = res.p_out + res.p_loss
        else:   # source
            res.v_out = v
            res.i_out = sum(c.i_in for c in child_res)
            res.p_out = sum(c.p_in for c in child_res)
            res.i_in = res.i_out
            res.p_in = res.p_out

        out.results[el.id][corner] = res
        return res

    finalize(src)

    if not converged:
        out.warnings.append(Warning_(
            "warn", None, corner,
            f"Solver did not fully converge in the '{corner}' corner "
            "(series-resistance / power-load interaction is extreme)."))
    return converged


def _check_margins(tree: PowerTree, src: Source, out: TreeResults) -> None:
    warn = out.warnings.append

    # source limits (worst corner)
    if src.limit_type != LimitType.NONE and src.limit_value > 0:
        for corner in CORNERS:
            res = out.get(src.id, corner)
            actual = res.i_out if src.limit_type == LimitType.CURRENT else res.p_out
            unit = "A" if src.limit_type == LimitType.CURRENT else "W"
            margin_pct = (src.limit_value - actual) / src.limit_value * 100.0
            if actual > src.limit_value:
                warn(Warning_("error", src.id, corner,
                              f"Source {src.limit_type} limit exceeded in '{corner}' corner: "
                              f"{actual:.4g} {unit} > {src.limit_value:.4g} {unit} "
                              f"(margin {margin_pct:.1f} %)."))
            elif margin_pct < 10:
                warn(Warning_("warn", src.id, corner,
                              f"Source {src.limit_type} margin below 10 % in '{corner}' corner: "
                              f"{actual:.4g} {unit} of {src.limit_value:.4g} {unit} "
                              f"({margin_pct:.1f} % left)."))

    for el in tree.elements.values():
        # converter checks
        if el.kind == ElementKind.CONVERTER:
            if el.limit_type != LimitType.NONE and el.limit_value > 0:
                for corner in CORNERS:
                    res = out.get(el.id, corner)
                    actual = res.i_out if el.limit_type == LimitType.CURRENT else res.p_out
                    unit = "A" if el.limit_type == LimitType.CURRENT else "W"
                    margin_pct = (el.limit_value - actual) / el.limit_value * 100.0
                    if actual > el.limit_value:
                        warn(Warning_("error", el.id, corner,
                                      f"'{el.name}' output {el.limit_type} limit exceeded in "
                                      f"'{corner}' corner: {actual:.4g} {unit} > "
                                      f"{el.limit_value:.4g} {unit}."))
                    elif margin_pct < 10:
                        warn(Warning_("warn", el.id, corner,
                                      f"'{el.name}' output {el.limit_type} margin below 10 % "
                                      f"in '{corner}' corner ({margin_pct:.1f} % left)."))
            for corner in CORNERS:
                res = out.get(el.id, corner)
                if el.topology in ("buck", "ldo") and res.v_out > res.v_in + V_EPS:
                    warn(Warning_("warn", el.id, corner,
                                  f"'{el.name}' is a step-down ({el.topology})"
                                  f" but Vout {res.v_out:.3g} V > Vin "
                                  f"{res.v_in:.3g} V in '{corner}' corner."))
                    break
                if el.topology == "boost" and res.v_out < res.v_in - V_EPS:
                    warn(Warning_("warn", el.id, corner,
                                  f"'{el.name}' is a boost but Vout {res.v_out:.3g} V < Vin "
                                  f"{res.v_in:.3g} V in '{corner}' corner."))
                    break

        # power-up sequencing: a rail must not enable before its input rail
        if el.kind == ElementKind.CONVERTER and el.seq_order > 0:
            parent = tree.parent_of(el)
            while parent is not None:
                if parent.kind == ElementKind.CONVERTER:
                    if parent.seq_order > 0 and \
                            parent.seq_order > el.seq_order:
                        warn(Warning_("warn", el.id, "typ",
                                      f"Sequencing: '{el.name}' enables at "
                                      f"step {el.seq_order} but its input "
                                      f"rail '{parent.name}' only enables at "
                                      f"step {parent.seq_order} — the rail "
                                      "powers up before its supply."))
                    break
                parent = tree.parent_of(parent)

        # load input-voltage window
        if el.kind == ElementKind.LOAD:
            for corner in CORNERS:
                res = out.get(el.id, corner)
                if el.v_in_min is not None and res.v_in < el.v_in_min - V_EPS:
                    warn(Warning_("error", el.id, corner,
                                  f"'{el.name}' undervoltage in '{corner}' corner: "
                                  f"{res.v_in:.4g} V < min {el.v_in_min:.4g} V "
                                  f"(margin {res.v_in - el.v_in_min:+.4g} V)."))
                if el.v_in_max is not None and res.v_in > el.v_in_max + V_EPS:
                    warn(Warning_("error", el.id, corner,
                                  f"'{el.name}' overvoltage in '{corner}' corner: "
                                  f"{res.v_in:.4g} V > max {el.v_in_max:.4g} V "
                                  f"(margin {el.v_in_max - res.v_in:+.4g} V)."))

        # series element ratings: current, dissipation, input window
        if el.kind == ElementKind.SERIES:
            for corner in CORNERS:
                res = out.get(el.id, corner)
                if el.i_max is not None and el.i_max > 0:
                    pct = res.i_in / el.i_max * 100
                    if res.i_in > el.i_max:
                        warn(Warning_("error", el.id, corner,
                                      f"'{el.name}' current rating exceeded in "
                                      f"'{corner}' corner: {res.i_in:.4g} A > "
                                      f"{el.i_max:.4g} A ({pct:.0f} %)."))
                    elif pct > 90:
                        warn(Warning_("warn", el.id, corner,
                                      f"'{el.name}' at {pct:.0f} % of its "
                                      f"{el.i_max:.4g} A current rating in "
                                      f"'{corner}' corner."))
                if el.p_max is not None and el.p_max > 0:
                    pct = res.p_loss / el.p_max * 100
                    if res.p_loss > el.p_max:
                        warn(Warning_("error", el.id, corner,
                                      f"'{el.name}' dissipation rating exceeded "
                                      f"in '{corner}' corner: "
                                      f"{res.p_loss:.4g} W > {el.p_max:.4g} W."))
                    elif pct > 90:
                        warn(Warning_("warn", el.id, corner,
                                      f"'{el.name}' at {pct:.0f} % of its "
                                      f"{el.p_max:.4g} W dissipation rating in "
                                      f"'{corner}' corner."))
                if el.v_in_min is not None and res.v_in < el.v_in_min - V_EPS:
                    warn(Warning_("error", el.id, corner,
                                  f"'{el.name}' input undervoltage in "
                                  f"'{corner}' corner: {res.v_in:.4g} V < min "
                                  f"{el.v_in_min:.4g} V."))
                if el.v_in_max is not None and res.v_in > el.v_in_max + V_EPS:
                    warn(Warning_("error", el.id, corner,
                                  f"'{el.name}' input overvoltage in "
                                  f"'{corner}' corner: {res.v_in:.4g} V > max "
                                  f"{el.v_in_max:.4g} V."))

        # collapsed rails behind series resistance
        for corner in CORNERS:
            res = out.get(el.id, corner)
            if res.collapsed_rail:
                warn(Warning_("error", el.id, corner,
                              f"Rail feeding '{el.name}' collapsed to ~0 V in '{corner}' "
                              "corner (series resistance drop exceeds the rail voltage)."))
                break


def block_power(tree: PowerTree, results: TreeResults, block_id: str,
                corner: str = "typ") -> float:
    """Aggregate input power of a block: sum of members whose parent is outside
    the block (avoids double counting nested members)."""
    total = 0.0
    for el in tree.block_members(block_id):
        parent = tree.parent_of(el)
        if parent is None or parent.block_id != block_id:
            total += results.get(el.id, corner).p_in
    return total


# ---------------------------------------------------------------------------
# formatting helpers shared by UI and exports
# ---------------------------------------------------------------------------

# significant digits used by fmt_si — an app-settings knob (3..6)
SI_DIGITS = 3


def fmt_si(value: float, unit: str) -> str:
    """Engineering-notation formatter: 0.0123, 'A' -> '12.3 mA'."""
    if value is None:
        return "—"
    av = abs(value)
    if av < 1e-13:
        return f"0 {unit}"
    for factor, prefix in ((1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"),
                           (1e-6, "µ"), (1e-9, "n"), (1e-12, "p")):
        if av >= factor:
            return f"{value / factor:.{SI_DIGITS}g} {prefix}{unit}"
    return f"{value:.{SI_DIGITS}g} {unit}"
