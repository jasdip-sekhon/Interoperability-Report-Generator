"""Tests for joining two runs of one testcase.

The merge rules differ per field and one of them is the opposite of a union, so every
rule gets an assertion. Output looks plausible whichever way the never_recovered rule
goes; only the count distinguishes them, which is exactly why it is pinned here.
"""

import os
import tempfile

import yaml

from merge_runs import (
    MAX_LISTED_CONFLICTS,
    merge_flaps,
    merge_meta,
    merge_points,
    merge_runs,
    merge_values,
    _start_offsets,
)


def lane(switch, port, lane_no, **fields):
    record = {"switch": switch, "port": port, "lane": lane_no}
    record.update(fields)
    return record


def run(start="2026-07-17 01:05:24", test_type="reset", ber_source="vdm", **sections):
    base = {
        "meta": {
            "test_type": test_type,
            "start_time": start,
            "ber_source": ber_source,
            "switches": {"0": {"device_model": "AZ9074", "device_ip": "10.0.0.1",
                               "temp_min": 0.0, "temp_max": 70.0}},
        },
        "flaps": [], "ber": [], "tcode": None,
        "uncorrected_cw": None, "link_up": [], "temps": [], "sensors": [],
    }
    base.update(sections)
    return base


# --- never_recovered intersects: the rule a union would get backwards -------------

dut = run(flaps=[
    lane("0", 1, 1, count=0, never_recovered=True),    # stuck here
    lane("0", 1, 2, count=0, never_recovered=True),    # stuck here, not in ref
])
ref = run(flaps=[
    lane("0", 1, 1, count=0, never_recovered=True),    # stuck in BOTH
    lane("0", 1, 2, count=0, never_recovered=False),   # recovered in ref
])
flaps, _ = merge_flaps([dut, ref], ["dut", "ref"])
by_lane = {(r["switch"], r["port"], r["lane"]): r for r in flaps}
assert by_lane[("0", 1, 1)]["never_recovered"] is True, "stuck in both runs stays stuck"
assert by_lane[("0", 1, 2)]["never_recovered"] is False, \
    "recovered in one run means not never-recovered overall; a union would keep it True"
before = 2 + 1
after = sum(1 for r in flaps if r["never_recovered"])
assert after == 1, f"intersect should give 1, a union would give 2 (got {after})"
print(f"ok  never_recovered intersects: {before} flagged across runs -> {after} overall")


# --- a lane only one run measured must survive -----------------------------------

dut = run(ber=[lane("0", 1, 1, values=[1e-11])])
ref = run(ber=[lane("0", 1, 1, values=[2e-11]),
               lane("4-33", 9, 1, values=[3e-11])])   # ref alone saw this one
merged = merge_values([dut, ref], "ber")
keys = {(r["switch"], r["port"], r["lane"]) for r in merged}
assert ("4-33", 9, 1) in keys, "dropping a lane only one run saw is the bug this exists to stop"
shared = [r for r in merged if (r["switch"], r["port"], r["lane"]) == ("0", 1, 1)][0]
assert sorted(shared["values"]) == [1e-11, 2e-11], "shared lanes pool their readings"
print("ok  coverage unions: a lane seen by one run only is kept, shared lanes concatenate")


# --- flap counts take the max, and disagreements are reported --------------------

dut = run(flaps=[lane("0", 1, 1, count=0, never_recovered=False)])
ref = run(flaps=[lane("0", 1, 1, count=3, never_recovered=False)])
flaps, conflicts = merge_flaps([dut, ref], ["dut", "ref"])
assert flaps[0]["count"] == 3, "a flap seen in either run really happened"
assert conflicts == 1
print("ok  flap count: max across runs, disagreement counted")


# --- a section absent from every run stays absent --------------------------------

assert merge_values([run(), run()], "tcode") is None, \
    "null must not become an empty list; 'could not look' is not 'looked, found nothing'"
present = merge_values([run(tcode=[lane("0", 1, 1, values=[1])]), run()], "tcode")
assert present is not None and len(present) == 1
print("ok  absent sections stay null, present-in-one-run sections survive")


# --- incompatible runs are refused rather than silently pooled -------------------

try:
    merge_meta([run(ber_source="fec_counter"), run(ber_source="vdm")], ["a", "b"])
    raise AssertionError("merging an ASIC counter with the optic's own reading must fail")
except ValueError as error:
    assert "never be pooled" in str(error)
print("ok  refuses to pool fec_counter with vdm")

try:
    merge_meta([run(test_type="soak"), run(test_type="reset")], ["a", "b"])
    raise AssertionError("merging a soak with a reset must fail")
except ValueError as error:
    assert "soak" in str(error)
print("ok  refuses to merge a soak capture with a reset one")


# --- later runs are shifted onto a shared clock, and the seam is recorded --------

first = run(start="2026-07-17 01:00:00",
            temps=[{"switch": "0", "port": 1, "points": [[0.0, 40.0], [1.0, 42.0]]}])
second = run(start="2026-07-18 01:00:00",
             temps=[{"switch": "0", "port": 1, "points": [[0.0, 50.0]]}])
offsets = _start_offsets([first, second])
assert offsets == [0.0, 24.0], offsets
points = merge_points([first, second], offsets, "temps", ["switch", "port"])[0]["points"]
assert points == [[0.0, 40.0], [1.0, 42.0], [24.0, 50.0]], points
print("ok  later runs shift onto a shared timeline (24h apart stays 24h apart)")


# --- end to end through files, which is how it is actually used ------------------

work = tempfile.mkdtemp()
paths = []
for name, data in (("dut.yml", first), ("ref.yml", second)):
    path = os.path.join(work, name)
    yaml.dump(data, open(path, "w"), default_flow_style=False, sort_keys=False)
    paths.append(path)
out = os.path.join(work, "merged.yml")
merged = merge_runs(paths, out)
written = yaml.safe_load(open(out))
assert written["meta"]["seams"] == [24.0], written["meta"]["seams"]
assert written["meta"]["merged_from"] == ["dut.yml", "ref.yml"]
assert written["meta"]["start_time"] == "2026-07-17 01:00:00", "earliest start wins"
print("ok  end to end: seams recorded so a chart knows not to draw across the gap")

assert MAX_LISTED_CONFLICTS > 0
print()
print("all tests passed")
