from pathlib import Path
import yaml

from plotting import Plots

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
INTERCONNECTS_YML = PROJECT_ROOT / "interconnects" / "interconnects.yml"
MEASUREMENTS_DIR = PROJECT_ROOT / "data" / "output"
# a bit error rate of 0.5 means half the bits are wrong, which is noise rather than a
# degraded link; readings at or above it are the counter saturating
SATURATED_BER = 0.5

plots = Plots()


def ensure_output_dir():
    OUTPUT_DIR.mkdir(exist_ok=True)

def clear_output_dir():
    # a chart left over from an earlier run is indistinguishable from a fresh one, and
    # the deck builder reads whatever is in here
    ensure_output_dir()
    removed = 0
    for path in OUTPUT_DIR.glob("*.png"):
        path.unlink()
        removed = removed + 1
    if removed:
        print(f"  Cleared {removed} chart(s) from {OUTPUT_DIR.name}/")

def output_path(filename):
    ensure_output_dir()
    return OUTPUT_DIR / filename

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


def generate_plots(measurements_yml):
    measurements = load_yaml(measurements_yml)
    interconnects = load_yaml(INTERCONNECTS_YML)
    meta = measurements["meta"]
    print(f"{Path(measurements_yml).name} ({meta['test_type']}, BER from "
          f"{meta['ber_source']})")
    clear_output_dir()

    interconnect_keys, interconnect_labels = build_interconnect_x_axis(interconnects)
    switch_keys, switch_labels = build_switch_x_axis(interconnects)
    spec = meta["spec"]

    if measurements["flaps"] is not None:
        plots.bargraph(_flaps_per_switch(measurements["flaps"]),
                       switch_keys, switch_labels,
                       title="Link flaps by switch", ylabel="Flaps",
                       out_path=output_path("flaps.png"))

    if measurements["ber"] is not None:
        ber = _lane_values(measurements["ber"], drop_at_or_above=SATURATED_BER)
        _report_unmatched(interconnect_keys, ber, "BER")
        title = f"Pre-FEC BER by interconnect ({meta['ber_source']})"
        plots.box_plot(ber, interconnect_keys, interconnect_labels,
                       title=title, ylabel="Pre-FEC BER",
                       out_path=output_path("pre_fec_ber_box.png"))
        plots.dot_plot(ber, interconnect_keys, interconnect_labels,
                       title=title, ylabel="Pre-FEC BER",
                       out_path=output_path("pre_fec_ber_dot.png"))

    if measurements["tcode"] is not None:
        tcode = _lane_values(measurements["tcode"])
        _report_unmatched(interconnect_keys, tcode, "T-Code")
        plots.dot_plot(tcode, interconnect_keys, interconnect_labels,
                       title="T-Code by interconnect", ylabel="T-Code",
                       out_path=output_path("tcode_dot.png"))

    if measurements["uncorrected_cw"] is not None:
        plots.dot_plot(_lane_values(measurements["uncorrected_cw"]),
                       interconnect_keys, interconnect_labels,
                       title="Uncorrected codewords by interconnect",
                       ylabel="Uncorrected codewords",
                       out_path=output_path("uncorrected_cw_dot.png"))

    if measurements["link_up"] is not None:
        plots.dot_plot(_lane_values(measurements["link_up"]),
                       interconnect_keys, interconnect_labels,
                       title="Link-up time by interconnect", ylabel="Seconds",
                       out_path=output_path("link_up_dot.png"))

    # one temperature chart per switch: the lines are that switch's ports, and the
    # board sensor is a single extra line, so the switches cannot share an axis
    seams = meta.get("seams") or []
    if seams:
        print(f"  Info: merged capture; lines break at {len(seams)} run boundary "
              f"({', '.join(f'{s:.1f}h' for s in seams)}) where nothing was measured.")

    for switch in switch_keys:
        temps = _temps_per_port(measurements["temps"], switch, seams)
        if not temps:
            continue

        # a line needs two samples; with one per module there is no trend to draw and
        # the chart degrades to scattered points, which is worth saying out loud
        longest = 0
        for port in temps:
            real = [p for p in temps[port] if p[0] == p[0]]
            if len(real) > longest:
                longest = len(real)
        if longest < 2:
            print(f"  Warning: switch {switch} has a single temperature sample per "
                  f"module, so the chart shows points rather than a trend over time.")

        ports = sorted(temps)
        labels = []
        for port in ports:
            labels.append(f"port {port}")
        model = (meta["switches"].get(switch) or {}).get("device_model") or "unknown"
        plots.temp_time_series(temps, ports, labels,
                               title=f"Module temperature over time — switch {switch} ({model})",
                               ylabel="Temperature (°C)",
                               xlabel="Elapsed time (hours)",
                               out_path=output_path(f"temp_switch_{switch}.png"),
                               spec_min=spec["temp_min"], spec_max=spec["temp_max"],
                               sensor_points=_sensor_points(measurements["sensors"],
                                                            switch, seams))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        generate_plots(sys.argv[1])
    else:
        generate_plots(MEASUREMENTS_DIR / "soak_sample.yml")
