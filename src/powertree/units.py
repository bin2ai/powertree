"""SI-suffix value entry — engineers type '100m', '4.7u', '2.2k', '50 mΩ'
instead of 0.0000047. One parser used by every electrical field."""

from __future__ import annotations

import re

_PREFIXES = {
    "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3,
    "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9,
}

# number, optional SI prefix, optional unit tail (A, V, W, Ω, ohm, H, %…)
_RE = re.compile(
    r"^\s*([+-]?\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?)\s*"
    r"([pnuµmkKMG]?)\s*"
    r"([a-zA-ZΩω%]*)\s*$")


def parse_si(text: str) -> float | None:
    """'100m' -> 0.1, '4.7u' -> 4.7e-6, '2.2k' -> 2200, '3.3' -> 3.3,
    '50 mΩ' -> 0.05, '1e-3' -> 0.001. Returns None when unparseable.

    Ambiguity rule: a lone trailing 'm' is milli (engineering convention);
    unit letters after the prefix ('mA', 'mV', 'mΩ') are ignored."""
    if text is None:
        return None
    m = _RE.match(str(text))
    if not m:
        return None
    number, prefix, unit = m.groups()
    # 'M' vs 'm': '5M' = mega, but '5MHz'-style tails keep their case rule;
    # a lowercase unit like 'mv' ('5mv') means milli + volt
    factor = _PREFIXES.get(prefix, 1.0)
    if not prefix and unit:
        # forms like '100mA' put the prefix inside the unit group when the
        # regex grabbed greedily — check the first unit letter
        first = unit[0]
        if first in _PREFIXES and (len(unit) > 1 or first not in "MG"):
            factor = _PREFIXES[first]
    try:
        return float(number.replace(",", ".")) * factor
    except ValueError:
        return None


def si_text(value: float | None, digits: int = 4) -> str:
    """Engineering-notation text WITHOUT the unit ('0.1' -> '100m'),
    round-trippable through parse_si."""
    if value is None:
        return ""
    if value == 0:
        return "0"
    av = abs(value)
    for factor, prefix in ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""),
                           (1e-3, "m"), (1e-6, "u"), (1e-9, "n"),
                           (1e-12, "p")):
        if av >= factor:
            return f"{value / factor:.{digits}g}{prefix}"
    return f"{value:.{digits}g}"
