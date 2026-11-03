"""Sequence the four stages: captures in, slide deck out.

Each stage is already a script that runs on its own; this only orders them and decides
where the files go. One report writes one folder under output/, so two racks cannot
overwrite each other's charts.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent
# the stages are sibling scripts rather than a package, so they import each other by
# bare name; one sys.path fixup here beats rewriting every import (see tests/_bootstrap)
for folder in ("data", "interconnects", "plotting", "deck"):
    sys.path.insert(0, str(PROJECT_ROOT / folder))

from build_deck import build_deck                      # noqa: E402
from data_to_yml import data_to_yml, is_current        # noqa: E402
from interconnects_to_yml import interconnects_to_yml  # noqa: E402
from merge_runs import merge_runs                      # noqa: E402
from plotting_runner import generate_plots             # noqa: E402
from run_config import config_for                      # noqa: E402

MEASUREMENTS_DIR = PROJECT_ROOT / "data" / "output"
OUTPUT_DIR = PROJECT_ROOT / "output"
INTERCONNECTS_NAME = "interconnects.yml"


def _slug(name):
    return name.strip().lower().replace(" ", "_").replace("/", "_")


def _resolve(path):
    path = Path(path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _capture_entries(testcase):
    """[(label, path)] for this testcase.

    The common shapes write flat - `capture:` for one file, `dut:`/`ref:` for a
    pair - so a config never needs the list-of-dicts form unless a testcase has more
    than two runs or labels other than DUT/Ref. `captures:` still does that, in full.
    """
    flat = {key for key in ("capture", "dut", "ref") if key in testcase}
    if flat and "captures" in testcase:
        raise ValueError(f"testcase '{testcase['name']}' has both {sorted(flat)} and "
                         f"'captures' - use one or the other, not both.")

    if "capture" in testcase:
        return [(None, testcase["capture"])]
    if flat:
        entries = []
        if "dut" in testcase:
            entries.append(("DUT", testcase["dut"]))
        if "ref" in testcase:
            entries.append(("Ref", testcase["ref"]))
        return entries

    entries = []
    for capture in testcase["captures"]:
        if isinstance(capture, dict):
            entries.append((capture.get("label"), capture["file"]))
        else:
            entries.append((None, capture))
    return entries


def prepare_measurements(testcase, use_cache=True):
    """Convert each capture. Returns [(label, measurement yaml)].

    Each run is charted on its own: a DUT run and a Ref run reset different hardware, so
    merging would seam every time series. The merged yaml is written anyway, for the
    analysis that wants the union.
    """
    recovery_commanded = testcase.get("recovery_commanded")
    if recovery_commanded is None:
        recovery_commanded = False

    # the configured name, not a guess from the sheets: detection calls every
    # non-reset capture a soak, losing the recovery signal
    test_type = _slug(testcase["name"])

    converted = []
    paths = []
    reused = 0
    for label, capture in _capture_entries(testcase):
        source = _resolve(capture)
        target = MEASUREMENTS_DIR / (source.stem + ".yml")
        if use_cache and is_current(source, target, test_type, recovery_commanded):
            reused = reused + 1
        else:
            data_to_yml(source, target, test_type, recovery_commanded)
        converted.append((label, target))
        paths.append(target)

    if reused:
        print(f"  Reused {reused} of {len(paths)} capture(s); the spreadsheets and the "
              f"converter are unchanged since they were read.")

    if len(paths) > 1:
        # not cached: it is seconds, and redoing it keeps it true to its inputs
        merged = MEASUREMENTS_DIR / f"{_slug(testcase['name'])}_merged.yml"
        merge_runs(paths, merged)
    return converted


def build_x_axis(topology, report_dir):
    """The topology yaml this report charts against, or None to label from the data."""
    if topology is None:
        print("== topology == none configured; x axis comes from the measurements")
        return None
    print("== topology ==")
    interconnects_yml = report_dir / INTERCONNECTS_NAME
    interconnects_to_yml(_resolve(topology), interconnects_yml)
    return interconnects_yml


def run(target, topology=None, use_cache=True):
    config = config_for(target)
    report = config.get("report")
    if report is None:
        report = "Report"
    if topology is None:                 # the flag overrides the config, not the reverse
        topology = config.get("topology")

    report_dir = OUTPUT_DIR / _slug(report)
    MEASUREMENTS_DIR.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    interconnects_yml = build_x_axis(topology, report_dir)

    manifests = []
    for testcase in config["testcases"]:
        print(f"== {testcase['name']} ==")
        for label, measurements in prepare_measurements(testcase, use_cache):
            name = testcase["name"]
            if label:
                name = f"{name} {label}"
            manifests.append(generate_plots(measurements, report_dir / _slug(name),
                                            interconnects_yml, name,
                                            testcase.get("metrics")))

    print("== deck ==")
    deck_path = report_dir / f"{_slug(report)}.pptx"
    build_deck(manifests, deck_path, report)
    return deck_path
