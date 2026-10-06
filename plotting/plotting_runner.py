from pathlib import Path
import yaml

from plotting import Plots

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
INTERCONNECTS_YML = PROJECT_ROOT / "interconnects" / "interconnects.yml"
MEASUREMENTS_DIR = PROJECT_ROOT / "data" / "output"
MANIFEST_NAME = "manifest.yml"
# a bit error rate of 0.5 means half the bits are wrong, which is noise rather than a
# degraded link; readings at or above it are the counter saturating
SATURATED_BER = 0.5

plots = Plots()

CHART_KINDS = {"box": plots.box_plot, "dot": plots.dot_plot}

# Every chart drawn against the interconnect axis, declared rather than hand-written.
# Adding a metric is a row here; the loop below needs no change, and neither does
# anything downstream that wants to know which charts a run produces.
#   section          the measurement yaml key, null when the capture lacks it
#   stem + kind      the file name, e.g. pre_fec_ber_box.png
#   title            formatted against meta, so it can name the instrument used
INTERCONNECT_CHARTS = (
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


def ensure_output_dir(out_dir=OUTPUT_DIR):
    Path(out_dir).mkdir(parents=True, exist_ok=True)

def clear_output_dir(out_dir=OUTPUT_DIR):
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

def output_path(filename, out_dir=OUTPUT_DIR):
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


def _draw_interconnect_charts(measurements, meta, keys, labels, out_dir):
    """Every chart whose x axis is the interconnect list. Returns manifest entries."""
    drawn = []
    for spec in INTERCONNECT_CHARTS:
        records = measurements[spec["section"]]
        if records is None:
            continue
        values = _lane_values(records, spec.get("drop_at_or_above"))
        _report_unmatched(keys, values, spec["metric"])
        title = spec["title"].format(**meta)
        for kind in spec["kinds"]:
            name = f"{spec['stem']}_{kind}.png"
            CHART_KINDS[kind](values, keys, labels, title=title, ylabel=spec["ylabel"],
                              out_path=output_path(name, out_dir))
            drawn.append({"file": name, "title": title, "scope": "all"})
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
        plots.temp_time_series(temps, ports, labels,
                               title=title,
                               ylabel="Temperature (°C)",
                               xlabel="Elapsed time (hours)",
                               out_path=output_path(name, out_dir),
                               spec_min=info.get("temp_min"),
                               spec_max=info.get("temp_max"),
                               sensor_points=_sensor_points(measurements["sensors"],
                                                            switch, seams))
        drawn.append({"file": name, "title": title, "scope": switch})
    return drawn


def _write_manifest(measurements_yml, meta, charts, out_dir):
    """Declare what was drawn, in the order it should be presented.

    The deck builder reads this instead of the file names, so it needs no knowledge of
    which metrics exist or how switches are named. Adding a chart type changes what
    appears in the deck without touching the deck code.
    """
    manifest = {
        "capture": Path(measurements_yml).name,
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


def generate_plots(measurements_yml, out_dir=OUTPUT_DIR):
    measurements = load_yaml(measurements_yml)
    interconnects = load_yaml(INTERCONNECTS_YML)
    meta = measurements["meta"]
    print(f"{Path(measurements_yml).name} ({meta['test_type']}, BER from "
          f"{meta['ber_source']})")
    clear_output_dir(out_dir)

    interconnect_keys, interconnect_labels = build_interconnect_x_axis(interconnects)
    switch_keys, switch_labels = build_switch_x_axis(interconnects)

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

    return _write_manifest(measurements_yml, meta, charts, out_dir)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        generate_plots(sys.argv[1])
    else:
        generate_plots(MEASUREMENTS_DIR / "soak_sample.yml")
