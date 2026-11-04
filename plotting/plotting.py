from pathlib import Path

import yaml

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
from matplotlib.ticker import MaxNLocator

STYLE_PATH = Path(__file__).parent / "plotting_style.yaml"
with open(STYLE_PATH) as f:
    STYLE = yaml.safe_load(f)

"""
1. guard:        if not keys: return False
2. create:       figure, axes = plt.subplots(figsize=self._figsize(labels))
3. shape data:   <one of the _process_* helpers>
4. draw:         axes.<chart_call>(...)
5. decorate:     _set_category_ticks, set_title, set_ylabel, set_xlabel
6. annotate:     _draw_limits
7. save:         return self._finish(figure, out_path)
"""

class Plots:
    def __init__(self, style=None):
        if style is not None:
            self.style = style
        else:
            self.style = dict(STYLE)

    def _process_scalars(self, data, keys):
        heights = []
        for i in keys:
            value = data.get(i)
            if value is None:
                heights.append(float("nan"))
            else:
                heights.append(float(value))
        return heights
    
    def _process_samples(self, data, keys):
        values = []
        for i in keys:
            series = data.get(i, [])
            values.append(series)
        return values

    def _set_log_scale(self, axes, series):
        # values spanning orders of magnitude flatten to nothing on a linear axis. A log
        # axis cannot place zero or a negative, so apply it only when something positive
        # is there to show; the rest clip to the bottom of the axis.
        for values in series:
            for value in values:
                if value is not None and value > 0:
                    axes.set_yscale("log")
                    return

    def _draw_limits(self, axes, spec_min, spec_max):
        for limit in (spec_min, spec_max):
            if limit is not None:
                axes.axhline(limit, color=self.style["LIMIT_COLOR"], linestyle="--")

    def _figsize(self, labels):
        width = max(self.style["MIN_FIG_WIDTH_IN"], self.style["WIDTH_PER_X_AXIS_ENTRY_IN"] * len(labels))
        label_lengths = []
        for s in labels:
            label_lengths.append(len(s))
        longest = max(label_lengths, default=0)
        grow = max(0, longest - self.style["FREE_LABEL_CHARS"]) * self.style["HEIGHT_PER_LABEL_CHAR_IN"]
        # if there are too many labels to fit horizontally, grow the height of the figure
        if len(labels) > self.style["VERTICAL_LABEL_X_AXIS_ENTRIES"]:
            height = self.style["MIN_FIG_HEIGHT_IN"] + grow
        else:
            height = self.style["MIN_FIG_HEIGHT_IN"]
        return width, height

    def _set_category_ticks(self, axes, labels):
        axes.set_xticks(range(1, len(labels) + 1))
        # rotate labels if there are too many to fit horizontally
        vertical = len(labels) > self.style["VERTICAL_LABEL_X_AXIS_ENTRIES"]
        if vertical:
            rotation = 90
        else:
            rotation = 45
        axes.set_xticklabels(labels, rotation=rotation, ha="right", fontsize=7)

    def _decorate(self, axes, title, ylabel, xlabel, spec_min, spec_max):
        axes.set_title(title)
        axes.set_ylabel(ylabel)
        if xlabel:
            axes.set_xlabel(xlabel)
        self._draw_limits(axes, spec_min, spec_max)

    def _finish(self, figure, out_path):
        figure.tight_layout()
        # written to a temp file and renamed, so an interrupt leaves nothing half-written
        partial = Path(out_path).with_suffix(".partial")
        figure.savefig(partial, dpi=self.style["DPI"], format="png")
        plt.close(figure)
        partial.replace(out_path)
        return True

    def bargraph(self, data, keys, labels, title, ylabel, out_path, spec_min=None, spec_max=None, xlabel=None, colors=None, log=False):
        if not keys:
            return False
        figure, axes = plt.subplots(figsize=self._figsize(labels))

        heights = self._process_scalars(data, keys)
        x = range(1, len(heights) + 1)
        if not colors:
            colors = [self.style["DEFAULT_COLOR"]] * len(keys)
        axes.bar(x, heights, color=colors)
        if log:
            self._set_log_scale(axes, [heights])
        # a bar's height is a count, never a fraction of one
        axes.yaxis.set_major_locator(MaxNLocator(integer=True))

        # a zero-height bar draws nothing, which looks exactly like the gap left by a
        # key that was never measured. Mark the measured zeros so "counted, none found"
        # stays distinguishable from "no data".
        zero_x = []
        for i in range(len(heights)):
            if heights[i] == 0:
                zero_x.append(i + 1)
        if zero_x:
            axes.scatter(zero_x, [0] * len(zero_x), marker="_", s=260, linewidths=2.5,
                         color=self.style["DEFAULT_COLOR"], zorder=3)

        # when every bar is 0, matplotlib autoscales to a sliver of an axis - too
        # narrow for any integer tick but 0 to fit, so it falls back to fractions
        tallest = 0
        for height in heights:
            if height == height and height > tallest:
                tallest = height
        if tallest == 0:
            axes.set_ylim(bottom=0, top=1)
        else:
            axes.set_ylim(bottom=0)

        self._set_category_ticks(axes, labels)
        self._decorate(axes, title, ylabel, xlabel, spec_min, spec_max)
        return self._finish(figure, out_path)
    
    def box_plot(self, data, keys, labels, title, ylabel, out_path, spec_min=None, spec_max=None, xlabel=None, colors=None, log=False):
        if not keys:
            return False
        figure, axes = plt.subplots(figsize=self._figsize(labels))

        values = self._process_samples(data, keys)
        boxplot = axes.boxplot(values, patch_artist=True)
        if log:
            self._set_log_scale(axes, values)

        self._set_category_ticks(axes, labels)
        self._decorate(axes, title, ylabel, xlabel, spec_min, spec_max)
        if not colors:
            colors = [self.style["DEFAULT_COLOR"]] * len(keys)
        boxes = boxplot["boxes"]
        for i in range(len(boxes)):
            patch = boxes[i]
            color = colors[i]
            patch.set_facecolor(color)
        return self._finish(figure, out_path)

    def _stable_seed(self, key):
        # a small polynomial hash, not python's own hash() - that one is salted per
        # process, so the same key would get a different seed on every run
        seed = 0
        for char in repr(key):
            seed = (seed * 131 + ord(char)) % 2147483647
        return seed

    def _jitter(self, key, count):
        """Deterministic offsets around a category's centre, seeded by the key itself
        rather than its position - so a key keeps its pattern even if other keys are
        added or dropped."""
        width = self.style["DOT_JITTER_WIDTH"]
        seed = self._stable_seed(key)
        offsets = []
        for _ in range(count):
            # a plain linear congruential generator - no import earns its way into a
            # library meant to be liftable unchanged into another project
            seed = (seed * 1103515245 + 12345) % 2147483648
            fraction = seed / 2147483648
            offsets.append((fraction * 2 - 1) * width)
        return offsets

    def _density_alpha(self, values):
        """One reading stays fully opaque; a value shared by many fades toward the
        floor, so a rare reading is never the faint one next to a common cluster."""
        floor = self.style["DOT_ALPHA_FLOOR"]
        counts = {}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        alphas = []
        for value in values:
            alphas.append(max(floor, min(1.0, 1.0 / counts[value])))
        return alphas

    def _label_counts(self, axes, position, values):
        # a count only earns a label once there is more than one dot to count
        counts = {}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        width = self.style["DOT_JITTER_WIDTH"]
        for value in counts:
            if counts[value] > 1:
                axes.text(position + width + 0.05, value, f"×{counts[value]}",
                          fontsize=self.style["DOT_LABEL_FONTSIZE"], va="center")

    def dot_plot(self, data, keys, labels, title, ylabel, out_path, spec_min=None, spec_max=None, xlabel=None, colors=None, log=False):
        if not keys:
            return False
        figure, axes = plt.subplots(figsize=self._figsize(labels))

        samples = self._process_samples(data, keys)
        if log:
            self._set_log_scale(axes, samples)
        x = []
        y = []
        alpha = []
        for i in range(len(keys)):
            sample = samples[i]
            position = i + 1
            offsets = self._jitter(keys[i], len(sample))
            for j in range(len(sample)):
                x.append(position + offsets[j])
                y.append(sample[j])
            for value in self._density_alpha(sample):
                alpha.append(value)
            self._label_counts(axes, position, sample)
        axes.scatter(x, y, color=colors, alpha=alpha if alpha else None)

        self._set_category_ticks(axes, labels)
        self._decorate(axes, title, ylabel, xlabel, spec_min, spec_max)
        return self._finish(figure, out_path)

    def _process_time_series(self, data, keys):
        series = []
        for i in keys:
            points = data.get(i, [])
            timestamps = []
            values = []
            for timestamp, value in points:
                timestamps.append(timestamp)
                values.append(value)
            series.append((timestamps, values))
        return series

    def _segments(self, x, y):
        # a NaN marks a gap where nothing was measured, so no segment spans it
        segments = []
        for i in range(len(x) - 1):
            pair = (x[i], y[i], x[i + 1], y[i + 1])
            if any(v != v for v in pair):
                continue
            segments.append([(x[i], y[i]), (x[i + 1], y[i + 1])])
        return segments

    def _add_colorbar(self, figure, axes, norm, label):
        mappable = ScalarMappable(norm=norm, cmap=self.style["VALUE_CMAP"])
        colorbar = figure.colorbar(mappable, ax=axes)
        colorbar.set_label(label)

    def _value_range(self, series, overlay_points, spec_min, spec_max):
        """The colour scale. Spec limits win, so charts of one metric stay comparable."""
        all_values = []
        for timestamps, values in series:
            all_values.extend(values)
        if overlay_points:
            for timestamp, value in overlay_points:
                all_values.append(value)
        if spec_min is not None:
            vmin = spec_min
        else:
            vmin = min(all_values, default=0)
        if spec_max is not None:
            vmax = spec_max
        else:
            vmax = max(all_values, default=1)
        return Normalize(vmin=vmin, vmax=vmax)

    def _draw_value_line(self, axes, timestamps, values, norm):
        segments = self._segments(timestamps, values)
        if segments:
            line = LineCollection(segments, cmap=self.style["VALUE_CMAP"], norm=norm)
            # each segment takes the colour of the value it starts at; this cannot be
            # values[:-1] because segments spanning a gap were dropped
            segment_colors = []
            for segment in segments:
                segment_colors.append(segment[0][1])
            line.set_array(segment_colors)
            axes.add_collection(line)
            return

        # isolated samples have no segment to colour - a series of one, or one point
        # stranded either side of a gap. Show them rather than drawing nothing.
        points_x = []
        points_y = []
        for i in range(len(timestamps)):
            if timestamps[i] == timestamps[i] and values[i] == values[i]:
                points_x.append(timestamps[i])
                points_y.append(values[i])
        if points_x:
            axes.scatter(points_x, points_y, c=points_y,
                         cmap=self.style["VALUE_CMAP"], norm=norm, s=18)

    def _draw_overlay(self, axes, overlay_points, overlay_label):
        overlay_x = []
        overlay_y = []
        for timestamp, value in overlay_points:
            overlay_x.append(timestamp)
            overlay_y.append(value)
        axes.plot(overlay_x, overlay_y, color="black", marker="o", markersize=4,
                  label=overlay_label, linewidth=1.5)
        axes.legend(loc="upper left", frameon=True)

    def value_series(self, data, keys, title, ylabel, out_path, spec_min=None, spec_max=None, xlabel=None, overlay_points=None, overlay_label="Overlay"):
        if not keys:
            return False
        figure, axes = plt.subplots(figsize=(12, 6))

        series = self._process_time_series(data, keys)
        norm = self._value_range(series, overlay_points, spec_min, spec_max)
        for timestamps, values in series:
            self._draw_value_line(axes, timestamps, values, norm)
        axes.relim()
        axes.autoscale_view()

        if overlay_points:
            self._draw_overlay(axes, overlay_points, overlay_label)

        axes.grid(True, alpha=0.3)
        self._decorate(axes, title, ylabel, xlabel, spec_min, spec_max)
        self._add_colorbar(figure, axes, norm, ylabel)
        return self._finish(figure, out_path)
