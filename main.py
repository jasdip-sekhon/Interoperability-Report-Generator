"""Build one report from one run config: captures in, slide deck out.

Each stage is already a script that can be run on its own; this only sequences them and
decides where the intermediate files go. Each testcase renders into its own folder so
several can appear in one deck without overwriting each other's charts.
"""

from pathlib import Path
import argparse
import sys

import yaml
from openpyxl import load_workbook

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


# the sheets the converter reads. A topology workbook has none of them, and a folder
# of captures usually has the topology sitting right next to them.
CAPTURE_SHEETS = ("log", "get_link_flap", "get_module_info", "get_switch_sensor",
                  "get_fec_counter")


def is_capture(path):
    """Whether this workbook holds measurements, by the sheets it carries."""
    workbook = load_workbook(path, read_only=True)
    names = workbook.sheetnames
    workbook.close()
    for name in names:
        for sheet in CAPTURE_SHEETS:
            if name.endswith(sheet):
                return True
    return False


def config_for(target):
    """A config from whatever the user pointed at, so a one-off run needs no run.yml.

    A .yml is a run config. Anything else is captures: one spreadsheet, or a folder of
    them, each charted as its own testcase.

    Nothing is paired here, and that is the point. A config file exists because a DUT
    run and a Ref run cannot be told apart by filename - the real captures spell one
    testcase 'lane1-1' and 'ln1-1', another 'lan2-8' and 'lane2-8' - and a wrong
    pairing is silent, because a bad merge still makes a plausible deck. Charting each
    capture on its own is what the deck shows either way; only the merged yaml, which
    nothing charts, is lost.
    """
    target = Path(target)
    if target.suffix.lower() in (".yml", ".yaml"):
        return load_config(target)

    if target.is_dir():
        captures = []
        skipped = []
        for path in sorted(target.glob("*.xlsx")):
            if is_capture(path):
                captures.append(path)
            else:
                skipped.append(path.name)
        if skipped:
            print(f"== config == skipping {', '.join(skipped)}: no measurement sheets, "
                  f"so not a capture")
        if not captures:
            raise SystemExit(f"no captures in {target}")
        report = target.name
    elif target.exists():
        if not is_capture(target):
            raise SystemExit(f"{target.name} has no measurement sheets; it is not a "
                             f"capture. Pass a topology with --topology.")
        captures = [target]
        report = target.stem
    else:
        raise SystemExit(f"no such file or folder: {target}")

    testcases = []
    for capture in captures:
        testcases.append({"name": capture.stem,
                          "captures": [str(capture.resolve())]})
    print(f"== config == none given; charting {len(testcases)} capture(s) from "
          f"{target}, each on its own")
    return {"report": report, "testcases": testcases}


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


def run(target, topology=None):
    config = config_for(target)
    report = config.get("report", "Report")
    MEASUREMENTS_DIR.mkdir(parents=True, exist_ok=True)
    # everything one report produces lives under its own folder, so two racks cannot
    # overwrite each other's charts - which cost a deck once, silently
    report_dir = OUTPUT_DIR / _slug(report)
    report_dir.mkdir(parents=True, exist_ok=True)

    # a rack without a topology in the format we read still charts, just with plainer
    # x-axis labels taken from the measurements
    if topology is None:
        topology = config.get("topology")
    if topology:
        print("== topology ==")
        interconnects_yml = report_dir / INTERCONNECTS_YML.name
        interconnects_to_yml(_resolve(topology), interconnects_yml)
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
            charts_dir = report_dir / _slug(name)
            manifests.append(generate_plots(measurements, charts_dir,
                                            interconnects_yml, name,
                                            testcase.get("metrics")))

    print("== deck ==")
    deck_path = report_dir / f"{_slug(report)}.pptx"
    build_deck(manifests, deck_path, report)
    return deck_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", nargs="?", default=PROJECT_ROOT / "run.yml",
                        help="a run config, a capture .xlsx, or a folder of them "
                             "(default: run.yml)")
    parser.add_argument("-t", "--topology",
                        help="topology .xlsx for x-axis labels; without one the labels "
                             "come from the measurements themselves")
    args = parser.parse_args()
    run(args.target, args.topology)
