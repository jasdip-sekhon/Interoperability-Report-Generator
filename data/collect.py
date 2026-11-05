"""One collector per measurement section. None always means not measured; deciding a
sheet is missing is the caller's job."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from console import warn, warn_detail                          # noqa: E402

from parse import (_elapsed_hours, _group_by_lane, _lanes_to_records, _norm_switch,
                   _parse_temp)

VDM_PREFEC_PREFIX = "VDM_Pre-FEC_BER_Average_Media_Input_Lane_"
SENSOR_COLUMN = "mb_asc5_temp1_Q88_frontrighttop_C"

def _report_stuck_lanes(flap_data):
    stuck = []
    for record in flap_data:
        if record["never_recovered"]:
            stuck.append((record["switch"], record["port"], record["lane"]))
    if not stuck:
        return
    named = []
    for switch, port, lane in stuck:
        named.append(f"switch {switch} port {port} lane {lane}")
    if len(stuck) == 1:
        lane_word = "lane"
    else:
        lane_word = "lanes"
    warn_detail(f"{len(stuck)} {lane_word} went down during this capture and never "
                f"came back up:", ", ".join(named))

def collect_link_flaps(flap_records):
    """Per-lane flap counts, and whether a lane went down and never came back - directly
    from Up->Down and Down->Up, not guessed from outside: a lane with neither column
    ever moving was not part of whatever this test took down, not a failure."""
    down_up = _group_by_lane(flap_records, "Down->Up")
    up_down = _group_by_lane(flap_records, "Up->Down")

    flap_data = []
    for key in down_up:
        switch, port, lane = key
        raw_values = down_up[key]

        # Fixes the "Down->Up" count by subtracting 1 from each value
        count = 0
        for raw in raw_values:
            if raw is None:
                continue
            corrected = max(0, raw - 1)
            if corrected > count:
                count = corrected

        went_down = False
        for raw in up_down.get(key, []):
            if raw is not None and raw > 0:
                went_down = True
        came_back = False
        for raw in raw_values:
            if raw is not None and raw > 0:
                came_back = True
        never_recovered = went_down and not came_back

        flap_data.append({
            "switch": switch,
            "port": port,
            "lane": lane,
            "count": count,
            "never_recovered": never_recovered,
        })
    _report_stuck_lanes(flap_data)
    return flap_data


def collect_pre_fec_ber(ber_records):
    return _lanes_to_records(_group_by_lane(ber_records, "FEC_BER"))


def collect_ber_from_vdm(module_records):
    # has the same structure as collect_pre_fec_ber but uses the VDM columns instead of a single FEC_BER column
    lanes = {}
    for record in module_records:
        switch = _norm_switch(record["TreeL1"])
        port   = record["TreeL2"]
        for lane in range(1, 9):
            column = VDM_PREFEC_PREFIX + str(lane)
            if column not in record:
                continue
            key = (switch, port, lane)
            if key not in lanes:
                lanes[key] = []
            lanes[key].append(record[column])

    return _lanes_to_records(lanes)


def collect_tcode(fec_records):
    # only some switches have this measured; a None here means "not measured" and must
    # not become a 0 — that would report a switch as passing a spec it never ran
    return _lanes_to_records(_group_by_lane(fec_records, "tcode2"))


def collect_uncorrected_cw(fec_records):
    return _lanes_to_records(_group_by_lane(fec_records, "UNCORR_CW"))


def collect_link_up(reset_records):
    # seconds from admin-up to link-up, per lane
    return _lanes_to_records(_group_by_lane(reset_records, "LinkUpTime"))


def collect_temps(module_records, timestamps):
    # one optic per PORT, so there is no lane here — all 8 lanes share this reading
    start = _elapsed_hours(timestamps)
    modules = {}
    unmatched = 0
    for record in module_records:
        switch = _norm_switch(record["TreeL1"])
        port   = record["TreeL2"]
        key = (str(record["Repeat"]), str(record["test_step"]), str(switch))
        when = timestamps.get(key)
        if when is None or start is None:
            unmatched = unmatched + 1
            continue

        hours = (when - start).total_seconds() / 3600.0
        temp = _parse_temp(record["ModuleMonitorsModuleMonitorInternalTemperature"])

        module_key = (switch, port)
        if module_key not in modules:
            modules[module_key] = []
        modules[module_key].append([round(hours, 4), temp])

    if unmatched:
        if unmatched == 1:
            reading_word = "reading was"
        else:
            reading_word = "readings were"
        warn(f"{unmatched} module temperature {reading_word} dropped, having no "
             f"matching log timestamp")

    temp_data = []
    for module_key in modules:
        switch, port = module_key
        # a value-coloured line is drawn segment by segment, so order matters
        points = sorted(modules[module_key])
        temp_data.append({
            "switch": switch,
            "port": port,
            "points": points,
        })
    return temp_data


def collect_sensors(sensor_records, timestamps):
    # one reading per switch, not per port — this is a sensor on the switch board
    start = _elapsed_hours(timestamps)
    switches = {}
    unmatched = 0
    for record in sensor_records:
        switch = _norm_switch(record["TreeL1"])
        value = record[SENSOR_COLUMN]
        # only some switch models carry this sensor; on the rest the column is blank
        if value is None:
            continue
        key = (str(record["Repeat"]), str(record["test_step"]), str(switch))
        when = timestamps.get(key)
        if when is None or start is None:
            unmatched = unmatched + 1
            continue

        hours = (when - start).total_seconds() / 3600.0
        if switch not in switches:
            switches[switch] = []
        switches[switch].append([round(hours, 4), float(value)])

    if unmatched:
        if unmatched == 1:
            reading_word = "reading was"
        else:
            reading_word = "readings were"
        warn(f"{unmatched} sensor {reading_word} dropped, having no matching log "
             f"timestamp")

    sensor_data = []
    for switch in switches:
        sensor_data.append({
            "switch": switch,
            "name": SENSOR_COLUMN,
            "points": sorted(switches[switch]),
        })
    return sensor_data
