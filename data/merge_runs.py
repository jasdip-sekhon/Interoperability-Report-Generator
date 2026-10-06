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


def merge_meta(runs, labels):
    base = dict(runs[0]["meta"])

    # the ASIC counter and the optic's own reading are different instruments; pooling
    # them would compare two measurements against one threshold
    for run, label in zip(runs[1:], labels[1:]):
        if run["meta"]["ber_source"] != base["ber_source"]:
            raise ValueError(
                f"refusing to merge: {labels[0]} reports ber_source "
                f"'{base['ber_source']}' but {label} reports '{run['meta']['ber_source']}'. "
                "These are different instruments and must never be pooled.")
        if run["meta"]["test_type"] != base["test_type"]:
            raise ValueError(
                f"refusing to merge: {labels[0]} is a '{base['test_type']}' capture but "
                f"{label} is '{run['meta']['test_type']}'.")

    switches = {}
    for run, label in zip(runs, labels):
        for switch, info in (run["meta"]["switches"] or {}).items():
            if switch not in switches:
                switches[switch] = dict(info)
                continue
            for field, value in info.items():
                held = switches[switch][field]
                if held is None:
                    switches[switch][field] = value
                elif value is not None and value != held:
                    print(f"Warning: switch {switch} reports {field} '{held}' in "
                          f"{labels[0]} but '{value}' in {label}; keeping '{held}'. "
                          "The two runs may not be the same population.")

    starts = [run["meta"]["start_time"] for run in runs]
    base["start_time"] = min(starts)
    base["switches"] = switches
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
