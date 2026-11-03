"""Several runs of one testcase into one measurement yaml.

    merge_runs -> {merge_rules, merge_report} -> merge_rules

Each capture is still charted on its own; this union is what an analysis stage needs.
"""

from datetime import datetime
from pathlib import Path
import argparse

import yaml

from merge_report import _report
from merge_rules import merge_flaps, merge_meta, merge_points, merge_values

def _load(path):
    with open(path) as f:
        return yaml.safe_load(f)




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






























def merge_runs(paths, out_path, labels=None, quiet=False):
    """labels names each run in the printed summary; the filename if none is given.

    quiet reduces the summary to one line: nothing reads the merged yaml, so for a
    DUT/Ref pair its reconciliation is not a result, and reads as one when skimmed.
    """
    if labels is None:
        labels = []
        for path in paths:
            labels.append(Path(path).name)

    runs = []
    for path in paths:
        runs.append(_load(path))

    offsets = _start_offsets(runs)
    flaps, conflicts = merge_flaps(runs, quiet)
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

    partial = Path(out_path).with_suffix(".partial")
    with open(partial, "w") as f:
        yaml.dump(merged, f, default_flow_style=False, sort_keys=False)
    partial.replace(out_path)

    _report(runs, labels, merged, offsets, conflicts, out_path, quiet)
    return merged












if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("runs", nargs="+", help="measurement yaml files to merge")
    parser.add_argument("-o", "--out", required=True, help="merged yaml to write")
    args = parser.parse_args()
    merge_runs(args.runs, args.out)
    print(f"Wrote {args.out}")
