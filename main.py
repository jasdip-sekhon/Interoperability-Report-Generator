"""Build one report from one run config: captures in, slide deck out.

Each stage is already a script that can be run on its own; this only sequences them and
decides where the intermediate files go. Each testcase renders into its own folder so
several can appear in one deck without overwriting each other's charts.
"""

from pathlib import Path
import argparse
import sys

import yaml

PROJECT_ROOT = Path(__file__).parent
# the stages are sibling scripts rather than a package, so they import each other by
# bare name; one sys.path fixup here beats rewriting every import and every test
for folder in ("data", "interconnects", "plotting", "deck"):
    sys.path.insert(0, str(PROJECT_ROOT / folder))

from build_deck import build_deck                      # noqa: E402
from data_to_yml import data_to_yml                    # noqa: E402
from interconnects_to_yml import interconnects_to_yml  # noqa: E402
from merge_runs import merge_runs                      # noqa: E402
from plotting_runner import generate_plots             # noqa: E402

MEASUREMENTS_DIR = PROJECT_ROOT / "data" / "output"
INTERCONNECTS_YML = PROJECT_ROOT / "interconnects" / "interconnects.yml"
OUTPUT_DIR = PROJECT_ROOT / "output"


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _slug(name):
    return name.strip().lower().replace(" ", "_").replace("/", "_")


def _resolve(path):
    path = Path(path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _test_type(testcase):
    """What this capture is, taken from the config rather than guessed from its sheets.

    It matters beyond the label: only a soak commands no link recovery, so only a soak
    suppresses never_recovered. A reset, a shut/no-shut and the lane tests all command
    one, and sheet-based detection calls every non-reset capture a soak - which would
    throw that signal away for three of the five testcases.
    """
    return _slug(testcase["name"])


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
    """Convert each capture of this testcase. Returns [(label, measurement yaml)].

    Each run is charted on its own rather than merged. A reset-DUT run resets the DUT's
    modules and a reset-Ref run resets the other side's, so the two measured different
    hardware - merging them would put a seam through every time series and hide which
    run saw a given flap.

    The merged view is still written, because the union is what an analysis stage needs:
    picking one file per switch is what hid 68 failing lanes on the real data.
    """
    converted = []
    for label, capture in _capture_entries(testcase):
        source = _resolve(capture)
        target = MEASUREMENTS_DIR / (source.stem + ".yml")
        data_to_yml(source, target, _test_type(testcase),
                    testcase.get("recovery_commanded", False))
        converted.append((label, target))

    if len(converted) > 1:
        merged = MEASUREMENTS_DIR / f"{_slug(testcase['name'])}_merged.yml"
        paths = []
        for _, path in converted:
            paths.append(path)
        merge_runs(paths, merged)
    return converted


def run(config_path):
    config = load_config(config_path)
    report = config.get("report", "Report")
    MEASUREMENTS_DIR.mkdir(parents=True, exist_ok=True)

    # a rack without a topology in the format we read still charts, just with plainer
    # x-axis labels taken from the measurements
    topology = config.get("topology")
    if topology:
        print("== topology ==")
        interconnects_to_yml(_resolve(topology), INTERCONNECTS_YML)
        interconnects_yml = INTERCONNECTS_YML
    else:
        print("== topology == none configured; x axis comes from the measurements")
        interconnects_yml = None

    manifests = []
    for testcase in config["testcases"]:
        print(f"== {testcase['name']} ==")
        for label, measurements in prepare_measurements(testcase):
            name = testcase["name"]
            if label:
                name = f"{name} {label}"
            charts_dir = OUTPUT_DIR / _slug(name)
            manifests.append(generate_plots(measurements, charts_dir,
                                            interconnects_yml, name))

    print("== deck ==")
    deck_path = OUTPUT_DIR / f"{_slug(report)}.pptx"
    build_deck(manifests, deck_path, report)
    return deck_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("config", nargs="?", default=PROJECT_ROOT / "run.yml",
                        help="run config listing the captures (default: run.yml)")
    args = parser.parse_args()
    run(args.config)
