"""Builds the demo project: a realistic Zynq-7000 carrier board power tree.

12 V input → fuse → ferrite → 5 V buck, fanning into 3.3 / 1.8 / 1.5 / 1.0 V
regulator blocks (each modelled as converter + its own Iq load), through
per-rail ferrite beads into a Zynq XC7Z020 block, DDR3, PHYs, clocking and
storage — all built from the device template library.

The demo deliberately contains findings so margin flagging is visible:
  - FB3 (1.5 Ω bead on the clock 1.8 V rail) causes a real undervoltage
    VIOLATION at the clock generator VDDA,
  - the 1.0 V core buck runs at >90 % of its current limit (LOW MARGIN).
"""

from __future__ import annotations

from .model.elements import (
    Project, Source, Converter, Load, SeriesElement, SeriesType,
    LimitType, LoadType,
)
from .templates import template_by_key, instantiate_template


def build_sample_project() -> Project:
    project = Project("Zynq Carrier Demo")
    project.description = ("Reference power distribution for a Zynq-7000 "
                           "(XC7Z020) carrier board with DDR3, GigE, USB, "
                           "clocking and storage.")
    project.author = "PowerTree"

    tree = project.new_tree("Zynq Carrier 12V")
    tree.description = ("12 V brick through input protection into a 5 V "
                        "intermediate bus, then point-of-load regulators "
                        "for every Zynq / peripheral rail.")

    # ---- input stage -------------------------------------------------------
    src = tree.add_element(Source(
        name="12V DC Input", signal_name="VIN_12V", refdes="J1",
        pins="1 (VIN), 2 (GND)", v_min=11.4, v_typ=12.0, v_max=12.6,
        limit_type=LimitType.POWER, limit_value=24.0,
        description="External 12 V / 2 A AC-DC brick."))

    prot = tree.add_block("Input Protection")
    fuse = tree.add_element(SeriesElement(
        name="Input Fuse", signal_name="VIN_12V_F", refdes="F1",
        series_type=SeriesType.FUSE, resistance_ohm=0.030, rating="2 A slow",
        description="Littelfuse 0451002; cold resistance."),
        parent_id=src.id)
    fb_in = tree.add_element(SeriesElement(
        name="Input Bead", signal_name="VIN_FLT", refdes="FB1",
        series_type=SeriesType.FERRITE_BEAD, resistance_ohm=0.020,
        inductance_uh=1.0, rating="120R@100MHz / 4A",
        description="Murata BLM31 series, DCR 20 mΩ."),
        parent_id=fuse.id)
    fuse.block_id = prot.id
    fb_in.block_id = prot.id

    # ---- 5 V intermediate bus ---------------------------------------------
    bulk5 = instantiate_template(
        tree, template_by_key("buck_block"), {"VIN": fb_in.id},
        block_name="5V Intermediate Bus (U10)", refdes="U10")
    buck5 = next(e for e in bulk5 if isinstance(e, Converter))
    buck5.name = "5V Buck"
    buck5.part_number = "TPS54560"
    buck5.signal_name = "VCC_5V0"
    buck5.vout_min, buck5.vout_typ, buck5.vout_max = 4.95, 5.0, 5.05
    buck5.efficiency_pct = 93.0
    buck5.limit_type, buck5.limit_value = LimitType.CURRENT, 5.0
    buck5.quiescent_ma = 0.0

    def pol_buck(name, refdes, part, signal, vmin, vtyp, vmax, eff, ilim):
        created = instantiate_template(
            tree, template_by_key("buck_block"), {"VIN": buck5.id},
            block_name=f"{name} (${refdes})".replace("$", ""), refdes=refdes)
        conv = next(e for e in created if isinstance(e, Converter))
        conv.name = name
        conv.part_number = part
        conv.signal_name = signal
        conv.vout_min, conv.vout_typ, conv.vout_max = vmin, vtyp, vmax
        conv.efficiency_pct = eff
        conv.limit_type, conv.limit_value = LimitType.CURRENT, ilim
        return conv

    buck33 = pol_buck("3.3V Buck", "U11", "TPS62130", "VCC_3V3",
                      3.267, 3.30, 3.333, 90.0, 3.0)
    buck18 = pol_buck("1.8V Buck", "U12", "TPS62130", "VCC_1V8",
                      1.782, 1.80, 1.818, 88.0, 2.0)
    # deliberately tight limit -> LOW MARGIN showcase on the core rail
    buck10 = pol_buck("1.0V Core Buck", "U13", "TPS62085", "VCC_1V0",
                      0.99, 1.00, 1.01, 87.0, 2.2)
    buck15 = pol_buck("1.5V DDR Buck", "U14", "TPS62130", "VCC_1V5",
                      1.485, 1.50, 1.515, 88.0, 3.0)

    # 1.2 V PHY core from the 1.8 V rail (LDO block, eff ≈ Vout/Vin)
    ldo12_items = instantiate_template(
        tree, template_by_key("ldo_block"), {"VIN": buck18.id},
        block_name="1.2V PHY LDO (U15)", refdes="U15")
    ldo12 = next(e for e in ldo12_items if isinstance(e, Converter))
    ldo12.name = "1.2V LDO"
    ldo12.part_number = "TLV75712"
    ldo12.signal_name = "VCC_1V2"
    ldo12.vout_min, ldo12.vout_typ, ldo12.vout_max = 1.188, 1.20, 1.212
    ldo12.efficiency_pct = 66.7
    ldo12.limit_type, ldo12.limit_value = LimitType.CURRENT, 0.5

    # ---- per-rail ferrites into the SoC core ------------------------------
    fb_core = tree.add_element(SeriesElement(
        name="VCCINT Bead", signal_name="VCCINT_FLT", refdes="FB2",
        series_type=SeriesType.FERRITE_BEAD, resistance_ohm=0.010,
        inductance_uh=0.6, rating="60R@100MHz / 6A",
        description="Low-DCR bead for the core rail."),
        parent_id=buck10.id)

    # deliberately too-resistive bead -> VIOLATION showcase at the clock gen
    fb_clk = tree.add_element(SeriesElement(
        name="Clock 1V8 Bead", signal_name="CLK_1V8_FLT", refdes="FB3",
        series_type=SeriesType.FERRITE_BEAD, resistance_ohm=1.5,
        inductance_uh=2.2, rating="1kR@100MHz / 0.3A",
        description="WRONG PART: 1.5 Ω DCR bead drops the rail below the "
                    "clock generator's minimum — visible finding."),
        parent_id=buck18.id)

    # ---- devices from templates -------------------------------------------
    instantiate_template(tree, template_by_key("zynq7020"), {
        "1.0V": fb_core.id, "1.8V": buck18.id, "3.3V": buck33.id,
        "1.5V (DDR IO)": buck15.id},
        block_name="Zynq XC7Z020 (U1)", refdes="U1")
    instantiate_template(tree, template_by_key("ddr3"), {"1.5V": buck15.id},
                         block_name="DDR3L x16 #1 (U2)", refdes="U2")
    instantiate_template(tree, template_by_key("ddr3"), {"1.5V": buck15.id},
                         block_name="DDR3L x16 #2 (U3)", refdes="U3")
    instantiate_template(tree, template_by_key("eth_phy"), {
        "3.3V": buck33.id, "1.2V": ldo12.id},
        block_name="GigE PHY (U4)", refdes="U4")
    instantiate_template(tree, template_by_key("usb_phy"), {
        "3.3V": buck33.id, "1.8V": buck18.id},
        block_name="USB PHY (U5)", refdes="U5")
    clk_items = instantiate_template(tree, template_by_key("clockgen"), {
        "3.3V": buck33.id, "1.8V": fb_clk.id},
        block_name="Clock Gen (U6)", refdes="U6")
    instantiate_template(tree, template_by_key("qspi_flash"),
                         {"3.3V": buck33.id},
                         block_name="QSPI Flash (U7)", refdes="U7")
    instantiate_template(tree, template_by_key("sd_card"), {"3.3V": buck33.id},
                         block_name="SD Card (J2)", refdes="J2")

    # ---- second tree: battery backup --------------------------------------
    t2 = project.new_tree("Battery Backup")
    t2.description = "Coin-cell keeps the Zynq RTC domain alive."
    bat = t2.add_element(Source(
        name="CR2032 Coin Cell", signal_name="VBAT", refdes="BT1",
        v_min=2.0, v_typ=3.0, v_max=3.3,
        limit_type=LimitType.CURRENT, limit_value=0.010))
    rser = t2.add_element(SeriesElement(
        name="Battery ESR + Diode", refdes="D1", signal_name="VBAT_RTC",
        series_type=SeriesType.RESISTOR, resistance_ohm=15.0),
        parent_id=bat.id)
    t2.add_element(Load(
        name="RTC Backup", signal_name="VBAT_RTC_LD", refdes="U1", pins="VBAT",
        load_type=LoadType.CURRENT, value_typ=0.0000015, value_max=0.000003,
        v_in_min=1.65, v_in_max=3.6), parent_id=rser.id)

    # ---- notes vault -------------------------------------------------------
    root = project.add_note("Power Budget Sources")
    root.body_md = (
        "# Power budget references\n\n"
        "Every number in the tree traces back to a note here so the budget "
        "is **auditable**.\n\n"
        "- Input brick: label rating 12 V / 2 A (24 W)\n"
        "- Zynq rails: Xilinx DS191 operating ranges, DS187 typical currents\n"
        "- Regulator efficiencies: vendor datasheet curves at our operating "
        "point\n")
    n_zynq = project.add_note("Zynq XC7Z020 rails (DS191)", parent_id=root.id)
    n_zynq.body_md = (
        "## Operating windows used\n\n"
        "| Rail | Min | Typ | Max |\n|---|---|---|---|\n"
        "| VCCINT/VCCPINT/VCCBRAM | 0.95 | 1.00 | 1.05 |\n"
        "| VCCAUX/VCCPAUX/VCCPLL | 1.71 | 1.80 | 1.89 |\n"
        "| VCCO 3.3 V banks | 3.135 | 3.30 | 3.465 |\n"
        "| VCCO DDR 1.5 V | 1.425 | 1.50 | 1.575 |\n\n"
        "Currents are placeholder XPE-style estimates — replace with your "
        "design's Xilinx Power Estimator output.\n")
    zynq_block = next(b for b in tree.blocks.values() if "Zynq" in b.name)
    for el in tree.block_members(zynq_block.id):
        n_zynq.linked_element_ids.append(el.id)
    n_fb = project.add_note("Ferrite bead selection", parent_id=root.id)
    n_fb.body_md = (
        "## Bead DCR discipline\n\n"
        "Bead DCR × worst-case rail current must stay well inside every "
        "downstream device's minimum input voltage.\n\n"
        "- FB2 (core rail): 10 mΩ · 2 A = 20 mV drop — fine.\n"
        "- **FB3 (clock 1V8): 1.5 Ω is the WRONG part** — at ~150 mA it "
        "drops ≈225 mV and violates the Si5341 1.71 V minimum. The tree "
        "flags this as a violation on purpose; swap for a ≤50 mΩ bead.\n")
    n_fb.linked_element_ids += [fb_in.id, fb_core.id, fb_clk.id]
    for el in clk_items:
        n_fb.linked_element_ids.append(el.id)
    n_reg = project.add_note("Regulator modelling", parent_id=root.id)
    n_reg.body_md = (
        "## Regulators as blocks\n\n"
        "Each regulator is a block holding the converter **and** its own "
        "controller Iq as a separate input-rail load, so self-consumption "
        "is budgeted explicitly.\n\n"
        "The 1.0 V core buck (U13) intentionally runs above 90 % of its "
        "2.2 A limit to demonstrate low-margin flagging — pick the 4 A "
        "variant for real designs.\n")
    n_reg.linked_element_ids += [buck5.id, buck33.id, buck18.id, buck10.id,
                                 buck15.id, ldo12.id]
    return project
