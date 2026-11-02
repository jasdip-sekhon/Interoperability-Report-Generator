"""Tests for matching the topology to the measurements.

The two name switches and ports differently, so a mistake here does not fail - it drops
entries off a chart, or lines labels up against the wrong lane. Both are invisible in
the output, which is why the normalisation and the alias are pinned.
"""

import _bootstrap
from x_axis import (_topology_key, build_interconnect_axis, build_port_vendors,
                    build_switch_axis)


def topology(switch, port_lane, label="label"):
    return {"Rx Switch": switch, "Rx Port-Lane": port_lane,
            "FEC-BER / T-Code x-axis label": label}


assert _topology_key(topology("SW0", "1-1")) == ("0", 1, 1),     "the topology writes SW0 where the measurements write 0"
assert _topology_key(topology("4-33", "2-4")) == ("4-33", 2, 4),     "a switch already named without the prefix is left alone"
assert _topology_key(topology("Ixia", "1-1")) == ("Ixia", 1, 1)
print("ok  _topology_key: one key shape, whichever side named it")

keys, labels = build_interconnect_axis([topology("SW0", "1-1", "a"),
                                        topology("SW0", "1-2", "b")])
assert keys == [("0", 1, 1), ("0", 1, 2)]
assert labels == ["a", "b"], "the label is the topology's own column, used verbatim"
print("ok  build_interconnect_axis: keys normalised, labels taken as written")

keys, labels = build_switch_axis([topology("SW0", "1-1"), topology("SW0", "1-2"),
                                  topology("4-33", "1-1")])
assert keys == ["0", "4-33"], "one entry per switch, in the order the topology lists"
assert labels == ["switch 0", "switch 4-33"]
print("ok  build_switch_axis: deduped, topology order kept")

vendors = build_port_vendors([
    dict(topology("SW0", "1-1"), **{"Rx Vendor": "NWB"}),
    dict(topology("SW0", "1-4"), **{"Rx Vendor": "NWB"}),
    dict(topology("SW0", "2-1"), **{"Rx Vendor": "NWS"})])
assert vendors == {("0", 1): "NWB", ("0", 2): "NWS"}, vendors
assert ("0", 9) not in vendors, "a port with no topology entry falls back to 'port N'"
print("ok  build_port_vendors: one optic per port, every lane of it agreeing")

print()
print("all tests passed")
