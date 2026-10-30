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
from data_to_yml import data_to_yml                    # noqa: E402
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
    """[(label, path)] for this testcase. A bare path has no label."""
    entries = []
    for capture in testcase["captures"]:
        if isinstance(capture, dict):
            entries.append((capture.get("label"), capture["file"]))
        else:
            entries.append((None, capture))
    return entries


def prepare_measurements(testcase):
    """Convert each capture. Returns [(label, measurement yaml)].

    Each run is charted on its own: a DUT run and a Ref run reset different hardware, so
    merging would seam every time series. The merged yaml is written anyway, for the
    analysis that wants the union.
    """
    recovery_commanded = testcase.get("recovery_commanded")
    if recovery_commanded is None:
        recovery_commanded = False

    converted = []
    paths = []
    for label, capture in _capture_entries(testcase):
        source = _resolve(capture)
        target = MEASUREMENTS_DIR / (source.stem + ".yml")
        # the configured name, not a guess from the sheets: detection calls every
        # non-reset capture a soak, losing the recovery signal
        data_to_yml(source, target, _slug(testcase["name"]), recovery_commanded)
        converted.append((label, target))
        paths.append(target)

    if len(paths) > 1:
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


def run(target, topology=None):
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
        for label, measurements in prepare_measurements(testcase):
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
