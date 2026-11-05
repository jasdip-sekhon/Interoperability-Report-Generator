"""How each section of two runs is reconciled: flags intersect, readings concatenate,
flap counts take the highest."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from console import warn                                       # noqa: E402

MAX_LISTED_CONFLICTS = 5

def _index(records, fields):
    # section -> {key tuple: record}, so runs can be compared key by key
    indexed = {}
    for record in records or []:
        key = []
        for field in fields:
            key.append(record[field])
        indexed[tuple(key)] = record
    return indexed


def _refuse_mixed_ber_sources(runs, labels):
    """The ASIC counter and the optic's own reading are different instruments; pooling
    them would compare two measurements against one threshold."""
    held = runs[0]["meta"]["ber_source"]
    for i in range(1, len(runs)):
        source = runs[i]["meta"]["ber_source"]
        if source != held:
            raise ValueError(
                f"refusing to merge: {labels[0]} reports ber_source '{held}' but "
                f"{labels[i]} reports '{source}'. These are different instruments "
                "and must never be pooled.")


def _refuse_mixed_test_types(runs, labels):
    """A reset and a soak answer different questions; one chart cannot serve both."""
    held = runs[0]["meta"]["test_type"]
    for i in range(1, len(runs)):
        test_type = runs[i]["meta"]["test_type"]
        if test_type != held:
            raise ValueError(
                f"refusing to merge: {labels[0]} is a '{held}' capture but "
                f"{labels[i]} is '{test_type}'.")


def _fill_switch_gaps(held, info, switch, first_label, label):
    """Take what the first run did not describe; warn where the two disagree."""
    for field in info:
        value = info[field]
        if held[field] is None:
            held[field] = value
        elif value is not None and value != held[field]:
            warn(f"switch {switch} reports {field} '{held[field]}' in {first_label} "
                 f"but '{value}' in {label}; keeping '{held[field]}'. The two runs may "
                 f"not be the same population")


def _union_switches(runs, labels):
    """Every switch any run described, each filled in from whichever run knew it."""
    switches = {}
    for i in range(len(runs)):
        described = runs[i]["meta"]["switches"]
        if described is None:
            described = {}
        for switch in described:
            if switch not in switches:
                switches[switch] = dict(described[switch])
            else:
                _fill_switch_gaps(switches[switch], described[switch], switch,
                                  labels[0], labels[i])
    return switches


def _earliest_start(runs):
    starts = []
    for run in runs:
        starts.append(run["meta"]["start_time"])
    return min(starts)


def merge_meta(runs, labels):
    base = dict(runs[0]["meta"])
    _refuse_mixed_ber_sources(runs, labels)
    _refuse_mixed_test_types(runs, labels)
    base["switches"] = _union_switches(runs, labels)
    base["start_time"] = _earliest_start(runs)
    base["merged_from"] = list(labels)
    return base


def _flaps_by_lane(runs):
    """Every flap record each lane has, across the runs."""
    seen = {}
    for run in runs:
        indexed = _index(run["flaps"], ["switch", "port", "lane"])
        for key in indexed:
            if key not in seen:
                seen[key] = []
            seen[key].append(indexed[key])
    return seen


def _highest_count(records):
    """A flap seen in either run really happened, so the highest count wins."""
    count = 0
    for record in records:
        if record["count"] > count:
            count = record["count"]
    return count


def _distinct_counts(records):
    counts = []
    for record in records:
        if record["count"] not in counts:
            counts.append(record["count"])
    return counts


def _never_recovered_across(records):
    """Intersected, not unioned: a lane that recovered even once in any run is not
    never-recovered overall, so a union here would invent failures."""
    flags = []
    for record in records:
        flags.append(record["never_recovered"])
    return all(flags)


def _report_count_conflict(key, counts, kept, conflicts):
    """A real capture can disagree on hundreds of lanes; listing every one buries the
    summary, so only the first few are named and the rest are counted."""
    switch, port, lane = key
    if conflicts <= MAX_LISTED_CONFLICTS:
        counts_text = []
        for count in sorted(counts):
            counts_text.append(str(count))
        counts_text = ", ".join(counts_text)
        warn(f"switch {switch} port {port} lane {lane} flap count differs across "
             f"runs ({counts_text}); keeping {kept}")
    elif conflicts == MAX_LISTED_CONFLICTS + 1:
        warn("further flap-count disagreements not listed individually; see the "
             "count below")


def merge_flaps(runs, quiet=False):
    merged = []
    conflicts = 0
    by_lane = _flaps_by_lane(runs)
    for key in by_lane:
        records = by_lane[key]
        switch, port, lane = key
        count = _highest_count(records)
        counts = _distinct_counts(records)
        if len(counts) > 1:
            conflicts = conflicts + 1
            # quiet: reconciling DUT against Ref is not a result anyone should read
            if not quiet:
                _report_count_conflict(key, counts, count, conflicts)
        merged.append({
            "switch": switch,
            "port": port,
            "lane": lane,
            "count": count,
            "never_recovered": _never_recovered_across(records),
        })
    return merged, conflicts


def merge_values(runs, section):
    # ber, tcode, uncorrected_cw and link_up are all per-lane reading lists, so more
    # runs simply means more samples of the same lane
    present = False
    merged = {}
    for run in runs:
        if run.get(section) is None:
            continue
        present = True
        indexed = _index(run[section], ["switch", "port", "lane"])
        for key in indexed:
            if key not in merged:
                switch, port, lane = key
                merged[key] = {"switch": switch, "port": port, "lane": lane, "values": []}
            merged[key]["values"].extend(indexed[key]["values"])
    if not present:
        return None
    return list(merged.values())


def merge_points(runs, offsets, section, fields):
    merged = {}
    for i in range(len(runs)):
        indexed = _index(runs[i][section], fields)
        for key in indexed:
            if key not in merged:
                merged[key] = dict(indexed[key])
                merged[key]["points"] = []
            for hours, value in indexed[key]["points"]:
                merged[key]["points"].append([round(hours + offsets[i], 4), value])
    for key in merged:
        merged[key]["points"] = sorted(merged[key]["points"])
    return list(merged.values())
