"""Render every chart for one capture, from the yaml the converters produce.

This decides which charts a capture gets and writes the result. Imports run one way,
so a change never has to be chased backwards:

    plotting_runner -> charts -> {output, x_axis} -> plotting

plotting.py is the generic chart library and imports none of the others.
"""

from pathlib import Path
import yaml

from charts import (draw_ber, draw_flaps_by_interconnect, draw_flaps_by_switch,
                    draw_link_up, draw_tcode, draw_temperature_over_time,
                    draw_temperature_per_port)
from output import clear_output_dir, _sort_by_scope, _write_manifest
from x_axis import (build_interconnect_axis, build_measured_axis,
                    build_measured_switches, build_port_vendors, build_switch_axis,
                    topology_source)

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
INTERCONNECTS_YML = PROJECT_ROOT / "interconnects" / "interconnects.yml"
MEASUREMENTS_DIR = PROJECT_ROOT / "data" / "output"

# what a testcase can ask to chart, named after the measurement yaml's sections
METRICS = ("flaps", "ber", "tcode", "link_up", "temps")


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)
    

def _wanted(metrics, name):
    """Every metric unless the testcase named a subset."""
    if metrics is None:
        return True
    return name in metrics


def _report_unknown_metrics(metrics):
    unknown = []
    for name in metrics:
        if name not in METRICS:
            unknown.append(name)
    if unknown:
        if len(unknown) == 1:
            metric_word = "metric"
        else:
            metric_word = "metrics"
        print(f"  Warning: configured {metric_word} {', '.join(unknown)} are not drawn "
              f"by anything; known metrics are {', '.join(METRICS)}.")


def generate_plots(measurements_yml, out_dir, interconnects_yml=INTERCONNECTS_YML,
                   testcase=None, metrics=None):
    measurements = load_yaml(measurements_yml)
    meta = measurements["meta"]
    if meta["ber_source"] is None:
        ber_note = "BER not collected"
    elif meta["ber_source"] == "fec_counter":
        ber_note = "BER from the switch's FEC counter"
    else:
        ber_note = "BER from the module's own VDM reading"
    if testcase is None:
        heading = Path(measurements_yml).name
    else:
        heading = testcase
    print(f"{heading} ({meta['test_type']}, {ber_note})")
    clear_output_dir(out_dir)

    if interconnects_yml and Path(interconnects_yml).exists():
        interconnects = load_yaml(interconnects_yml)
        print(f"  Interconnect order from {topology_source(interconnects_yml)}, "
              f"{len(interconnects)} interconnects")
        keys, labels = build_interconnect_axis(interconnects)
        switch_keys, switch_labels = build_switch_axis(interconnects)
        vendors = build_port_vendors(interconnects)
    else:
        print("  Info: no topology file; ordering interconnects from the measurements "
              "themselves, so entries are named rather than described.")
        keys, labels = build_measured_axis(measurements)
        switch_keys, switch_labels = build_measured_switches(measurements)
        vendors = {}

    seams = meta.get("seams")
    if seams is None:
        seams = []
    if seams:
        at = []
        for seam in seams:
            at.append(f"{seam:.1f}h")
        print(f"  Info: merged capture; lines break at {len(seams)} run boundary "
              f"({', '.join(at)}) where nothing was measured.")

    if metrics is not None:
        _report_unknown_metrics(metrics)
        print(f"  Charting {', '.join(metrics)}; this testcase measures nothing else.")

    charts = []
    if _wanted(metrics, "flaps"):
        charts.extend(draw_flaps_by_switch(measurements, switch_keys, switch_labels,
                                           out_dir))
        charts.extend(draw_flaps_by_interconnect(measurements, meta, keys, labels,
                                                 out_dir))
    if _wanted(metrics, "ber"):
        charts.extend(draw_ber(measurements, meta, keys, labels, out_dir))
    if _wanted(metrics, "tcode"):
        charts.extend(draw_tcode(measurements, meta, keys, labels, out_dir))
    if _wanted(metrics, "link_up"):
        charts.extend(draw_link_up(measurements, meta, keys, labels, out_dir))
    if _wanted(metrics, "temps"):
        charts.extend(draw_temperature_over_time(measurements, meta, switch_keys, seams,
                                                 out_dir))
        charts.extend(draw_temperature_per_port(measurements, meta, switch_keys, vendors,
                                                out_dir))

    return _write_manifest(measurements_yml, meta, _sort_by_scope(charts), out_dir, testcase)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("measurements", nargs="?",
                        default=MEASUREMENTS_DIR / "soak_sample.yml",
                        help="measurement yaml to chart")
    parser.add_argument("-o", "--out-dir",
                        help="where the charts go (default: output/<capture name>/)")
    args = parser.parse_args()
    if args.out_dir is None:
        out_dir = OUTPUT_DIR / Path(args.measurements).stem
    else:
        out_dir = args.out_dir
    generate_plots(args.measurements, out_dir)
