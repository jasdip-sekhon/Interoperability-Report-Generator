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


def prepare_measurements(testcase):
    """Convert this testcase's captures, merging them when there is more than one."""
    converted = []
    for capture in testcase["captures"]:
        source = _resolve(capture)
        target = MEASUREMENTS_DIR / (source.stem + ".yml")
        data_to_yml(source, target)
        converted.append(target)

    if len(converted) == 1:
        return converted[0]
    merged = MEASUREMENTS_DIR / f"{_slug(testcase['name'])}_merged.yml"
    merge_runs(converted, merged)
    return merged


def run(config_path):
    config = load_config(config_path)
    report = config.get("report", "Report")
    MEASUREMENTS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"== topology ==")
    interconnects_to_yml(_resolve(config["topology"]), INTERCONNECTS_YML)

    manifests = []
    for testcase in config["testcases"]:
        print(f"== {testcase['name']} ==")
        measurements = prepare_measurements(testcase)
        charts_dir = OUTPUT_DIR / _slug(testcase["name"])
        manifests.append(generate_plots(measurements, charts_dir))

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
