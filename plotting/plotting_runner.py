"""Render every chart for one capture, from the yaml the converters produce.

This decides which charts a capture gets and writes the result. Imports run one way,
so a change never has to be chased backwards:

    plotting_runner -> charts -> {output, x_axis} -> plotting

plotting.py is the generic chart library and imports none of the others.
"""

from pathlib import Path
import sys
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))
from console import info, line, say, short_path, warn         # noqa: E402

from charts import (METRIC_NAMES, draw_ber, draw_flaps_by_interconnect,
                    draw_flaps_by_switch, draw_link_up, draw_tcode,
                    draw_temperature_over_time, draw_temperature_per_port,
                    draw_uncorrected_cw)
from output import clear_output_dir, _sort_by_scope, _write_manifest
from x_axis import (build_interconnect_axis, build_measured_axis,
                    build_measured_switches, build_port_vendors, build_switch_axis,
                    report_uncharted_lanes, topology_source)

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
INTERCONNECTS_YML = PROJECT_ROOT / "interconnects" / "interconnects.yml"
MEASUREMENTS_DIR = PROJECT_ROOT / "data" / "output"

# what a testcase can ask to chart, named after the measurement yaml's sections
METRICS = ("flaps", "ber", "tcode", "uncorrected_cw", "link_up", "temps")


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)
    

def load_axis(interconnects_yml):
    """The topology, read once per report. Re-reading it per testcase lets a run that
    writes the same path change the axis partway through, which charts as silent gaps."""
    if interconnects_yml is None:
        return None
    if not Path(interconnects_yml).exists():
        return None
    return {"interconnects": load_yaml(interconnects_yml),
            "source": short_path(topology_source(interconnects_yml))}


def _wanted(metrics, name):
    """Every metric unless the testcase named a subset."""
    if metrics is None:
        return True
    return name in metrics


def _report_empty_metrics(metrics, drawn):
    """A metric the config asks for that the capture never measured: the config and the
    data have drifted apart, and a silently missing chart is how that stays hidden."""
    if metrics is None:
        return
    empty = []
    for name in metrics:
        if name in METRICS and name not in drawn:
            empty.append(name)
    if empty:
        named = []
        for name in empty:
            named.append(METRIC_NAMES[name])
        warn(f"{', '.join(named)} configured for this testcase but not measured in "
             f"this capture, so no chart is drawn")


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
        warn(f"configured {metric_word} {', '.join(unknown)} are not drawn by "
             f"anything; known metrics are {', '.join(METRICS)}")


def generate_plots(measurements_yml, out_dir, interconnects_yml=INTERCONNECTS_YML,
                   testcase=None, metrics=None, axis=None):
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
    replaced = clear_output_dir(out_dir)

    # a caller that passed the axis in has already named it; only a standalone run
    # has to announce it here, and then only once for the one capture it charts
    announce = axis is None
    if axis is None:
        axis = load_axis(interconnects_yml)

    if axis is not None:
        interconnects = axis["interconnects"]
        if announce:
            line(f"Interconnect order from {axis['source']}, {len(interconnects)} "
                 f"interconnects")
        keys, labels = build_interconnect_axis(interconnects)
        switch_keys, switch_labels = build_switch_axis(interconnects)
        vendors = build_port_vendors(interconnects)
        report_uncharted_lanes(measurements, keys, METRIC_NAMES)
    else:
        info("no topology file; ordering interconnects from the measurements "
             "themselves, so entries are named rather than described")
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
        info(f"merged capture; lines break at {len(seams)} run boundary "
             f"({', '.join(at)}) where nothing was measured")

    if metrics is not None:
        _report_unknown_metrics(metrics)

    # what was charted is what the draw_* calls returned, not what the config asked
    # for: a metric the capture never measured draws nothing and must not be claimed
    charts = []
    drawn = []
    if _wanted(metrics, "flaps"):
        before = len(charts)
        charts.extend(draw_flaps_by_switch(measurements, switch_keys, switch_labels,
                                           out_dir))
        charts.extend(draw_flaps_by_interconnect(measurements, meta, keys, labels,
                                                 out_dir))
        if len(charts) > before:
            drawn.append("flaps")
    if _wanted(metrics, "ber"):
        before = len(charts)
        charts.extend(draw_ber(measurements, meta, keys, labels, out_dir))
        if len(charts) > before:
            drawn.append("ber")
    if _wanted(metrics, "tcode"):
        before = len(charts)
        charts.extend(draw_tcode(measurements, meta, keys, labels, out_dir))
        if len(charts) > before:
            drawn.append("tcode")
    if _wanted(metrics, "uncorrected_cw"):
        before = len(charts)
        charts.extend(draw_uncorrected_cw(measurements, meta, keys, labels, out_dir))
        if len(charts) > before:
            drawn.append("uncorrected_cw")
    if _wanted(metrics, "link_up"):
        before = len(charts)
        charts.extend(draw_link_up(measurements, meta, keys, labels, out_dir))
        if len(charts) > before:
            drawn.append("link_up")
    if _wanted(metrics, "temps"):
        before = len(charts)
        charts.extend(draw_temperature_over_time(measurements, meta, switch_keys, seams,
                                                 out_dir))
        charts.extend(draw_temperature_per_port(measurements, meta, switch_keys, vendors,
                                                out_dir))
        if len(charts) > before:
            drawn.append("temps")

    if drawn:
        named = []
        for name in drawn:
            named.append(METRIC_NAMES[name])
        say(f"Charting {', '.join(named)}")
    _report_empty_metrics(metrics, drawn)

    return _write_manifest(measurements_yml, meta, _sort_by_scope(charts), out_dir,
                           testcase, replaced)


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
