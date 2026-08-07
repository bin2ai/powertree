"""Builds a realistic demo project — used by tests, first-run experience and docs."""

from __future__ import annotations

from .model.elements import (
    Project, Source, Converter, Load, SeriesElement, LimitType, LoadType,
)


def build_sample_project() -> Project:
    project = Project("Demo Board")
    project.description = "Example power distribution for a small embedded board."
    project.author = "PowerTree"

    # ---- Tree 1: 12 V main input -------------------------------------------
    tree = project.new_tree("Main 12V Rail")
    tree.description = "12 V barrel-jack input feeding 5 V / 3.3 V / 1.8 V rails."

    src = tree.add_element(Source(
        name="12V DC Input", signal_name="VIN_12V", refdes="J1", pins="1 (VIN), 2 (GND)",
        v_min=11.4, v_typ=12.0, v_max=12.6,
        limit_type=LimitType.CURRENT, limit_value=2.0,
        description="Wall adapter, 24 W max."))

    fuse = tree.add_element(SeriesElement(
        name="Input Fuse + Trace", signal_name="VIN_12V_F", refdes="F1",
        resistance_ohm=0.050), parent_id=src.id)

    buck5 = tree.add_element(Converter(
        name="5V Buck", signal_name="VCC_5V0", refdes="U1", part_number="TPS54331",
        topology="buck", efficiency_pct=92.0,
        vout_min=4.9, vout_typ=5.0, vout_max=5.1,
        limit_type=LimitType.CURRENT, limit_value=3.0,
        quiescent_ma=1.5), parent_id=fuse.id)

    buck33 = tree.add_element(Converter(
        name="3.3V Buck", signal_name="VCC_3V3", refdes="U2", part_number="TPS62130",
        topology="buck", efficiency_pct=90.0,
        vout_min=3.23, vout_typ=3.30, vout_max=3.37,
        limit_type=LimitType.CURRENT, limit_value=1.0,
        quiescent_ma=0.5), parent_id=buck5.id)

    ldo18 = tree.add_element(Converter(
        name="1.8V LDO", signal_name="VCC_1V8", refdes="U3", part_number="TLV75718",
        topology="ldo", efficiency_pct=54.5,
        vout_min=1.75, vout_typ=1.80, vout_max=1.85,
        quiescent_ma=0.05), parent_id=buck33.id)

    # MCU block with several loads on the 3.3 V rail
    mcu_block = tree.add_block("MCU (STM32H7)")
    icc = tree.add_element(Load(
        name="MCU Icc (run)", signal_name="VDD", refdes="U10", pins="VDD 1-8",
        load_type=LoadType.CURRENT, value_typ=0.120, value_max=0.180,
        v_in_min=3.0, v_in_max=3.6), parent_id=buck33.id)
    iq = tree.add_element(Load(
        name="MCU analog Iq", signal_name="VDDA", refdes="U10", pins="VDDA",
        load_type=LoadType.CURRENT, value_typ=0.002,
        v_in_min=3.0, v_in_max=3.6), parent_id=buck33.id)
    icc.block_id = mcu_block.id
    iq.block_id = mcu_block.id

    core = tree.add_element(Load(
        name="MCU core 1V8", signal_name="VCORE", refdes="U10", pins="VCAP",
        load_type=LoadType.CURRENT, value_typ=0.040, value_max=0.060,
        v_in_min=1.71, v_in_max=1.89), parent_id=ldo18.id)
    core.block_id = mcu_block.id

    # 5 V direct loads
    usb_block = tree.add_block("USB / Peripherals")
    usb = tree.add_element(Load(
        name="USB Host Port", signal_name="VBUS_OUT", refdes="J2", pins="1 (VBUS)",
        load_type=LoadType.CURRENT, value_typ=0.250, value_max=0.500,
        v_in_min=4.75, v_in_max=5.25), parent_id=buck5.id)
    usb.block_id = usb_block.id
    heater = tree.add_element(Load(
        name="Sensor Heater", signal_name="HTR_5V", refdes="R45",
        load_type=LoadType.POWER, value_typ=0.75, value_max=1.2,
        v_in_min=4.5, v_in_max=5.5), parent_id=buck5.id)
    heater.block_id = usb_block.id

    # ---- Tree 2: battery backup rail ---------------------------------------
    t2 = project.new_tree("Battery Backup")
    t2.description = "Coin-cell keeps the RTC alive when main power is off."
    bat = t2.add_element(Source(
        name="CR2032 Coin Cell", signal_name="VBAT", refdes="BT1",
        v_min=2.0, v_typ=3.0, v_max=3.3,
        limit_type=LimitType.CURRENT, limit_value=0.010))
    rser = t2.add_element(SeriesElement(
        name="Battery ESR + Diode", refdes="D1", resistance_ohm=15.0),
        parent_id=bat.id)
    t2.add_element(Load(
        name="RTC Backup", signal_name="VBAT_RTC", refdes="U10", pins="VBAT",
        load_type=LoadType.CURRENT, value_typ=0.0000015, value_max=0.000003,
        v_in_min=1.65, v_in_max=3.6), parent_id=rser.id)

    # ---- Notes vault --------------------------------------------------------
    root = project.add_note("Power Budget Sources")
    root.body_md = (
        "# Power budget references\n\n"
        "This vault collects **where every number came from** so the tree is auditable.\n\n"
        "- Wall adapter rating: label on unit, 12 V / 2 A\n"
        "- Regulator efficiencies: vendor datasheets (see child notes)\n")
    n1 = project.add_note("TPS54331 (5V Buck)", parent_id=root.id)
    n1.body_md = ("## TPS54331 efficiency\n\nDatasheet Fig. 7: ~92 % at 12 Vin / 5 Vout / 1 A.\n\n"
                  "| Vin | Iout | Eff |\n|---|---|---|\n| 12 V | 0.5 A | 90 % |\n| 12 V | 1 A | 92 % |\n")
    n1.linked_element_ids.append(buck5.id)
    n2 = project.add_note("MCU current draw", parent_id=root.id)
    n2.body_md = ("## STM32H7 Icc\n\nDS: run mode @ 480 MHz, all peripherals: 120 mA typ, "
                  "180 mA max (85 °C).\n")
    n2.linked_element_ids += [icc.id, iq.id]

    return project
