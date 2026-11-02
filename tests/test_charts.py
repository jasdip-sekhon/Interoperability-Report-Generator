"""Tests for reshaping measurement records into what plotting.py wants.

This is where the topology side and the measurement side are reconciled. They name
switches and ports differently, so a mistake here silently drops entries off a chart
rather than failing - which is the failure mode worth pinning down.
"""

import _bootstrap
from x_axis import build_interconnect_axis
from charts import (
    SATURATED_BER,
    _break_at_seams,
    _totals_per_switch,
    _lane_scalars,
    _lane_values,
    _sensor_points,
    _temp_readings_per_port,
    _temps_per_port,
)


def topology(switch, port_lane, label="label"):
    return {"Rx Switch": switch, "Rx Port-Lane": port_lane,
            "FEC-BER / T-Code x-axis label": label}


def lane(switch, port, lane_no, values):
    return {"switch": switch, "port": port, "lane": lane_no, "values": values}


# --- a port that is not broken out reports lane 0, the topology calls it lane 1 ---

values = _lane_values([lane("0", 3, 0, [1e-11])])
assert ("0", 3, 0) in values, "the measurement's own key still works"
assert ("0", 3, 1) in values, \
    "without the lane-1 alias every un-broken-out port loses its label and vanishes"
assert values[("0", 3, 0)] == values[("0", 3, 1)]
print("ok  lane 0 is indexed under lane 1 too, so single-lane ports keep their label")


# --- saturated readings are dropped at plot time, not at ingest ------------------

print("    (expect a saturation notice on the next line)")
values = _lane_values([lane("0", 1, 1, [1e-11, 0.5, 1.0, 2e-11, None])],
                      drop_at_or_above=SATURATED_BER)
assert values[("0", 1, 1)] == [1e-11, 2e-11], values[("0", 1, 1)]
# without a threshold nothing is dropped - the other metrics are not error rates
keep = _lane_values([lane("0", 1, 1, [0.5, 1.0])])
assert keep[("0", 1, 1)] == [0.5, 1.0], "only BER saturates; tcode and link_up do not"
print("ok  saturation filter: >= 0.5 dropped for BER, left alone otherwise")


# --- some metrics are one number per lane, not a list of readings ----------------

scalars = _lane_scalars([
    {"switch": "0", "port": 1, "lane": 1, "count": 0, "never_recovered": False},
    {"switch": "0", "port": 6, "lane": 1, "count": 2, "never_recovered": False},
], "count")
assert scalars[("0", 1, 1)] == 0, "a measured zero is a value, not an absence"
assert scalars[("0", 6, 1)] == 2
# a flap count is a total, so there is nothing to box or scatter - it stays a number
assert not isinstance(scalars[("0", 6, 1)], list)
print("ok  _lane_scalars: one number per lane, zero kept as a value")

aliased = _lane_scalars([{"switch": "0", "port": 3, "lane": 0, "count": 1}], "count")
assert aliased[("0", 3, 0)] == 1 and aliased[("0", 3, 1)] == 1, \
    "the lane-0 alias applies here too, or un-broken-out ports lose their label"
print("ok  _lane_scalars: lane 0 aliased to lane 1 like the values path")


# --- flaps are stored per lane and charted per switch ----------------------------

totals = _totals_per_switch([
    {"switch": "0", "port": 1, "lane": 1, "count": 2},
    {"switch": "0", "port": 1, "lane": 2, "count": 3},
    {"switch": "4-33", "port": 1, "lane": 1, "count": 0},
])
assert totals == {"0": 5, "4-33": 0}, totals
print("ok  _totals_per_switch: lane counts sum onto their switch")


# --- nothing was measured across a seam, so no line may span it ------------------

points = [(0.0, 40.0), (1.0, 41.0), (24.0, 55.0), (25.0, 56.0)]
assert _break_at_seams(points, []) == points, "an unmerged capture is untouched"

broken = _break_at_seams(points, [24.0])
gaps = [i for i, (hours, _) in enumerate(broken) if hours != hours]
assert len(gaps) == 1 and gaps[0] == 2, broken
assert broken[1] == (1.0, 41.0) and broken[3] == (24.0, 55.0), \
    "the real points keep their real times; only a gap is inserted between them"
print("ok  _break_at_seams: a NaN splits the runs, real timestamps unchanged")

records = [{"switch": "0", "port": 1, "points": [[0.0, 40.0], [24.0, 55.0]]}]
series = _temps_per_port(records, "0", [24.0])
assert len(series[1]) == 3, "two samples plus the gap between them"
sensors = _sensor_points([{"switch": "0", "points": [[0.0, 20.0], [24.0, 30.0]]}],
                         "0", [24.0])
assert len(sensors) == 3, "the sensor line breaks at the seam too"
assert _sensor_points([], "0", []) is None, "a switch with no sensor has no line"
print("ok  temps and sensors both break at the seam")

# the box plot reads the same records but must not see the seam NaNs - one NaN makes
# every quartile of a box NaN, so it reshapes from the raw points instead.
readings = _temp_readings_per_port(records, "0")
assert readings == {1: [40.0, 55.0]}, readings
for value in readings[1]:
    assert value == value, "a reading that is NaN would poison the whole box"
assert _temp_readings_per_port(None, "0") == {}, "a capture with no temps draws nothing"
assert _temp_readings_per_port(records, "9") == {}, "another switch's ports are not mixed in"
print("ok  _temp_readings_per_port: timestamps dropped, no seam NaNs, one switch only")

# --- a measurement with no topology entry must not be silently charted -----------

values = _lane_values([lane("0", 99, 1, [1e-11])])
keys, _ = build_interconnect_axis([topology("SW0", "1-1")])
missing = [key for key in keys if key not in values]
assert missing == [("0", 1, 1)], \
    "an interconnect with no measurement is reported, not quietly dropped"
print("ok  interconnects without measurements are detectable (they render as gaps)")


# --- every draw_* is actually called, and writes what its manifest entry claims ------
#
# The reshaping above is covered thoroughly, but nothing here used to call a draw_*.
# Dropping an import from charts.py once left this file green while python main.py died
# on the first chart, so each family is now exercised end to end against a real render.

import os
import shutil
import tempfile

from charts import (draw_ber, draw_flaps_by_interconnect, draw_flaps_by_switch,
                    draw_link_up, draw_tcode, draw_temperature_over_time,
                    draw_temperature_per_port)

out_dir = tempfile.mkdtemp()
keys = [("0", 1, 1), ("0", 1, 2)]
axis_labels = ["1-1-Tx-A ==> 1-1-Rx-B", "1-2-Tx-A ==> 1-2-Rx-B"]
meta = {"test_type": "reset", "ber_source": "fec_counter",
        "switches": {"0": {"device_model": "SW-1", "device_ip": "10.0.0.1",
                           "temp_min": 0.0, "temp_max": 70.0}}}
measurements = {
    "flaps": [{"switch": "0", "port": 1, "lane": 1, "count": 2, "never_recovered": False},
              {"switch": "0", "port": 1, "lane": 2, "count": 0, "never_recovered": False}],
    "ber": [lane("0", 1, 1, [1e-11, 2e-11]), lane("0", 1, 2, [3e-11])],
    "tcode": [lane("0", 1, 1, [1, 2]), lane("0", 1, 2, [0])],
    "link_up": [lane("0", 1, 1, [4.0, 5.0]), lane("0", 1, 2, [6.0])],
    "temps": [{"switch": "0", "port": 1, "points": [[0.0, 40.0], [1.0, 44.0]]}],
    "sensors": [{"switch": "0", "points": [[0.0, 20.0], [1.0, 22.0]]}],
}

drawn = []
drawn.extend(draw_flaps_by_switch(measurements, ["0"], ["switch 0"], out_dir))
drawn.extend(draw_flaps_by_interconnect(measurements, meta, keys, axis_labels, out_dir))
drawn.extend(draw_ber(measurements, meta, keys, axis_labels, out_dir))
drawn.extend(draw_tcode(measurements, meta, keys, axis_labels, out_dir))
drawn.extend(draw_link_up(measurements, meta, keys, axis_labels, out_dir))
drawn.extend(draw_temperature_over_time(measurements, meta, ["0"], [], out_dir))
drawn.extend(draw_temperature_per_port(measurements, meta, ["0"], {}, out_dir))

assert len(drawn) == 7, f"one chart per family, got {len(drawn)}"
for entry in drawn:
    for field in ("file", "title", "scope", "metric"):
        assert entry.get(field), f"{entry.get('file')} has no {field}"
    path = os.path.join(out_dir, entry["file"])
    assert os.path.exists(path), f"{entry['file']} is in the manifest but was not written"
    assert os.path.getsize(path) > 1000, f"{entry['file']} is too small to be a chart"
metrics = []
for entry in drawn:
    metrics.append(entry["metric"])
assert len(set(metrics)) == 7, f"each family declares its own metric: {metrics}"
print(f"ok  every draw_* renders and declares what it wrote ({len(drawn)} families)")

# a capture missing a section charts nothing rather than failing
empty = dict(measurements)
for section in ("flaps", "ber", "tcode", "link_up", "temps", "sensors"):
    empty[section] = None
assert draw_ber(empty, meta, keys, axis_labels, out_dir) == []
assert draw_flaps_by_switch(empty, ["0"], ["switch 0"], out_dir) == []
assert draw_temperature_over_time(empty, meta, ["0"], [], out_dir) == []
print("ok  a missing section draws nothing instead of raising")

shutil.rmtree(out_dir, ignore_errors=True)

print()
print("all tests passed")
