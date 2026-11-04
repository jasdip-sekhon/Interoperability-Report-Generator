"""One chart per switch, split again past MAX_X_AXIS_ENTRIES_PER_CHART - a rack has
hundreds of interconnects, so a single axis is unreadable."""

from plotting import Plots
from output import output_path

plots = Plots()


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


def _draw_per_switch(draw, values, keys, labels, meta, stem, metric, title, ylabel,
                     out_dir, spec_max=None, log=False):
    """One chart per switch, split again past the axis limit - numbered "(2 of 4)" with
    no noun, since the deck heading above it already says "page N of M" about slides."""
    drawn = []
    for switch, switch_keys, switch_labels in _split_by_switch(keys, labels):
        chunks = _chunks(switch_keys, switch_labels)
        number = 1
        for chunk_keys, chunk_labels in chunks:
            device = _switch_info(meta, switch)[1]
            chart_title = f"{title} — switch {switch} ({device})"
            name = f"{stem}_sw{switch}.png"
            if len(chunks) > 1:
                chart_title = f"{chart_title} ({number} of {len(chunks)})"
                name = f"{stem}_sw{switch}_p{number}.png"
            draw(values, chunk_keys, chunk_labels, title=chart_title, ylabel=ylabel,
                 out_path=output_path(name, out_dir), spec_max=spec_max, log=log)
            drawn.append({"file": name, "title": chart_title, "scope": switch,
                          "metric": metric})
            number = number + 1
    return drawn


def _switch_info(meta, switch):
    """(limits, device) for one switch, the device being its model and address - both
    missing is normal for a device the capture did not describe."""
    info = meta["switches"].get(switch)
    if info is None:
        info = {}
    device = info.get("device_model")
    if device is None:
        device = "unknown"
    address = info.get("device_ip")
    if address is not None:
        device = f"{device} — {address}"
    return info, device
