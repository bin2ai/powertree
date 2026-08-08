"""Device template library.

A template captures how a real device loads the power tree:
  - an IC (Zynq, PHY, DDR…) = a Block containing one load per supply rail/bank,
    each with its true allowed input-voltage window,
  - a regulator = a Block containing the Converter itself plus its own input
    loading (controller Iq) as a separate load.

Items attach either to an EXTERNAL rail (a key the user maps to an existing
source/converter/series element at instantiation) or to another item of the
same template via "@Item Name" (e.g. loads hanging off the template's own
converter output).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model.elements import (
    PowerTree, Element, Converter, Load, SeriesElement, LoadType, LimitType,
)


@dataclass
class TemplateItem:
    kind: str                 # 'converter' | 'load' | 'series'
    name: str
    rail: str                 # external rail key OR '@<sibling item name>'
    params: dict = field(default_factory=dict)


@dataclass
class DeviceTemplate:
    key: str
    name: str
    category: str
    description: str
    rails: list               # external rail keys that must be mapped
    items: list               # [TemplateItem]
    part_number: str = ""
    datasheet: str = ""


def _load(name, rail, i_typ, i_max, v_lo, v_hi, signal="", pins="") -> TemplateItem:
    return TemplateItem("load", name, rail, {
        "load_type": LoadType.CURRENT, "value_typ": i_typ, "value_max": i_max,
        "v_in_min": v_lo, "v_in_max": v_hi, "signal_name": signal, "pins": pins})


TEMPLATES: list = [
    DeviceTemplate(
        key="zynq7020", name="Zynq-7000 SoC (XC7Z020)", category="SoC / FPGA",
        part_number="XC7Z020-1CLG484", datasheet="DS187 / DS191",
        description="PS+PL SoC: core, aux, BRAM, PLL and IO-bank rails with "
                    "datasheet operating windows (DS191).",
        rails=["1.0V", "1.8V", "3.3V", "1.5V (DDR IO)"],
        items=[
            _load("VCCINT (PL core)", "1.0V", 0.350, 1.200, 0.95, 1.05,
                  "VCCINT", "VCCINT balls"),
            _load("VCCPINT (PS core)", "1.0V", 0.200, 0.750, 0.95, 1.05,
                  "VCCPINT", "VCCPINT balls"),
            _load("VCCBRAM", "1.0V", 0.020, 0.080, 0.95, 1.05,
                  "VCCBRAM", "VCCBRAM balls"),
            _load("VCCAUX (PL aux)", "1.8V", 0.040, 0.120, 1.71, 1.89,
                  "VCCAUX", "VCCAUX balls"),
            _load("VCCPAUX (PS aux)", "1.8V", 0.030, 0.100, 1.71, 1.89,
                  "VCCPAUX", "VCCPAUX balls"),
            _load("VCCPLL", "1.8V", 0.010, 0.030, 1.71, 1.89,
                  "VCCPLL", "VCCPLL ball"),
            _load("VCCO MIO0 (3.3V IO)", "3.3V", 0.050, 0.150, 3.135, 3.465,
                  "VCCO_MIO0", "bank 500/501"),
            _load("VCCO HR banks 34/35", "3.3V", 0.100, 0.300, 3.135, 3.465,
                  "VCCO_34", "banks 34/35"),
            _load("VCCO DDR (PS DDR IO)", "1.5V (DDR IO)", 0.080, 0.250,
                  1.425, 1.575, "VCCO_DDR", "bank 502"),
        ]),
    DeviceTemplate(
        key="buck_block", name="Buck regulator (block)", category="Regulators",
        description="Step-down converter modelled the recommended way: the "
                    "converter plus its own controller Iq as a separate load "
                    "on the input rail, grouped in one block.",
        rails=["VIN"],
        items=[
            TemplateItem("converter", "Buck converter", "VIN", {
                "topology": "buck", "efficiency_pct": 90.0,
                "vout_min": 3.23, "vout_typ": 3.30, "vout_max": 3.37,
                "limit_type": LimitType.CURRENT, "limit_value": 3.0}),
            _load("Controller Iq", "VIN", 0.0005, 0.001, None, None, "", "VIN pin"),
        ]),
    DeviceTemplate(
        key="ldo_block", name="LDO regulator (block)", category="Regulators",
        description="LDO as a block: pass element (efficiency ≈ Vout/Vin — set "
                    "it accordingly) plus ground-pin Iq load.",
        rails=["VIN"],
        items=[
            TemplateItem("converter", "LDO", "VIN", {
                "topology": "ldo", "efficiency_pct": 60.0,
                "vout_min": 1.78, "vout_typ": 1.80, "vout_max": 1.82,
                "limit_type": LimitType.CURRENT, "limit_value": 1.0}),
            _load("LDO Iq (GND pin)", "VIN", 0.0001, 0.0003, None, None,
                  "", "GND pin"),
        ]),
    DeviceTemplate(
        key="pmic_quad", name="Quad-output PMIC (block pattern)",
        category="Regulators",
        description="Multi-output PMIC modelled the PowerTree way: ONE block "
                    "holding one converter per output rail (sharing the "
                    "refdes) plus the shared quiescent current — budgeting "
                    "is per-rail anyway, so this is electrically exact for "
                    "DC power planning.",
        rails=["VIN"],
        items=[
            TemplateItem("converter", "BUCK1 (core)", "VIN", {
                "topology": "buck", "efficiency_pct": 88.0,
                "signal_name": "PMIC_1V0",
                "vout_min": 0.99, "vout_typ": 1.00, "vout_max": 1.01,
                "limit_type": LimitType.CURRENT, "limit_value": 3.0}),
            TemplateItem("converter", "BUCK2 (io)", "VIN", {
                "topology": "buck", "efficiency_pct": 90.0,
                "signal_name": "PMIC_1V8",
                "vout_min": 1.78, "vout_typ": 1.80, "vout_max": 1.82,
                "limit_type": LimitType.CURRENT, "limit_value": 2.0}),
            TemplateItem("converter", "BUCK3 (periph)", "VIN", {
                "topology": "buck", "efficiency_pct": 90.0,
                "signal_name": "PMIC_3V3",
                "vout_min": 3.27, "vout_typ": 3.30, "vout_max": 3.33,
                "limit_type": LimitType.CURRENT, "limit_value": 2.0}),
            TemplateItem("converter", "LDO1 (analog)", "VIN", {
                "topology": "ldo", "efficiency_pct": 60.0,
                "signal_name": "PMIC_1V2A",
                "vout_min": 1.19, "vout_typ": 1.20, "vout_max": 1.21,
                "limit_type": LimitType.CURRENT, "limit_value": 0.3}),
            _load("PMIC Iq (shared)", "VIN", 0.002, 0.004, None, None,
                  "", "VIN pin"),
        ]),
    DeviceTemplate(
        key="ddr3", name="DDR3L SDRAM (x16, 4Gb)", category="Memory",
        part_number="MT41K256M16",
        description="Single DDR3L device: VDD/VDDQ at 1.35/1.5 V with JEDEC "
                    "window.",
        rails=["1.5V"],
        items=[
            _load("VDD+VDDQ", "1.5V", 0.150, 0.450, 1.425, 1.575,
                  "VDD_DDR", "VDD/VDDQ balls"),
            _load("VREFDQ/CA", "1.5V", 0.001, 0.002, 1.425, 1.575,
                  "VREF_DDR", "VREF balls"),
        ]),
    DeviceTemplate(
        key="eth_phy", name="Gigabit Ethernet PHY", category="Interfaces",
        part_number="KSZ9031RNX",
        description="GigE PHY: 3.3 V analog/IO plus 1.2 V core.",
        rails=["3.3V", "1.2V"],
        items=[
            _load("AVDD/DVDD 3.3V", "3.3V", 0.060, 0.120, 3.135, 3.465,
                  "PHY_3V3", "AVDDH/DVDDH"),
            _load("Core 1.2V", "1.2V", 0.150, 0.300, 1.14, 1.26,
                  "PHY_1V2", "DVDDL/AVDDL"),
        ]),
    DeviceTemplate(
        key="usb_phy", name="USB 2.0 ULPI PHY", category="Interfaces",
        part_number="USB3320",
        description="ULPI PHY: 3.3 V analog + 1.8 V core.",
        rails=["3.3V", "1.8V"],
        items=[
            _load("VDD33", "3.3V", 0.030, 0.060, 3.0, 3.6, "USB_3V3", "VDD33"),
            _load("VDD18", "1.8V", 0.020, 0.050, 1.65, 1.95, "USB_1V8",
                  "VDD18"),
        ]),
    DeviceTemplate(
        key="clockgen", name="Clock generator", category="Timing",
        part_number="Si5341",
        description="Any-frequency clock generator: 3.3 V + 1.8 V cores.",
        rails=["3.3V", "1.8V"],
        items=[
            _load("VDD 3.3V", "3.3V", 0.100, 0.180, 3.135, 3.465,
                  "CLK_3V3", "VDD"),
            _load("VDDA 1.8V", "1.8V", 0.150, 0.250, 1.71, 1.89,
                  "CLK_1V8", "VDDA"),
        ]),
    DeviceTemplate(
        key="qspi_flash", name="QSPI NOR flash", category="Memory",
        part_number="S25FL256S",
        description="Boot flash on the 3.3 V rail.",
        rails=["3.3V"],
        items=[_load("VCC", "3.3V", 0.020, 0.080, 2.7, 3.6, "QSPI_3V3",
                     "VCC")]),
    DeviceTemplate(
        key="sd_card", name="SD card slot", category="Interfaces",
        description="Full-size SD card worst-case draw.",
        rails=["3.3V"],
        items=[_load("SD VDD", "3.3V", 0.100, 0.200, 2.7, 3.6, "SD_3V3",
                     "VDD")]),
]


def _user_template_paths() -> list:
    """Where user-defined template JSON files may live (all optional):
    - POWERTREE_TEMPLATES env var (path to a .json file)
    - %APPDATA%/PowerTree/templates.json
    - ./user_templates.json (working directory / project folder)
    """
    import os
    paths = []
    env = os.environ.get("POWERTREE_TEMPLATES")
    if env:
        paths.append(env)
    appdata = os.environ.get("APPDATA")
    if appdata:
        paths.append(os.path.join(appdata, "PowerTree", "templates.json"))
    paths.append(os.path.join(os.getcwd(), "user_templates.json"))
    return paths


def template_from_dict(entry: dict) -> DeviceTemplate:
    """Build a DeviceTemplate from a JSON template/library-part definition."""
    items = [TemplateItem(i["kind"], i["name"], i["rail"],
                          dict(i.get("params", {})))
             for i in entry["items"]]
    return DeviceTemplate(
        key=entry["key"], name=entry["name"],
        category=entry.get("category", "User"),
        description=entry.get("description", ""),
        rails=list(entry.get("rails", [])),
        items=items,
        part_number=entry.get("part_number", ""),
        datasheet=entry.get("datasheet", ""))


def load_user_templates() -> list:
    """Parse user template JSON files AND the component library into
    DeviceTemplate objects.

    File format: a list of objects with keys key, name, category,
    description, part_number?, datasheet?, rails (list), items (list of
    {kind, name, rail, params?}). Invalid files are skipped with a console
    warning — they must never break the app."""
    import json
    import os
    from .library import library_path, project_library_path
    out = []
    paths = _user_template_paths() + [library_path()]
    if project_library_path():
        paths.append(project_library_path())
    for path in paths:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for entry in data:
                out.append(template_from_dict(entry))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"PowerTree: skipping user templates {path}: {exc}")
    return out


def all_templates() -> list:
    """Built-in templates plus user templates (user keys override
    built-ins)."""
    user = load_user_templates()
    user_keys = {t.key for t in user}
    return [t for t in TEMPLATES if t.key not in user_keys] + user


def template_by_key(key: str) -> DeviceTemplate | None:
    for t in all_templates():
        if t.key == key:
            return t
    return None


def instantiate_template(tree: PowerTree, template: DeviceTemplate,
                         rail_map: dict, block_name: str = "",
                         refdes: str = "") -> list:
    """Create the template's elements in `tree`.

    rail_map: external rail key -> parent element id. Every key in
    template.rails that is actually used by an item must be mapped.
    Returns the created elements (block members).
    """
    block = tree.add_block(block_name or template.name)
    created: dict[str, Element] = {}
    out: list = []
    for item in template.items:
        if item.rail.startswith("@"):
            ref = item.rail[1:]
            parent = created.get(ref)
            if parent is None:
                raise ValueError(f"Template item '{item.name}' references "
                                 f"unknown sibling '{ref}'.")
            parent_id = parent.id
        else:
            parent_id = rail_map.get(item.rail)
            if not parent_id or parent_id not in tree.elements:
                raise ValueError(
                    f"Rail '{item.rail}' is not mapped to an element "
                    f"(needed by '{item.name}').")
        cls = {"converter": Converter, "load": Load,
               "series": SeriesElement}[item.kind]
        el = cls(name=item.name)
        for attr, value in item.params.items():
            setattr(el, attr, value)
        if not el.part_number:
            el.part_number = template.part_number
        if refdes and not el.refdes:
            el.refdes = refdes
        if not el.datasheet:
            el.datasheet = template.datasheet
        tree.add_element(el, parent_id=parent_id)
        el.block_id = block.id
        created[item.name] = el
        out.append(el)
    return out
