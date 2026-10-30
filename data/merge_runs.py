"""Join the measurement yaml of two or more runs of the same testcase into one.

A reset testcase is captured twice - once DUT-run, once Ref-run - and neither file is
authoritative for a subset of the switches. Charting just one silently drops whatever
the other saw; on the real captures that hid 68 failing lanes.

Coverage is unioned, but the per-field rules differ and one of them is the opposite of
a union - see merge_flaps.
"""

from datetime import datetime
from pathlib import Path
import argparse
import yaml

MAX_LISTED_CONFLICTS = 5


def _load(path):
    with open(path) as f:
        return yaml.safe_load(f)


def _index(records, fields):
    # section -> {key tuple: record}, so runs can be compared key by key
    indexed = {}
    for record in records or []:
        key = []
        for field in fields:
            key.append(record[field])
        indexed[tuple(key)] = record
    return indexed


def _start_offsets(runs):
    # each run numbers its hours from its own start, so a later run has to be shifted
    # onto a shared timeline or the two would overlap at the same x positions
    starts = []
    for run in runs:
        starts.append(datetime.strptime(run["meta"]["start_time"], "%Y-%m-%d %H:%M:%S"))
    earliest = min(starts)
    offsets = []
    for start in starts:
        offsets.append((start - earliest).total_seconds() / 3600.0)
    return offsets


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
            print(f"Warning: switch {switch} reports {field} '{held[field]}' in "
                  f"{first_label} but '{value}' in {label}; keeping '{held[field]}'. "
                  "The two runs may not be the same population.")


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


def merge_flaps(runs, labels):
    merged = {}
    seen = {}
    for run in runs:
        for key, record in _index(run["flaps"], ["switch", "port", "lane"]).items():
            if key not in seen:
                seen[key] = []
            seen[key].append(record)

    conflicts = 0
    for key in seen:
        records = seen[key]
        switch, port, lane = key

        # a flap seen in either run really happened, so the highest count wins
        count = 0
        for record in records:
            if record["count"] > count:
                count = record["count"]
        counts = {record["count"] for record in records}
        if len(counts) > 1:
            conflicts = conflicts + 1
            # a real capture can disagree on hundreds of lanes; listing every one buries
            # the summary, so only the first few are named and the rest are counted
            if conflicts <= MAX_LISTED_CONFLICTS:
                print(f"Warning: switch {switch} port {port} lane {lane} flap count "
                      f"differs across runs {sorted(counts)}; keeping {count}.")
            elif conflicts == MAX_LISTED_CONFLICTS + 1:
                print("Warning: further flap-count disagreements not listed "
                      "individually; see the count below.")

        # intersected, not unioned: a lane that recovered even once in any run is not
        # 'never recovered' overall, so a union here would invent failures
        flags = []
        for record in records:
            if record["never_recovered"] is not None:
                flags.append(record["never_recovered"])
        if not flags:
            never_recovered = None
        else:
            never_recovered = all(flags)

        merged[key] = {
            "switch": switch,
            "port": port,
            "lane": lane,
            "count": count,
            "never_recovered": never_recovered,
        }
    return list(merged.values()), conflicts


def merge_values(runs, section):
    # ber, tcode, uncorrected_cw and link_up are all per-lane reading lists, so more
    # runs simply means more samples of the same lane
    present = False
    merged = {}
    for run in runs:
        if run.get(section) is None:
            continue
        present = True
        for key, record in _index(run[section], ["switch", "port", "lane"]).items():
            if key not in merged:
                switch, port, lane = key
                merged[key] = {"switch": switch, "port": port, "lane": lane, "values": []}
            merged[key]["values"].extend(record["values"])
    if not present:
        return None
    return list(merged.values())


def merge_points(runs, offsets, section, fields):
    merged = {}
    for run, offset in zip(runs, offsets):
        for key, record in _index(run[section], fields).items():
            if key not in merged:
                merged[key] = dict(record)
                merged[key]["points"] = []
            for hours, value in record["points"]:
                merged[key]["points"].append([round(hours + offset, 4), value])
    for key in merged:
        merged[key]["points"] = sorted(merged[key]["points"])
    return list(merged.values())


def merge_runs(paths, out_path):
    runs = []
    labels = []
    for path in paths:
        runs.append(_load(path))
        labels.append(Path(path).name)

    offsets = _start_offsets(runs)
    flaps, conflicts = merge_flaps(runs, labels)
    meta = merge_meta(runs, labels)

    # where one run ends and the next begins on the shared timeline. Nothing was
    # measured across these gaps, so a chart must not draw a line over them.
    seams = []
    for offset in offsets[1:]:
        seams.append(round(offset, 4))
    meta["seams"] = seams

    merged = {
        "meta": meta,
        "flaps": flaps,
        "ber": merge_values(runs, "ber"),
        "tcode": merge_values(runs, "tcode"),
        "uncorrected_cw": merge_values(runs, "uncorrected_cw"),
        "link_up": merge_values(runs, "link_up"),
        "temps": merge_points(runs, offsets, "temps", ["switch", "port"]),
        "sensors": merge_points(runs, offsets, "sensors", ["switch"]),
    }

    with open(out_path, "w") as f:
        yaml.dump(merged, f, default_flow_style=False, sort_keys=False)

    _report(runs, labels, merged, offsets, conflicts)
    return merged


def _report(runs, labels, merged, offsets, conflicts):
    print(f"Merged {len(runs)} runs: {', '.join(labels)}")
    lane = ["switch", "port", "lane"]
    for section, fields in (("flaps", lane), ("ber", lane), ("tcode", lane),
                            ("uncorrected_cw", lane), ("link_up", lane),
                            ("temps", ["switch", "port"]), ("sensors", ["switch"])):
        if merged[section] is None:
            print(f"  {section:14}   -- (absent from every run)")
            continue
        total = len(merged[section])
        line = f"  {section:14} {total:4} entries"
        for run, label in zip(runs, labels):
            own = set(_index(run.get(section), fields))
            others = set()
            for other in runs:
                if other is not run:
                    others |= set(_index(other.get(section), fields))
            only = len(own - others)
            if only:
                line = line + f" | {only} only in {label}"
        print(line)

    before = []
    for run in runs:
        before.append(sum(1 for r in run["flaps"] if r["never_recovered"]))
    after = sum(1 for r in merged["flaps"] if r["never_recovered"])
    print(f"  never_recovered {' + '.join(str(n) for n in before)} -> {after} "
          f"(intersected; a lane recovering in any run is not never-recovered)")

    for label, offset in zip(labels[1:], offsets[1:]):
        print(f"  {label} time-shifted +{offset:.2f}h onto the shared timeline")
    if conflicts:
        print(f"  {conflicts} lane(s) disagreed on flap count between runs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("runs", nargs="+", help="measurement yaml files to merge")
    parser.add_argument("-o", "--out", required=True, help="merged yaml to write")
    args = parser.parse_args()
    merge_runs(args.runs, args.out)
    print(f"Wrote {args.out}")
