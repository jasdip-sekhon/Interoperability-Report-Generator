"""Synthetic tests for the capture parsers.

Every collect_* function takes a list of plain dicts rather than a worksheet, so the
logic can be exercised without Excel. That matters most for the grouping: the fixtures
only ever hold one reading per lane, so the case the grouping exists for - many repeats
of the same lane - is never covered by running against references/.
"""

from datetime import datetime

from data_to_yml import (
    collect_ber_from_vdm,
    collect_link_flaps,
    collect_link_up,
    collect_meta_data,
    collect_pre_fec_ber,
    collect_sensors,
    collect_tcode,
    collect_temps,
    collect_uncorrected_cw,
    _norm_switch,
    _parse_temp,
    SENSOR_COLUMN,
    VDM_PREFEC_PREFIX,
)


def lane_row(switch, port, lane, column, value):
    return {"TreeL1": switch, "TreeL2": port, "TreeL3": lane, column: value}


# --- grouping: many readings of one lane collapse into one record ---------------

records = [
    lane_row(0, 1, 1, "FEC_BER", 1e-11),
    lane_row(0, 1, 1, "FEC_BER", 2e-11),
    lane_row(0, 1, 1, "FEC_BER", 3e-11),
    lane_row(0, 1, 2, "FEC_BER", 9e-11),
]
ber = collect_pre_fec_ber(records)
assert len(ber) == 2, f"4 rows over 2 lanes should give 2 records, got {len(ber)}"
lane_1 = [r for r in ber if r["lane"] == 1][0]
assert lane_1["values"] == [1e-11, 2e-11, 3e-11], lane_1["values"]
assert lane_1["switch"] == "0", "switch should be normalised to a string"
print("ok  grouping: 4 rows over 2 lanes -> 2 records, 3 values on the repeated lane")


# --- flap correction: the column reads one high on every row --------------------

flaps = collect_link_flaps([
    lane_row(0, 1, 1, "Down->Up", 0),
    lane_row(0, 1, 1, "Down->Up", 1),
    lane_row(0, 1, 1, "Down->Up", 2),
], test_type="reset")
assert len(flaps) == 1
assert flaps[0]["count"] == 1, f"max(0, raw-1) over [0,1,2] is 1, got {flaps[0]['count']}"
print("ok  flap correction: raw [0,1,2] -> count 1")


# --- never_recovered is the raw value, read before the correction ---------------

stuck = collect_link_flaps([
    lane_row(0, 1, 1, "Down->Up", 0),
    lane_row(0, 1, 1, "Down->Up", 0),
], test_type="reset")
assert stuck[0]["never_recovered"] is True
assert stuck[0]["count"] == 0

healthy = collect_link_flaps([
    lane_row(0, 1, 1, "Down->Up", 0),
    lane_row(0, 1, 1, "Down->Up", 1),
], test_type="reset")
assert healthy[0]["never_recovered"] is False
# both correct to count 0 - without the raw check they would be indistinguishable
assert healthy[0]["count"] == 0
print("ok  never_recovered: raw [0,0] -> True, raw [0,1] -> False, both count 0")


# --- soak commands no recovery, so the question does not apply ------------------

soak = collect_link_flaps([lane_row(0, 1, 1, "Down->Up", 0)], test_type="soak")
assert soak[0]["never_recovered"] is None, "soak should report null, not true"
print("ok  soak: never_recovered is null, not a false alarm")


# --- switch ids arrive as int, float or str in the same column ------------------

assert _norm_switch(0) == "0"
assert _norm_switch(0.0) == "0", "excel can hand back 0.0; '0.0' would join to nothing"
assert _norm_switch("4-33") == "4-33"
assert _norm_switch(" 4-35 ") == "4-35"
assert _norm_switch(None) is None
print("ok  _norm_switch: int, float and str all land on the same string")


# --- temperatures carry a unit suffix with inconsistent spacing -----------------

assert _parse_temp("70 C") == 70.0
assert _parse_temp("72.9141C") == 72.9141
assert _parse_temp(39.8) == 39.8
assert _parse_temp(None) is None
print("ok  _parse_temp: '70 C', '72.9141C' and bare numbers")


# --- VDM is wide: one row holds eight lanes in its columns ----------------------

wide = {"TreeL1": "4-33", "TreeL2": 2}
for lane in range(1, 9):
    wide[VDM_PREFEC_PREFIX + str(lane)] = lane * 1e-12
vdm = collect_ber_from_vdm([wide])
assert len(vdm) == 8, f"one port row should unpivot into 8 lanes, got {len(vdm)}"
assert sorted(r["lane"] for r in vdm) == [1, 2, 3, 4, 5, 6, 7, 8]
assert [r for r in vdm if r["lane"] == 3][0]["values"] == [3e-12]
print("ok  VDM unpivot: 1 port row -> 8 lane records")


# --- T-Code: not every switch has it measured ------------------------------------

tcode = collect_tcode([
    lane_row(0, 1, 1, "tcode2", 0),
    lane_row(0, 1, 1, "tcode2", 1),
    lane_row("4-33", 1, 1, "tcode2", None),
    lane_row("4-33", 1, 1, "tcode2", None),
])
measured = [r for r in tcode if r["switch"] == "0"][0]
unmeasured = [r for r in tcode if r["switch"] == "4-33"][0]
assert measured["values"] == [0, 1]
# the whole point: an unmeasured switch must not read as a measured zero, or it
# reports as passing a spec it never ran
assert unmeasured["values"] == [None, None], unmeasured["values"]
print("ok  collect_tcode: unmeasured switches keep null, never collapse to 0")


# --- uncorrected codewords and link-up times -------------------------------------

uncorr = collect_uncorrected_cw([
    lane_row(0, 1, 1, "UNCORR_CW", 0),
    lane_row(0, 1, 1, "UNCORR_CW", 3),
])
assert uncorr[0]["values"] == [0, 3]
print("ok  collect_uncorrected_cw: readings grouped per lane")

link_up = collect_link_up([
    lane_row("4-36", 1, 1, "LinkUpTime", 16.146865),
    lane_row("4-36", 1, 2, "LinkUpTime", 10.422622),
])
assert len(link_up) == 2
assert link_up[0]["values"] == [16.146865]
print("ok  collect_link_up: seconds per lane")


# --- time series join back to the log on (Repeat, test_step, TreeL1) ------------

timestamps = {
    ("0", "6", "0"): datetime(2026, 8, 16, 3, 0, 0),
    ("1", "6", "0"): datetime(2026, 8, 16, 4, 30, 0),
}
temp_rows = [
    {"Repeat": 0, "test_step": 6, "TreeL1": 0, "TreeL2": 1,
     "ModuleMonitorsModuleMonitorInternalTemperature": "40.0C"},
    {"Repeat": 1, "test_step": 6, "TreeL1": 0, "TreeL2": 1,
     "ModuleMonitorsModuleMonitorInternalTemperature": "42.5C"},
]
temps = collect_temps(temp_rows, timestamps)
assert len(temps) == 1, "both rows are the same module, so one record"
assert temps[0]["points"] == [[0.0, 40.0], [1.5, 42.5]], temps[0]["points"]
print("ok  collect_temps: hours counted from the earliest timestamp, points sorted")

sensor_rows = [
    {"Repeat": 1, "test_step": 6, "TreeL1": 0, SENSOR_COLUMN: 41.2},
    {"Repeat": 0, "test_step": 6, "TreeL1": 0, SENSOR_COLUMN: 39.8},
    # a model without this sensor leaves the column blank
    {"Repeat": 0, "test_step": 6, "TreeL1": "4-33", SENSOR_COLUMN: None},
]
sensors = collect_sensors(sensor_rows, timestamps)
assert len(sensors) == 1, "the switch with no sensor should not appear at all"
assert sensors[0]["switch"] == "0"
assert sensors[0]["points"] == [[0.0, 39.8], [1.5, 41.2]], "points must come out in time order"
print("ok  collect_sensors: blank-sensor switches skipped, points time-ordered")


# --- a mixed rack must not silently pick one spec --------------------------------

mixed = [
    {"TreeL1": 0, "MinModuleTemperature": "0 C", "MaxModuleTemperature": "70 C"},
    {"TreeL1": "4-33", "MinModuleTemperature": "0 C", "MaxModuleTemperature": "75 C"},
]
log = [{"TreeL1": 0, "device_model": "AZ9074", "device_ip": "10.0.0.1",
        "test_start_time": "2026-08-16 03:25:12"}]
meta = collect_meta_data(log, mixed, "soak")
# a rack can mix 70C and 75C optics; one global spec would put the wrong line on one
# of these two charts
assert meta["switches"]["0"]["temp_max"] == 70.0
assert meta["switches"]["4-33"]["temp_max"] == 75.0, \
    "each switch keeps its own rating rather than inheriting the first one seen"
assert meta["switches"]["0"]["temp_min"] == 0.0
assert meta["switches"]["0"]["device_model"] == "AZ9074"
assert "spec" not in meta, "no global spec to disagree with the per-switch ones"
print("ok  collect_meta_data: temperature spec is per switch, not per capture")

# modules on ONE switch disagreeing is still a problem - one chart, one line
print("    (expect a single-switch rating warning on the next line)")
within = [
    {"TreeL1": 0, "MinModuleTemperature": "0 C", "MaxModuleTemperature": "70 C"},
    {"TreeL1": 0, "MinModuleTemperature": "0 C", "MaxModuleTemperature": "75 C"},
]
meta = collect_meta_data(log, within, "soak")
assert meta["switches"]["0"]["temp_max"] == 70.0, "first value kept"
print("ok  collect_meta_data: modules disagreeing within one switch still warn")

print()
print("all tests passed")
