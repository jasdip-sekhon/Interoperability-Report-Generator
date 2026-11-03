"""Every chart this report draws, and the reshaping each one needs.

Each chart family is one block: the helper that turns measurement records into what the
chart wants, then the draw_* that uses it. Every draw_* follows the same recipe:

1. guard:    if records is None: return []
2. reshape:  records -> {(switch, port, lane): value}
3. report:   _report_unmatched, for interconnects with nothing measured
4. draw:     _draw_per_switch - one chart per switch, split when a switch has many lanes
5. record:   return one manifest entry per chart drawn

Scope appears in no name: _draw_per_switch gives every interconnect chart one file per
switch, and the manifest carries the result for the deck builder to group slides on.
"""

from pathlib import Path

from layout import _draw_per_switch, _switch_info, plots
from output import output_path
from x_axis import _report_unmatched

SATURATED_BER = 0.5  # BER >= 0.5 is the counter saturating, not a real reading
SENSOR_LABEL = "Board Sensor"

# test plan criteria, not MSA limits: KP4 survives 2.4e-4 and 15 symbol errors
SPEC_BER = 2e-6
SPEC_TCODE = 6
SPEC_LINK_UP_RESET_S = 30
SPEC_LINK_UP_SHUT_S = 20


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


def _lane_scalars(records, field):
    """Per-lane records -> {(switch, port, lane): number} for the bar chart."""
    values = {}
    for record in records:
        key = (record["switch"], record["port"], record["lane"])
        values[key] = record[field]
        if record["lane"] == 0:  # un-broken-out port; topology calls it lane 1
            values[(record["switch"], record["port"], 1)] = record[field]
    return values


def draw_flaps_by_interconnect(measurements, meta, keys, labels, out_dir):
    records = measurements["flaps"]
    if records is None:
        return []
    values = _lane_scalars(records, "count")
    _report_unmatched(keys, values, "link flap")
    return _draw_per_switch(plots.bargraph, values, keys, labels, meta,
                            stem="link_flap_bar", metric="Link flap count",
                            title="Link flap count by interconnect",
                            ylabel="Flaps (max per reading)", out_dir=out_dir)


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
    return _draw_per_switch(plots.box_plot, values, keys, labels, meta,
                            stem="pre_fec_ber_box", metric="Pre-FEC BER",
                            title=f"Pre-FEC BER by interconnect ({meta['ber_source']})",
                            ylabel="Pre-FEC BER", out_dir=out_dir,
                            spec_max=SPEC_BER, log=True)


def draw_tcode(measurements, meta, keys, labels, out_dir):
    records = measurements["tcode"]
    if records is None:
        return []
    values = _lane_values(records)
    _report_unmatched(keys, values, "T-Code")
    return _draw_per_switch(plots.dot_plot, values, keys, labels, meta,
                            stem="tcode_dot", metric="T-Code",
                            title="T-Code by interconnect",
                            ylabel="T-Code", out_dir=out_dir,
                            spec_max=SPEC_TCODE)


def _link_up_spec(meta):
    """How long a link may take to come back, which depends on what took it down."""
    if meta["test_type"].startswith("reset"):
        return SPEC_LINK_UP_RESET_S
    return SPEC_LINK_UP_SHUT_S


def draw_link_up(measurements, meta, keys, labels, out_dir):
    records = measurements["link_up"]
    if records is None:
        return []
    values = _lane_values(records)
    _report_unmatched(keys, values, "link-up")
    return _draw_per_switch(plots.box_plot, values, keys, labels, meta,
                            stem="link_up_box", metric="Link-up time",
                            title="Link-up time by interconnect",
                            ylabel="Link-up time (s)", out_dir=out_dir,
                            spec_max=_link_up_spec(meta))


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


def _is_flat(temps):
    # a line needs 2+ samples; a flat switch renders as scattered points instead
    longest = 0
    for port in temps:
        real = []
        for point in temps[port]:
            if point[0] == point[0]:
                real.append(point)
        if len(real) > longest:
            longest = len(real)
    return longest < 2


def draw_temperature_over_time(measurements, meta, keys, seams, out_dir):
    """One chart per switch: its ports are the lines, its board sensor an extra one."""
    drawn = []
    flat_switches = []
    for switch in keys:
        temps = _temps_per_port(measurements["temps"], switch, seams)
        if not temps:
            continue
        if _is_flat(temps):
            flat_switches.append(switch)

        ports = sorted(temps)
        info, device = _switch_info(meta, switch)
        name = f"temp_switch_{switch}.png"
        title = f"Module temperature over time — switch {switch} ({device})"
        plots.value_series(temps, ports,
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
    if flat_switches:
        if len(flat_switches) == 1:
            switch_word = "switch has"
        else:
            switch_word = "switches have"
        print(f"  Warning: {len(flat_switches)} {switch_word} a single temperature "
              f"sample per module ({', '.join(flat_switches)}); their charts show "
              f"points rather than a trend over time.")
    return drawn


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
        info, device = _switch_info(meta, switch)
        name = f"temp_per_port_sw{switch}.png"
        title = f"Module temperature per port — switch {switch} ({device})"
        plots.box_plot(readings, ports, labels,
                       title=title,
                       ylabel="Temperature (°C)",
                       out_path=output_path(name, out_dir),
                       spec_min=info.get("temp_min"),
                       spec_max=info.get("temp_max"))
        drawn.append({"file": name, "title": title, "scope": switch,
                      "metric": "Module temperature per port"})
    return drawn
