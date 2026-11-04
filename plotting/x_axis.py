"""The x axis: what the topology says is wired, matched to what the capture measured -
keys are normalised onto the measurement side (interconnects.yml's 'SW0'/'1-1' becomes
'0'/1/1), and a mismatch only shows as a gap, hence _report_unmatched."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from console import say, warn, warn_detail                     # noqa: E402


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


MAX_LISTED_UNCHARTED = 5

# the sections identified by (switch, port, lane); temps and sensors key differently
PER_LANE_SECTIONS = ("flaps", "ber", "tcode", "uncorrected_cw", "link_up")


def _name_ports(uncharted):
    """Grouped by port: a whole port missing from the topology is one fact, not eight."""
    ports = {}
    for switch, port, lane in uncharted:
        if (switch, port) not in ports:
            ports[(switch, port)] = []
        ports[(switch, port)].append(lane)

    named = []
    for switch, port in sorted(ports)[:MAX_LISTED_UNCHARTED]:
        found = sorted(ports[(switch, port)])
        if len(found) > 2:
            named.append(f"switch {switch} port {port} ({len(found)} lanes)")
            continue
        lanes = []
        for lane in found:
            lanes.append(str(lane))
        named.append(f"switch {switch} port {port} lane {'/'.join(lanes)}")
    listed = ", ".join(named)
    rest = len(ports) - MAX_LISTED_UNCHARTED
    if rest > 0:
        if rest == 1:
            listed = listed + ", and 1 more port"
        else:
            listed = listed + f", and {rest} more ports"
    return listed


def _uncharted_in(records, axis):
    """Measured lanes the topology does not describe, counted off the records so an
    un-broken-out port is one lane and not also its lane-1 alias."""
    found = []
    for record in records:
        key = (record["switch"], record["port"], record["lane"])
        if key in axis:
            continue
        if record["lane"] == 0 and (record["switch"], record["port"], 1) in axis:
            continue
        found.append(key)
    return found


def report_uncharted_lanes(measurements, keys, names, seen):
    """Once per report, not once per capture, since these lanes are missing from the
    topology file itself; seen is a set this call mutates, shared by every capture in
    the report the same way the axis is."""
    axis = set(keys)
    measured_sections = []
    by_section = {}
    for section in PER_LANE_SECTIONS:
        records = measurements.get(section)
        if not records:
            continue
        measured_sections.append(section)
        found = _uncharted_in(records, axis)
        if found:
            by_section[section] = tuple(sorted(set(found)))

    groups = {}
    for section in by_section:
        signature = by_section[section]
        if signature not in groups:
            groups[signature] = []
        groups[signature].append(section)

    for signature in groups:
        if signature in seen:
            continue
        seen.add(signature)
        sections = groups[signature]
        if len(groups) == 1 and len(sections) == len(measured_sections):
            which = "all metrics"
        else:
            named = []
            for section in sections:
                named.append(names[section])
            which = ", ".join(named)
        warn_detail(f"{len(signature)} measured lanes are absent from the topology "
                    f"({which}), so they appear in no chart:",
                    _name_ports(signature))


def report_link_up_coverage(records, keys, spec):
    """Only the side whose links were taken down reports link-up, so counting gaps
    against the whole rack always fires and would hide a real one. The topology
    filtered to that side is the honest denominator."""
    sides = []
    for record in records:
        if record["switch"] not in sides:
            sides.append(record["switch"])
    sides.sort(key=str)

    measured = set()
    for record in records:
        measured.add((record["switch"], record["port"], record["lane"]))
        if record["lane"] == 0:
            measured.add((record["switch"], record["port"], 1))

    expected = []
    for key in keys:
        if key[0] in sides:
            expected.append(key)

    missing = []
    for key in expected:
        if key not in measured:
            missing.append(key)

    # lanes measured here but absent from the topology are reported once per capture
    # by report_uncharted_lanes, so naming them again on this line only repeats it
    if len(sides) == 1:
        where = f"switch {sides[0]}"
    else:
        where = "switches " + "/".join(sides)

    if missing:
        warn_detail(f"link-up on {where}: {len(expected) - len(missing)} of "
                    f"{len(expected)} topology lanes measured, {len(missing)} missing "
                    f"(against the {spec}s spec):",
                    _name_ports(missing))
        return
    say(f"link-up on {where}: all {len(expected)} topology lanes measured, "
        f"against the {spec}s spec")


def _report_unmatched(keys, values, what):
    """Interconnects the capture never measured, which render as gaps. The other
    direction is reported once per capture by report_uncharted_lanes."""
    missing = 0
    for key in keys:
        if key not in values:
            missing = missing + 1
    if missing:
        warn(f"{missing} of {len(keys)} interconnects have no {what} measurement; "
             f"they will render as gaps")
