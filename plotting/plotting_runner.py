"""Render every chart for one capture, from the yaml the converters produce.

interconnects.yml supplies the x axis, the measurement yaml supplies the values. The two
name switches and ports differently, so the topology side is normalised onto the
measurement side's keys (see _topology_key). A manifest declares what was drawn, so the
deck builder needs no knowledge of switches or metrics.

Functions appear in the order the pipeline runs them, and each chart family is one block:
its reshape helper, then the draw_* that consumes it.

Every draw_* function follows the same recipe:

1. guard:    if records is None: return []
2. reshape:  records -> {(switch, port, lane): value}
3. report:   _report_unmatched, for interconnects with nothing measured
4. draw:     _draw_paged - one chart per switch, paged when a switch has many lanes
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


def _axis_order(key):
    switch, port, lane = key
    return (str(switch), port, lane)


def build_measured_axis(measurements):
    """x axis from what was measured, for a rack with no topology file."""
    keys = []
    for section in ("ber", "tcode", "uncorrected_cw", "link_up"):
        for record in measurements.get(section) or []:
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
        for record in measurements.get(section) or []:
            if record["switch"] not in keys:
                keys.append(record["switch"])
    keys.sort(key=str)
    labels = []
    for switch in keys:
        labels.append(f"switch {switch}")
    return keys, labels


# --- what every draw_* leans on --------------------------------------------------

def _report_unmatched(keys, values, what):
    missing = 0
    for key in keys:
        if key not in values:
            missing = missing + 1
    if missing:
        print(f"  Warning: {missing} of {len(keys)} interconnects have no {what} "
              f"measurement; they will render as gaps.")


def _by_switch(keys, labels):
    """[(switch, keys, labels)] - one x axis per switch, in first-seen order."""
    grouped = {}
    for key, label in zip(keys, labels):
        switch = key[0]
        if switch not in grouped:
            grouped[switch] = ([], [])
        grouped[switch][0].append(key)
        grouped[switch][1].append(label)

    axes = []
    for switch in grouped:
        switch_keys, switch_labels = grouped[switch]
        axes.append((switch, switch_keys, switch_labels))
    return axes


def _pages(keys, labels):
    """Split one switch's x axis into chart-sized pages."""
    per_page = plots.style["MAX_ENTRIES_PER_PAGE"]
    pages = []
    for start in range(0, len(keys), per_page):
        pages.append((keys[start:start + per_page], labels[start:start + per_page]))
    return pages


def _draw_paged(draw, values, keys, labels, stem, title, ylabel, out_dir):
    """One chart per switch, paged when a switch has more lanes than fit on an axis."""
    drawn = []
    for switch, switch_keys, switch_labels in _by_switch(keys, labels):
        pages = _pages(switch_keys, switch_labels)
        for number, (page_keys, page_labels) in enumerate(pages, start=1):
            page_title = f"{title} — switch {switch}"
            name = f"{stem}_sw{switch}.png"
            if len(pages) > 1:
                page_title = f"{page_title} (page {number} of {len(pages)})"
                name = f"{stem}_sw{switch}_p{number}.png"
            draw(values, page_keys, page_labels, title=page_title, ylabel=ylabel,
                 out_path=output_path(name, out_dir))
            drawn.append({"file": name, "title": page_title, "scope": switch,
                          "wide": True})
    return drawn


# --- flaps, summarised per switch ------------------------------------------------

def _flaps_per_switch(records):
    """Per-lane flap records -> {switch: total}, summed across that switch's lanes."""
    totals = {}
    for record in records or []:
        switch = record["switch"]
        if switch not in totals:
            totals[switch] = 0
        totals[switch] = totals[switch] + record["count"]
    return totals


def draw_flap_summary(measurements, keys, labels, out_dir):
    """One bar per switch: how many flaps it saw across all its lanes."""
    records = measurements["flaps"]
    if records is None:
        return []
    title = "Link flaps by switch"
    plots.bargraph(_flaps_per_switch(records), keys, labels,
                   title=title, ylabel="Flaps",
                   out_path=output_path("flaps.png", out_dir))
    return [{"file": "flaps.png", "title": title, "scope": "all"}]


# --- flaps, one bar per interconnect ---------------------------------------------

def _lane_scalars(records, field):
    """Per-lane records -> {(switch, port, lane): number} for the bar chart."""
    values = {}
    for record in records or []:
        key = (record["switch"], record["port"], record["lane"])
        values[key] = record[field]
        if record["lane"] == 0:  # un-broken-out port; topology calls it lane 1
            values[(record["switch"], record["port"], 1)] = record[field]
    return values


def draw_link_flaps(measurements, keys, labels, out_dir):
    records = measurements["flaps"]
    if records is None:
        return []
    values = _lane_scalars(records, "count")
    _report_unmatched(keys, values, "link flap")
    return _draw_paged(plots.bargraph, values, keys, labels,
                       stem="link_flap_bar",
                       title="Link flap count by interconnect",
                       ylabel="Flaps", out_dir=out_dir)


# --- the four metrics with many readings per lane --------------------------------

def _lane_values(records, drop_at_or_above=None):
    """Per-lane records -> {(switch, port, lane): [values]} for the box and dot plots."""
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


def draw_ber(measurements, meta, keys, labels, out_dir):
    records = measurements["ber"]
    if records is None:
        return []
    values = _lane_values(records, drop_at_or_above=SATURATED_BER)
    _report_unmatched(keys, values, "BER")
    return _draw_paged(plots.box_plot, values, keys, labels,
                       stem="pre_fec_ber_box",
                       title=f"Pre-FEC BER by interconnect ({meta['ber_source']})",
                       ylabel="Pre-FEC BER", out_dir=out_dir)


def draw_tcode(measurements, keys, labels, out_dir):
    records = measurements["tcode"]
    if records is None:
        return []
    values = _lane_values(records)
    _report_unmatched(keys, values, "T-Code")
    return _draw_paged(plots.dot_plot, values, keys, labels,
                       stem="tcode_dot",
                       title="T-Code by interconnect",
                       ylabel="T-Code", out_dir=out_dir)


def draw_uncorrected_cw(measurements, keys, labels, out_dir):
    records = measurements["uncorrected_cw"]
    if records is None:
        return []
    values = _lane_values(records)
    _report_unmatched(keys, values, "uncorrected codeword")
    return _draw_paged(plots.dot_plot, values, keys, labels,
                       stem="uncorrected_cw_dot",
                       title="Uncorrected codewords by interconnect",
                       ylabel="Uncorrected codewords", out_dir=out_dir)


def draw_link_up(measurements, keys, labels, out_dir):
    records = measurements["link_up"]
    if records is None:
        return []
    values = _lane_values(records)
    _report_unmatched(keys, values, "link-up")
    return _draw_paged(plots.dot_plot, values, keys, labels,
                       stem="link_up_dot",
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


def draw_temperatures(measurements, meta, keys, seams, out_dir):
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


# --- the manifest, written once every chart is on disk ---------------------------

def _by_scope(charts):
    """Reorder so each switch's charts arrive together, the 'all' ones first.

    A stable sort keeps the metric order within each switch.
    """
    def scope_order(chart):
        if chart["scope"] == "all":
            return (0, "")
        return (1, str(chart["scope"]))
    return sorted(charts, key=scope_order)


def _write_manifest(measurements_yml, meta, charts, out_dir, testcase):
    """Declare what was drawn, in the order it should be presented."""
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
    else:
        print("  Info: no topology file; labelling the x axis from the measurements "
              "themselves, so entries are named rather than described.")
        keys, labels = build_measured_axis(measurements)
        switch_keys, switch_labels = build_measured_switches(measurements)

    seams = meta.get("seams") or []
    if seams:
        print(f"  Info: merged capture; lines break at {len(seams)} run boundary "
              f"({', '.join(f'{s:.1f}h' for s in seams)}) where nothing was measured.")

    charts = []
    charts.extend(draw_flap_summary(measurements, switch_keys, switch_labels, out_dir))
    charts.extend(draw_link_flaps(measurements, keys, labels, out_dir))
    charts.extend(draw_ber(measurements, meta, keys, labels, out_dir))
    charts.extend(draw_tcode(measurements, keys, labels, out_dir))
    charts.extend(draw_uncorrected_cw(measurements, keys, labels, out_dir))
    charts.extend(draw_link_up(measurements, keys, labels, out_dir))
    charts.extend(draw_temperatures(measurements, meta, switch_keys, seams, out_dir))

    return _write_manifest(measurements_yml, meta, _by_scope(charts), out_dir, testcase)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("measurements", nargs="?",
                        default=MEASUREMENTS_DIR / "soak_sample.yml",
                        help="measurement yaml to chart")
    parser.add_argument("-o", "--out-dir",
                        help="where the charts go (default: output/<capture name>/)")
    args = parser.parse_args()
    out_dir = args.out_dir or OUTPUT_DIR / Path(args.measurements).stem
    generate_plots(args.measurements, out_dir)
