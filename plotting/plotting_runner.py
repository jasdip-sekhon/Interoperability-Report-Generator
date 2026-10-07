"""Render every chart for one capture.

Reads the two yaml files the converters produce and never opens a spreadsheet, so
re-rendering costs milliseconds rather than re-parsing the capture.

interconnects.yml supplies the x axis - which entries appear, in what order, and what
each is called. The measurement yaml supplies the values. The two name switches and
ports differently, so the topology side is normalised onto the measurement side's keys
before anything is looked up; see _topology_key.

Charts go in a folder of their own and a manifest declares what was drawn, so the deck
builder needs no knowledge of which metrics exist or how switches are named.
"""

from pathlib import Path
import yaml

from plotting import Plots

PROJECT_ROOT = Path(__file__).parent.parent
# decks sit at the top of output/; charts always go in a folder under it, one folder per
# thing rendered. Nothing else writes here, so a chart cannot be mistaken for one
# belonging to a different capture.
OUTPUT_DIR = PROJECT_ROOT / "output"
INTERCONNECTS_YML = PROJECT_ROOT / "interconnects" / "interconnects.yml"
MEASUREMENTS_DIR = PROJECT_ROOT / "data" / "output"
MANIFEST_NAME = "manifest.yml"
# a bit error rate of 0.5 means half the bits are wrong, which is noise rather than a
# degraded link; readings at or above it are the counter saturating
SATURATED_BER = 0.5
# the board sensor is the reference the module traces are read against; the chart
# library knows it only as "an overlay", so the domain word is supplied from here
SENSOR_LABEL = "Board Sensor"

plots = Plots()

CHART_KINDS = {"box": plots.box_plot, "dot": plots.dot_plot, "bar": plots.bargraph}

# Every chart drawn against the interconnect axis, declared rather than hand-written.
# Adding a metric is a row here; the loop below needs no change, and neither does
# anything downstream that wants to know which charts a run produces.
#   section          the measurement yaml key, null when the capture lacks it
#   stem + kind      the file name, e.g. pre_fec_ber_box.png
#   title            formatted against meta, so it can name the instrument used
#   field            read this scalar per lane instead of a list of readings
INTERCONNECT_CHARTS = (
    {"section": "flaps",
     "stem": "link_flap",
     "title": "Link flap count by interconnect",
     "ylabel": "Flaps",
     "metric": "link flap",
     "kinds": ("bar",),
     "field": "count"},
    {"section": "ber",
     "stem": "pre_fec_ber",
     "title": "Pre-FEC BER by interconnect ({ber_source})",
     "ylabel": "Pre-FEC BER",
     "metric": "BER",
     "kinds": ("box", "dot"),
     "drop_at_or_above": SATURATED_BER},
    {"section": "tcode",
     "stem": "tcode",
     "title": "T-Code by interconnect",
     "ylabel": "T-Code",
     "metric": "T-Code",
     "kinds": ("dot",)},
    {"section": "uncorrected_cw",
     "stem": "uncorrected_cw",
     "title": "Uncorrected codewords by interconnect",
     "ylabel": "Uncorrected codewords",
     "metric": "uncorrected codeword",
     "kinds": ("dot",)},
    {"section": "link_up",
     "stem": "link_up",
     "title": "Link-up time by interconnect",
     "ylabel": "Seconds",
     "metric": "link-up",
     "kinds": ("dot",)},
)


def ensure_output_dir(out_dir):
    Path(out_dir).mkdir(parents=True, exist_ok=True)

def clear_output_dir(out_dir):
    # a chart left over from an earlier run is indistinguishable from a fresh one, and
    # the deck builder reads whatever is in here
    out_dir = Path(out_dir)
    ensure_output_dir(out_dir)
    removed = 0
    for path in out_dir.glob("*.png"):
        path.unlink()
        removed = removed + 1
    if removed:
        print(f"  Cleared {removed} chart(s) from {out_dir.name}/")

def output_path(filename, out_dir):
    ensure_output_dir(out_dir)
    return Path(out_dir) / filename

def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def _topology_key(record):
    """One interconnect as (switch, port, lane), in the measurement side's spelling.

    interconnects.yml writes the switch as 'SW0' and the port-lane as the single string
    '1-1'; a capture writes '0', 1, 1 from its TreeL1/L2/L3 columns.
    """
    switch = str(record["Rx Switch"])
    if switch.upper().startswith("SW"):
        switch = switch[2:]
    port, _, lane = str(record["Rx Port-Lane"]).partition("-")
    return switch, int(port), int(lane)


def build_interconnect_x_axis(interconnects):
    keys = []
    labels = []
    for record in interconnects:
        keys.append(_topology_key(record))
        labels.append(record["FEC-BER / T-Code x-axis label"])
    return keys, labels


def derive_x_axis(measurements):
    """An x axis built from what was measured, for a rack with no topology file.

    A topology gives better labels and fixes the order, but it is not always available -
    racks ship their wiring in several formats. Without one, every lane that was measured
    still gets charted; only the naming is poorer.
    """
    keys = []
    for section in ("ber", "tcode", "uncorrected_cw", "link_up"):
        for record in measurements.get(section) or []:
            key = (record["switch"], record["port"], record["lane"])
            if key not in keys:
                keys.append(key)
    keys.sort(key=lambda k: (str(k[0]), k[1], k[2]))
    labels = []
    for switch, port, lane in keys:
        labels.append(f"{switch} {port}-{lane}")
    return keys, labels


def build_switch_x_axis(interconnects):
    keys = []
    for record in interconnects:
        switch, port, lane = _topology_key(record)
        if switch not in keys:
            keys.append(switch)
    labels = []
    for switch in keys:
        labels.append(f"switch {switch}")
    return keys, labels


def _lane_values(records, drop_at_or_above=None):
    """Per-lane records -> {(switch, port, lane): [values]} for the box and dot plots.

    A port that is not broken out reports lane 0, which the topology calls lane 1, so it
    is indexed under both - otherwise every un-broken-out port silently loses its label.

    The converter keeps every reading the capture made. Saturated ones are dropped here,
    because that is a judgement about what the chart should show rather than a fact about
    what was recorded.
    """
    values = {}
    dropped = 0
    for record in records or []:
        key = (record["switch"], record["port"], record["lane"])
        clean = []
        for value in record["values"]:
            if value is None:
                continue
            if drop_at_or_above is not None and value >= drop_at_or_above:
                dropped = dropped + 1
                continue
            clean.append(value)
        values[key] = clean
        if record["lane"] == 0:
            values[(record["switch"], record["port"], 1)] = clean
    if dropped:
        print(f"  Info: ignored {dropped} reading(s) at or above {drop_at_or_above} as "
              f"saturated; a link that wrong is a coin flip, not a measurement.")
    return values


def _lane_scalars(records, field):
    """Per-lane records -> {(switch, port, lane): number} for the bar chart.

    Some metrics are one number per lane rather than a list of readings - a flap count
    is a total, not a distribution - so there is nothing to box or scatter.
    """
    values = {}
    for record in records or []:
        key = (record["switch"], record["port"], record["lane"])
        values[key] = record[field]
        # a port that is not broken out reports lane 0 where the topology says lane 1
        if record["lane"] == 0:
            values[(record["switch"], record["port"], 1)] = record[field]
    return values


def _flaps_per_switch(records):
    """Per-lane flap records -> {switch: total}, summed across that switch's lanes."""
    totals = {}
    for record in records or []:
        switch = record["switch"]
        if switch not in totals:
            totals[switch] = 0
        totals[switch] = totals[switch] + record["count"]
    return totals


def _break_at_seams(points, seams):
    """Insert a NaN gap where one merged run ends and the next begins.

    Merged runs sit on a shared clock, so a later run starts hours after the first one
    stopped. Nothing was measured in between, and joining the two would draw a steady
    trend that never happened. matplotlib skips NaN, so the line simply stops and
    restarts while both halves keep their real times.
    """
    if not seams:
        return points
    remaining = sorted(seams)
    broken = []
    for hours, value in points:
        while remaining and hours >= remaining[0]:
            broken.append((float("nan"), float("nan")))
            remaining.pop(0)
        broken.append((hours, value))
    return broken


def _temps_per_port(records, switch, seams):
    """One switch's module temperatures -> {port: [(hours, celsius)]}."""
    series = {}
    for record in records or []:
        if record["switch"] != switch:
            continue
        points = []
        for hours, value in record["points"]:
            if value is not None:
                points.append((hours, value))
        series[record["port"]] = _break_at_seams(points, seams)
    return series


def _sensor_points(records, switch, seams):
    for record in records or []:
        if record["switch"] == switch:
            points = [(hours, value) for hours, value in record["points"]]
            return _break_at_seams(points, seams)
    return None


def _report_unmatched(keys, values, what):
    missing = 0
    for key in keys:
        if key not in values:
            missing = missing + 1
    if missing:
        print(f"  Warning: {missing} of {len(keys)} interconnects have no {what} "
              f"measurement; they will render as gaps.")


def _pages(keys, labels, per_page):
    """Split a long x axis into chart-sized pages.

    A rack can have hundreds of interconnects. Drawn on one axis at the per-entry width
    the style allows, 640 of them is a 224-inch strip - which, shrunk onto a slide, puts
    every label below a pixel. Paging keeps each chart at a readable size.
    """
    pages = []
    for start in range(0, len(keys), per_page):
        pages.append((keys[start:start + per_page], labels[start:start + per_page]))
    return pages


def _by_switch(keys, labels):
    """Split the interconnect axis into one axis per switch, in first-seen order.

    Charting all 640 interconnects on one axis puts page breaks at arbitrary places and
    leaves the chart belonging to no switch in particular. Per switch, a page boundary
    means something, and the chart can sit on that switch's slide beside its temperature.
    """
    grouped = {}
    for key, label in zip(keys, labels):
        switch = key[0]
        if switch not in grouped:
            grouped[switch] = ([], [])
        grouped[switch][0].append(key)
        grouped[switch][1].append(label)
    return grouped


def _draw_interconnect_charts(measurements, meta, keys, labels, out_dir):
    """Every chart whose x axis is the interconnect list. Returns manifest entries."""
    drawn = []
    per_page = plots.style["MAX_ENTRIES_PER_PAGE"]
    for spec in INTERCONNECT_CHARTS:
        records = measurements[spec["section"]]
        if records is None:
            continue
        if spec.get("field"):
            values = _lane_scalars(records, spec["field"])
        else:
            values = _lane_values(records, spec.get("drop_at_or_above"))
        _report_unmatched(keys, values, spec["metric"])
        base = spec["title"].format(**meta)

        for switch, (switch_keys, switch_labels) in _by_switch(keys, labels).items():
            pages = _pages(switch_keys, switch_labels, per_page)
            for number, (page_keys, page_labels) in enumerate(pages, start=1):
                title = f"{base} — switch {switch}"
                suffix = ""
                if len(pages) > 1:
                    title = f"{title} (page {number} of {len(pages)})"
                    suffix = f"_p{number}"
                for kind in spec["kinds"]:
                    name = f"{spec['stem']}_{kind}_sw{switch}{suffix}.png"
                    CHART_KINDS[kind](values, page_keys, page_labels, title=title,
                                      ylabel=spec["ylabel"],
                                      out_path=output_path(name, out_dir))
                    # scope puts this on that switch's slides, beside its temperature
                    drawn.append({"file": name, "title": title, "scope": switch,
                                  "wide": True})
    return drawn


def _draw_temperature_charts(measurements, meta, switch_keys, seams, out_dir):
    """One chart per switch: its ports are the lines, its board sensor an extra one.

    Switches cannot share an axis here - each has its own ports, its own sensor, and
    its own optics rating for the limit line. Returns manifest entries.
    """
    drawn = []
    for switch in switch_keys:
        temps = _temps_per_port(measurements["temps"], switch, seams)
        if not temps:
            continue

        # a line needs two samples; with one per module there is no trend to draw and
        # the chart degrades to scattered points, which is worth saying out loud
        longest = 0
        for port in temps:
            real = [point for point in temps[port] if point[0] == point[0]]
            if len(real) > longest:
                longest = len(real)
        if longest < 2:
            print(f"  Warning: switch {switch} has a single temperature sample per "
                  f"module, so the chart shows points rather than a trend over time.")

        ports = sorted(temps)
        labels = []
        for port in ports:
            labels.append(f"port {port}")
        info = meta["switches"].get(switch) or {}
        model = info.get("device_model") or "unknown"
        name = f"temp_switch_{switch}.png"
        title = f"Module temperature over time — switch {switch} ({model})"
        plots.value_series(temps, ports, labels,
                               title=title,
                               ylabel="Temperature (°C)",
                               xlabel="Elapsed time (hours)",
                               out_path=output_path(name, out_dir),
                               spec_min=info.get("temp_min"),
                               spec_max=info.get("temp_max"),
                               overlay_points=_sensor_points(measurements["sensors"],
                                                             switch, seams),
                               overlay_label=SENSOR_LABEL)
        drawn.append({"file": name, "title": title, "scope": switch})
    return drawn


def _write_manifest(measurements_yml, meta, charts, out_dir, testcase):
    """Declare what was drawn, in the order it should be presented.

    The deck builder reads this instead of the file names, so it needs no knowledge of
    which metrics exist or how switches are named. Adding a chart type changes what
    appears in the deck without touching the deck code.
    """
    manifest = {
        "capture": Path(measurements_yml).name,
        "testcase": testcase or meta["test_type"],
        "test_type": meta["test_type"],
        "ber_source": meta["ber_source"],
        "charts": charts,
    }
    path = Path(out_dir) / MANIFEST_NAME
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(manifest, f, default_flow_style=False, sort_keys=False,
                  allow_unicode=True)
    print(f"  Wrote {len(charts)} chart(s) and {path.name}")
    return path


def _switches_in(measurements):
    """Switch ids seen in the measurements, for when there is no topology to order them."""
    switches = []
    for section in ("flaps", "temps", "ber"):
        for record in measurements.get(section) or []:
            if record["switch"] not in switches:
                switches.append(record["switch"])
    switches.sort(key=str)
    labels = []
    for switch in switches:
        labels.append(f"switch {switch}")
    return switches, labels


def generate_plots(measurements_yml, out_dir, interconnects_yml=INTERCONNECTS_YML,
                   testcase=None):
    measurements = load_yaml(measurements_yml)
    meta = measurements["meta"]
    print(f"{Path(measurements_yml).name} ({meta['test_type']}, BER from "
          f"{meta['ber_source']})")
    clear_output_dir(out_dir)

    if interconnects_yml and Path(interconnects_yml).exists():
        interconnects = load_yaml(interconnects_yml)
        interconnect_keys, interconnect_labels = build_interconnect_x_axis(interconnects)
        switch_keys, switch_labels = build_switch_x_axis(interconnects)
    else:
        print("  Info: no topology file; labelling the x axis from the measurements "
              "themselves, so entries are named rather than described.")
        interconnect_keys, interconnect_labels = derive_x_axis(measurements)
        switch_keys, switch_labels = _switches_in(measurements)

    charts = []
    if measurements["flaps"] is not None:
        title = "Link flaps by switch"
        plots.bargraph(_flaps_per_switch(measurements["flaps"]),
                       switch_keys, switch_labels,
                       title=title, ylabel="Flaps",
                       out_path=output_path("flaps.png", out_dir))
        charts.append({"file": "flaps.png", "title": title, "scope": "all"})

    charts.extend(_draw_interconnect_charts(measurements, meta, interconnect_keys,
                                            interconnect_labels, out_dir))

    seams = meta.get("seams") or []
    if seams:
        print(f"  Info: merged capture; lines break at {len(seams)} run boundary "
              f"({', '.join(f'{s:.1f}h' for s in seams)}) where nothing was measured.")
    charts.extend(_draw_temperature_charts(measurements, meta, switch_keys,
                                           seams, out_dir))

    # charts are drawn metric by metric, but a reader wants one switch at a time. A
    # stable sort on scope regroups them without disturbing the metric order within a
    # switch, so each switch's pages arrive followed by its temperature chart.
    order = {"all": 0}
    charts.sort(key=lambda chart: (order.get(chart["scope"], 1), str(chart["scope"])))
    return _write_manifest(measurements_yml, meta, charts, out_dir, testcase)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("measurements", nargs="?",
                        default=MEASUREMENTS_DIR / "soak_sample.yml",
                        help="measurement yaml to chart")
    parser.add_argument("-o", "--out-dir",
                        help="where the charts go (default: output/<capture name>/)")
    args = parser.parse_args()
    # named after the capture, the same rule main.py uses for its testcases
    out_dir = args.out_dir or OUTPUT_DIR / Path(args.measurements).stem
    generate_plots(args.measurements, out_dir)
