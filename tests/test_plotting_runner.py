"""Tests for turning the two yaml files into what plotting.py wants.

This is where the topology side and the measurement side are reconciled. They name
switches and ports differently, so a mistake here silently drops entries off a chart
rather than failing - which is the failure mode worth pinning down.
"""

import _bootstrap
from plotting_runner import (
    SATURATED_BER,
    _break_at_seams,
    _totals_per_switch,
    _lane_scalars,
    _lane_values,
    _sensor_points,
    _temps_per_port,
    _topology_key,
    build_interconnect_axis,
    build_switch_axis,
)


def topology(switch, port_lane, label="label"):
    return {"Rx Switch": switch, "Rx Port-Lane": port_lane,
            "FEC-BER / T-Code x-axis label": label}


def lane(switch, port, lane_no, values):
    return {"switch": switch, "port": port, "lane": lane_no, "values": values}


# --- the two files spell the same interconnect differently -----------------------

assert _topology_key(topology("SW0", "1-1")) == ("0", 1, 1), \
    "interconnects.yml says SW0 and '1-1'; a capture says '0', 1, 1"
assert _topology_key(topology("4-33", "12-4")) == ("4-33", 12, 4), \
    "a switch id that is not SW-prefixed passes through unchanged"
assert _topology_key(topology("sw0", "2-1")) == ("0", 2, 1), "prefix match is case-insensitive"
print("ok  _topology_key: 'SW0' + '1-1' -> ('0', 1, 1)")

keys, labels = build_interconnect_axis([topology("SW0", "1-1", "a"),
                                          topology("4-33", "2-1", "b")])
assert keys == [("0", 1, 1), ("4-33", 2, 1)]
assert labels == ["a", "b"], "labels keep the topology's own wording and order"
switch_keys, switch_labels = build_switch_axis([topology("SW0", "1-1"),
                                                  topology("SW0", "1-2"),
                                                  topology("4-33", "2-1")])
assert switch_keys == ["0", "4-33"], "switches dedupe in first-seen order"
assert switch_labels == ["switch 0", "switch 4-33"]
print("ok  x axis: interconnect keys normalised, switch keys deduped")


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


# --- a measurement with no topology entry must not be silently charted -----------

values = _lane_values([lane("0", 99, 1, [1e-11])])
keys, _ = build_interconnect_axis([topology("SW0", "1-1")])
missing = [key for key in keys if key not in values]
assert missing == [("0", 1, 1)], \
    "an interconnect with no measurement is reported, not quietly dropped"
print("ok  interconnects without measurements are detectable (they render as gaps)")

print()
print("all tests passed")
