"""Global net registry.

Net (signal) names are PROJECT-global — the same net name used in two trees or
two places refers to the same electrical node. Rail-defining elements are
sources, converter outputs and series-element outputs (their `signal_name` is
the net they drive); loads consume the net feeding them.

`collect_nets()` builds the registry and flags electrical inconsistencies:
the same net name defined at meaningfully different nominal voltages.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .elements import Project, PowerTree, Element, ElementKind

# relative disagreement between definers of one net that triggers a conflict
NET_V_TOLERANCE = 0.02


@dataclass
class NetDefiner:
    tree_name: str
    element_name: str
    element_id: str
    kind: str
    v_typ: float | None      # None when not statically known (series drop)


@dataclass
class NetInfo:
    name: str
    definers: list = field(default_factory=list)   # [NetDefiner]
    consumers: int = 0                              # loads fed from this net

    @property
    def v_typ(self) -> float | None:
        vals = [d.v_typ for d in self.definers if d.v_typ is not None]
        return vals[0] if vals else None


def _output_net(el: Element) -> str:
    """Net name an element drives (empty when unnamed)."""
    if el.kind in (ElementKind.SOURCE, ElementKind.CONVERTER,
                   ElementKind.SERIES):
        return (el.signal_name or "").strip()
    return ""


def input_net(tree: PowerTree, el: Element) -> str:
    """Net name feeding an element: nearest ancestor's named output rail."""
    parent = tree.parent_of(el)
    while parent is not None:
        net = _output_net(parent)
        if net:
            return net
        parent = tree.parent_of(parent)
    return ""


def _defined_voltage(el: Element) -> float | None:
    if el.kind == ElementKind.SOURCE:
        return el.v_typ
    if el.kind == ElementKind.CONVERTER:
        return el.vout_typ
    return None    # series output voltage depends on load current


def collect_nets(project: Project):
    """Returns (nets: {name: NetInfo}, conflicts: [str])."""
    nets: dict[str, NetInfo] = {}
    for tree in project.trees:
        for el in tree.elements.values():
            net = _output_net(el)
            if net:
                info = nets.setdefault(net, NetInfo(net))
                info.definers.append(NetDefiner(
                    tree.name, el.name, el.id, el.kind, _defined_voltage(el)))
            if el.kind == ElementKind.LOAD:
                feed = input_net(tree, el)
                if feed:
                    nets.setdefault(feed, NetInfo(feed)).consumers += 1

    conflicts: list[str] = []
    for info in nets.values():
        vals = [(d.v_typ, d) for d in info.definers if d.v_typ is not None]
        if len(vals) > 1:
            v0 = vals[0][0]
            for v, d in vals[1:]:
                ref = max(abs(v0), 1e-9)
                if abs(v - v0) / ref > NET_V_TOLERANCE:
                    conflicts.append(
                        f"Net '{info.name}' is defined at {v0:g} V by "
                        f"'{vals[0][1].element_name}' ({vals[0][1].tree_name}) "
                        f"but at {v:g} V by '{d.element_name}' ({d.tree_name}) "
                        "— same net name must be one electrical node.")
        hard_definers = [d for d in info.definers
                         if d.kind in (ElementKind.SOURCE,
                                       ElementKind.CONVERTER)]
        if len(hard_definers) > 1:
            trees = {d.tree_name for d in hard_definers}
            if len(trees) == 1:
                names = ", ".join(f"'{d.element_name}'" for d in hard_definers)
                conflicts.append(
                    f"Net '{info.name}' is driven by multiple regulators/"
                    f"sources in tree '{next(iter(trees))}' ({names}) — "
                    "parallel rails need explicit sharing design.")
    return nets, conflicts


def all_net_names(project: Project) -> list:
    nets, _ = collect_nets(project)
    return sorted(nets)
