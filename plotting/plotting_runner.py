"""Render every chart for one capture, from the yaml the converters produce.

interconnects.yml supplies the x axis, the measurement yaml the values. The two spell
switches and ports differently, so topology keys are normalised onto the measurement
side's (see _topology_key).

Two independent things vary between charts:

  axis   what the x ticks are - switches, interconnects, or elapsed time
  scope  what one file covers - the whole rack ("all") or one switch

Interconnects are the default axis, so a name says "by_interconnect" only where another
chart draws the same metric differently. Scope appears in no name: _draw_per_switch
gives every interconnect chart one file per switch. It lands in the manifest, which is
all the deck builder reads - it groups slides on scope without knowing what a metric is.

Functions run in pipeline order, each chart family one block: reshape helper, then the
draw_* that uses it. Every draw_* follows the same recipe:

1. guard:    if records is None: return []
2. reshape:  records -> {(switch, port, lane): value}
3. report:   _report_unmatched, for interconnects with nothing measured
4. draw:     _draw_per_switch - one chart per switch, split when a switch has many lanes
5. record:   return one manifest entry per chart drawn
"""

from pathlib import Path
import yaml

from plotting import Plots

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
INTERCONNECTS_YML = PROJECT_ROOT / "interconnects" / "interconnects.yml"
MEASUREMENTS_DIR = PROJECT_ROOT / "data" / "output"
MANIFEST_NAME = "manifest.yml"
SATURATED_BER = 0.5  # BER >= 0.5 is the counter saturating, not a real reading
SENSOR_LABEL = "Board Sensor"

plots = Plots()


# --- files ---------------------------------------------------------------------

def ensure_output_dir(out_dir):
    Path(out_dir).mkdir(parents=True, exist_ok=True)

def clear_output_dir(out_dir):
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


# --- the x axis, built once and shared by every chart ----------------------------

def _topology_key(record):
    # interconnects.yml: 'SW0', '1-1' -> measurement side's ('0', 1, 1)
    switch = str(record["Rx Switch"])
    if switch.upper().startswith("SW"):
        switch = switch[2:]
    port, _, lane = str(record["Rx Port-Lane"]).partition("-")
    return switch, int(port), int(lane)


def build_interconnect_axis(interconnects):
    keys = []
    labels = []
    for record in interconnects:
        keys.append(_topology_key(record))
        labels.append(record["FEC-BER / T-Code x-axis label"])
    return keys, labels


def build_switch_axis(interconnects):
    keys = []
    for record in interconnects:
        switch, port, lane = _topology_key(record)
        if switch not in keys:
            keys.append(switch)
    labels = []
    for switch in keys:
        labels.append(f"switch {switch}")
    return keys, labels


def build_port_vendors(interconnects):
    """{(switch, port): vendor} - one optic per port, so every lane of it agrees."""
    vendors = {}
    for record in interconnects:
        switch, port, lane = _topology_key(record)
        vendors[(switch, port)] = record["Rx Vendor"]
    return vendors


def _axis_order(key):
    switch, port, lane = key
    return (str(switch), port, lane)


def build_measured_axis(measurements):
    """x axis from what was measured, for a rack with no topology file."""
    keys = []
    for section in ("ber", "tcode", "uncorrected_cw", "link_up"):
        records = measurements.get(section)
        if records is None:
            continue
        for record in records:
            key = (record["switch"], record["port"], record["lane"])
            if key not in keys:
                keys.append(key)
    keys.sort(key=_axis_order)
    labels = []
    for switch, port, lane in keys:
        labels.append(f"{switch} {port}-{lane}")
    return keys, labels


def build_measured_switches(measurements):
    """Switch axis from what was measured, when there is no topology to order it."""
    keys = []
    for section in ("flaps", "temps", "ber"):
        records = measurements.get(section)
        if records is None:
            continue
        for record in records:
            if record["switch"] not in keys:
                keys.append(record["switch"])
    keys.sort(key=str)
    labels = []
    for switch in keys:
        labels.append(f"switch {switch}")
    return keys, labels


# --- shared by every chart: axis check, per-switch split, paging -----------------

def _report_unmatched(keys, values, what):
    missing = 0
    for key in keys:
        if key not in values:
            missing = missing + 1
    if missing:
        print(f"  Warning: {missing} of {len(keys)} interconnects have no {what} "
              f"measurement; they will render as gaps.")


def _split_by_switch(keys, labels):
    """[(switch, keys, labels)] - one x axis per switch, in first-seen order."""
    order = []
    keys_by_switch = {}
    labels_by_switch = {}
    for i in range(len(keys)):
        switch = keys[i][0]
        if switch not in keys_by_switch:
            order.append(switch)
            keys_by_switch[switch] = []
            labels_by_switch[switch] = []
        keys_by_switch[switch].append(keys[i])
        labels_by_switch[switch].append(labels[i])

    axes = []
    for switch in order:
        axes.append((switch, keys_by_switch[switch], labels_by_switch[switch]))
    return axes


def _chunks(keys, labels):
    """Split one switch's x axis into chart-sized chunks."""
    per_chart = plots.style["MAX_X_AXIS_ENTRIES_PER_CHART"]
    chunks = []
    for start in range(0, len(keys), per_chart):
        chunks.append((keys[start:start + per_chart], labels[start:start + per_chart]))
    return chunks


def _draw_per_switch(draw, values, keys, labels, stem, metric, title, ylabel, out_dir):
    """One chart per switch, split again when a switch has more lanes than fit on an axis.

    A split chart is numbered "(2 of 4)" with no noun. The deck heading above it already
    says "page N of M" about slides, and two different counts calling themselves pages on
    one slide is how you make a reader distrust both.
    """
    drawn = []
    for switch, switch_keys, switch_labels in _split_by_switch(keys, labels):
        chunks = _chunks(switch_keys, switch_labels)
        number = 1
        for chunk_keys, chunk_labels in chunks:
            chart_title = f"{title} — switch {switch}"
            name = f"{stem}_sw{switch}.png"
            if len(chunks) > 1:
                chart_title = f"{chart_title} ({number} of {len(chunks)})"
                name = f"{stem}_sw{switch}_p{number}.png"
            draw(values, chunk_keys, chunk_labels, title=chart_title, ylabel=ylabel,
                 out_path=output_path(name, out_dir))
            drawn.append({"file": name, "title": chart_title, "scope": switch,
                          "metric": metric})
            number = number + 1
    return drawn


# --- flaps on a switch axis ------------------------------------------------------

def _totals_per_switch(records):
    """Per-lane flap records -> {switch: total}, summed across that switch's lanes."""
    totals = {}
    for record in records:
        switch = record["switch"]
        if switch not in totals:
            totals[switch] = 0
        totals[switch] = totals[switch] + record["count"]
    return totals


def draw_flaps_by_switch(measurements, keys, labels, out_dir):
    """One bar per switch: how many flaps it saw across all its lanes."""
    records = measurements["flaps"]
    if records is None:
        return []
    title = "Link flaps by switch"
    plots.bargraph(_totals_per_switch(records), keys, labels,
                   title=title, ylabel="Flaps",
                   out_path=output_path("flaps.png", out_dir))
    return [{"file": "flaps.png", "title": title, "scope": "all",
             "metric": "Link flaps by switch"}]


# --- flaps on the interconnect axis ----------------------------------------------

def _lane_scalars(records, field):
    """Per-lane records -> {(switch, port, lane): number} for the bar chart."""
    values = {}
    for record in records:
        key = (record["switch"], record["port"], record["lane"])
        values[key] = record[field]
        if record["lane"] == 0:  # un-broken-out port; topology calls it lane 1
            values[(record["switch"], record["port"], 1)] = record[field]
    return values


def draw_flaps_by_interconnect(measurements, keys, labels, out_dir):
    records = measurements["flaps"]
    if records is None:
        return []
    values = _lane_scalars(records, "count")
    _report_unmatched(keys, values, "link flap")
    return _draw_per_switch(plots.bargraph, values, keys, labels,
                            stem="link_flap_bar", metric="Link flap count",
                            title="Link flap count by interconnect",
                            ylabel="Flaps", out_dir=out_dir)


# --- the four metrics with many readings per lane --------------------------------

def _lane_values(records, drop_at_or_above=None):
    """Per-lane records -> {(switch, port, lane): [values]} for the box and dot plots."""
    values = {}
    dropped = 0
    for record in records:
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


def draw_ber(measurements, meta, keys, labels, out_dir):
    records = measurements["ber"]
    if records is None:
        return []
    values = _lane_values(records, drop_at_or_above=SATURATED_BER)
    _report_unmatched(keys, values, "BER")
    return _draw_per_switch(plots.box_plot, values, keys, labels,
                            stem="pre_fec_ber_box", metric="Pre-FEC BER",
                            title=f"Pre-FEC BER by interconnect ({meta['ber_source']})",
                            ylabel="Pre-FEC BER", out_dir=out_dir)


def draw_tcode(measurements, keys, labels, out_dir):
    records = measurements["tcode"]
    if records is None:
        return []
    values = _lane_values(records)
    _report_unmatched(keys, values, "T-Code")
    return _draw_per_switch(plots.dot_plot, values, keys, labels,
                            stem="tcode_dot", metric="T-Code",
                            title="T-Code by interconnect",
                            ylabel="T-Code", out_dir=out_dir)


def draw_uncorrected_cw(measurements, keys, labels, out_dir):
    records = measurements["uncorrected_cw"]
    if records is None:
        return []
    values = _lane_values(records)
    _report_unmatched(keys, values, "uncorrected codeword")
    return _draw_per_switch(plots.dot_plot, values, keys, labels,
                            stem="uncorrected_cw_dot", metric="Uncorrected codewords",
                            title="Uncorrected codewords by interconnect",
                            ylabel="Uncorrected codewords", out_dir=out_dir)


def draw_link_up(measurements, keys, labels, out_dir):
    records = measurements["link_up"]
    if records is None:
        return []
    values = _lane_values(records)
    _report_unmatched(keys, values, "link-up")
    return _draw_per_switch(plots.dot_plot, values, keys, labels,
                            stem="link_up_dot", metric="Link-up time",
                            title="Link-up time by interconnect",
                            ylabel="Seconds", out_dir=out_dir)


# --- temperature over time, the one chart with an x axis of its own --------------

def _break_at_seams(points, seams):
    """Insert a NaN gap at each seam, so a merged run's line doesn't span the gap where
    nothing was measured. matplotlib skips NaN, so the line just stops and restarts."""
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
    if records is None:
        return {}
    series = {}
    for record in records:
        if record["switch"] != switch:
            continue
        points = []
        for hours, value in record["points"]:
            if value is not None:
                points.append((hours, value))
        series[record["port"]] = _break_at_seams(points, seams)
    return series


def _sensor_points(records, switch, seams):
    if records is None:
        return None
    for record in records:
        if record["switch"] == switch:
            points = []
            for hours, value in record["points"]:
                points.append((hours, value))
            return _break_at_seams(points, seams)
    return None


def _switch_info(meta, switch):
    """(limits, model) for one switch. Both missing is normal for an unknown device."""
    info = meta["switches"].get(switch)
    if info is None:
        info = {}
    model = info.get("device_model")
    if model is None:
        model = "unknown"
    return info, model


def _report_flat_series(switch, temps):
    # a line needs 2+ samples; warn when it'll render as scattered points instead
    longest = 0
    for port in temps:
        real = []
        for point in temps[port]:
            if point[0] == point[0]:
                real.append(point)
        if len(real) > longest:
            longest = len(real)
    if longest < 2:
        print(f"  Warning: switch {switch} has a single temperature sample per "
              f"module, so the chart shows points rather than a trend over time.")


def draw_temperature_over_time(measurements, meta, keys, seams, out_dir):
    """One chart per switch: its ports are the lines, its board sensor an extra one."""
    drawn = []
    for switch in keys:
        temps = _temps_per_port(measurements["temps"], switch, seams)
        if not temps:
            continue
        _report_flat_series(switch, temps)

        ports = sorted(temps)
        labels = []
        for port in ports:
            labels.append(f"port {port}")
        info, model = _switch_info(meta, switch)
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
        drawn.append({"file": name, "title": title, "scope": switch,
                      "metric": "Module temperature over time"})
    return drawn


# --- temperature per port, the same readings on a category axis ------------------

def _temp_readings_per_port(records, switch):
    """One switch's module temperatures -> {port: [celsius]}, timestamps dropped.

    Deliberately not _temps_per_port: that one inserts NaN at run seams so the line
    chart breaks, and one NaN makes every quartile of a box NaN.
    """
    if records is None:
        return {}
    readings = {}
    for record in records:
        if record["switch"] != switch:
            continue
        values = []
        for hours, value in record["points"]:
            if value is not None:
                values.append(value)
        readings[record["port"]] = values
    return readings


def draw_temperature_per_port(measurements, meta, keys, vendors, out_dir):
    """One chart per switch: a box per port spanning the range that port ran through.

    Soak cycles hot and cold, so a box here is bimodal - it stretches from the cold
    mode to the hot one rather than describing a spread around a middle.
    """
    drawn = []
    for switch in keys:
        readings = _temp_readings_per_port(measurements["temps"], switch)
        if not readings:
            continue
        ports = sorted(readings)
        labels = []
        for port in ports:
            vendor = vendors.get((switch, port))
            if vendor is None:
                labels.append(f"port {port}")
            else:
                labels.append(f"{port}_{vendor}")
        info, model = _switch_info(meta, switch)
        name = f"temp_per_port_sw{switch}.png"
        title = f"Module temperature per port — switch {switch} ({model})"
        plots.box_plot(readings, ports, labels,
                       title=title,
                       ylabel="Temperature (°C)",
                       out_path=output_path(name, out_dir),
                       spec_min=info.get("temp_min"),
                       spec_max=info.get("temp_max"))
        drawn.append({"file": name, "title": title, "scope": switch,
                      "metric": "Module temperature per port"})
    return drawn


# --- the manifest, written once every chart is on disk ---------------------------

def _sort_by_scope(charts):
    """Reorder so each switch's charts arrive together, the 'all' ones first.

    Charts keep the order the draw_* functions produced them in, within each switch.
    """
    ordered = []
    for chart in charts:
        if chart["scope"] == "all":
            ordered.append(chart)

    switches = []
    for chart in charts:
        if chart["scope"] != "all" and chart["scope"] not in switches:
            switches.append(chart["scope"])
    switches.sort(key=str)

    for switch in switches:
        for chart in charts:
            if chart["scope"] == switch:
                ordered.append(chart)
    return ordered


def _write_manifest(measurements_yml, meta, charts, out_dir, testcase):
    """Declare what was drawn, in the order it should be presented."""
    if testcase is None:
        testcase = meta["test_type"]
    manifest = {
        "capture": Path(measurements_yml).name,
        "testcase": testcase,
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


# --- the pipeline ----------------------------------------------------------------

def generate_plots(measurements_yml, out_dir, interconnects_yml=INTERCONNECTS_YML,
                   testcase=None):
    measurements = load_yaml(measurements_yml)
    meta = measurements["meta"]
    print(f"{Path(measurements_yml).name} ({meta['test_type']}, BER from "
          f"{meta['ber_source']})")
    clear_output_dir(out_dir)

    if interconnects_yml and Path(interconnects_yml).exists():
        interconnects = load_yaml(interconnects_yml)
        keys, labels = build_interconnect_axis(interconnects)
        switch_keys, switch_labels = build_switch_axis(interconnects)
        vendors = build_port_vendors(interconnects)
    else:
        print("  Info: no topology file; labelling the x axis from the measurements "
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

    charts = []
    charts.extend(draw_flaps_by_switch(measurements, switch_keys, switch_labels, out_dir))
    charts.extend(draw_flaps_by_interconnect(measurements, keys, labels, out_dir))
    charts.extend(draw_ber(measurements, meta, keys, labels, out_dir))
    charts.extend(draw_tcode(measurements, keys, labels, out_dir))
    charts.extend(draw_uncorrected_cw(measurements, keys, labels, out_dir))
    charts.extend(draw_link_up(measurements, keys, labels, out_dir))
    charts.extend(draw_temperature_over_time(measurements, meta, switch_keys, seams, out_dir))
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
