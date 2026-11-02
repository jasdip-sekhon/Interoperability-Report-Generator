"""The x axis: what the topology says is wired, matched to what the capture measured.

interconnects.yml says 'SW0' and '1-1' where the measurements say '0', 1, 1, so keys are
normalised onto the measurement side. A mismatch only shows as gaps, hence
_report_unmatched.
"""

from pathlib import Path


def _topology_key(record):
    # interconnects.yml: 'SW0', '1-1' -> measurement side's ('0', 1, 1)
    switch = str(record["Rx Switch"])
    if switch.upper().startswith("SW"):
        switch = switch[2:]
    port, _, lane = str(record["Rx Port-Lane"]).partition("-")
    return switch, int(port), int(lane)


def build_interconnect_axis(interconnects):
    keys = []
    labels = []
    for record in interconnects:
        keys.append(_topology_key(record))
        labels.append(record["FEC-BER / T-Code x-axis label"])
    return keys, labels


def build_switch_axis(interconnects):
    keys = []
    for record in interconnects:
        switch, port, lane = _topology_key(record)
        if switch not in keys:
            keys.append(switch)
    labels = []
    for switch in keys:
        labels.append(f"switch {switch}")
    return keys, labels


def _axis_order(key):
    switch, port, lane = key
    return (str(switch), port, lane)


def build_measured_axis(measurements):
    """x axis from what was measured, for a rack with no topology file."""
    keys = []
    for section in ("ber", "tcode", "uncorrected_cw", "link_up"):
        records = measurements.get(section)
        if records is None:
            continue
        for record in records:
            key = (record["switch"], record["port"], record["lane"])
            if key not in keys:
                keys.append(key)
    keys.sort(key=_axis_order)
    labels = []
    for switch, port, lane in keys:
        labels.append(f"{switch} {port}-{lane}")
    return keys, labels


def build_measured_switches(measurements):
    """Switch axis from what was measured, when there is no topology to order it."""
    keys = []
    for section in ("flaps", "temps", "ber"):
        records = measurements.get(section)
        if records is None:
            continue
        for record in records:
            if record["switch"] not in keys:
                keys.append(record["switch"])
    keys.sort(key=str)
    labels = []
    for switch in keys:
        labels.append(f"switch {switch}")
    return keys, labels


def build_port_vendors(interconnects):
    """{(switch, port): vendor} - one optic per port, so every lane of it agrees."""
    vendors = {}
    for record in interconnects:
        switch, port, lane = _topology_key(record)
        vendors[(switch, port)] = record["Rx Vendor"]
    return vendors


def topology_source(path):
    """The workbook this yaml was built from, stamped by the converter."""
    with open(path, encoding="utf-8") as f:
        first = f.readline()
    if first.startswith("# source:"):
        return first[len("# source:"):].strip()
    return "unknown workbook"


def _report_unmatched(keys, values, what):
    missing = 0
    for key in keys:
        if key not in values:
            missing = missing + 1
    if missing:
        print(f"  Warning: {missing} of {len(keys)} interconnects have no {what} "
              f"measurement; they will render as gaps.")
