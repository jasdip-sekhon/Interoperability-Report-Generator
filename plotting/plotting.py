from pathlib import Path
import yaml

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize

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

    def _draw_limits(self, axes, spec_min, spec_max):
        for limit in (spec_min, spec_max):
            if limit is not None:
                axes.axhline(limit, color=self.style["LIMIT_COLOR"], linestyle="--")

    def _figsize(self, labels):
        width = max(self.style["MIN_FIG_WIDTH_IN"], self.style["ENTRY_WIDTH_IN"] * len(labels))
        label_lengths = []
        for s in labels:
            label_lengths.append(len(s))
        longest = max(label_lengths, default=0)
        grow = max(0, longest - self.style["FREE_LABEL_CHARS"]) * self.style["HEIGHT_PER_LABEL_CHAR_IN"]
        # if there are too many labels to fit horizontally, grow the height of the figure
        if len(labels) > self.style["VERTICAL_LABEL_ENTRIES"]:
            height = self.style["MIN_FIG_HEIGHT_IN"] + grow
        else:
            height = self.style["MIN_FIG_HEIGHT_IN"]
        return width, height

    def _set_category_ticks(self, axes, labels):
        axes.set_xticks(range(1, len(labels) + 1))
        # rotate labels if there are too many to fit horizontally
        vertical = len(labels) > self.style["VERTICAL_LABEL_ENTRIES"]
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
        figure.savefig(out_path, dpi=self.style["DPI"])
        plt.close(figure)
        return True

    def bargraph(self, data, keys, labels, title, ylabel, out_path, spec_min=None, spec_max=None, xlabel=None, colors=None):
        if not keys:
            return False
        figure, axes = plt.subplots(figsize=self._figsize(labels))

        heights = self._process_scalars(data, keys)
        x = range(1, len(heights) + 1)
        if not colors:
            colors = [self.style["DEFAULT_COLOR"]] * len(keys)
        axes.bar(x, heights, color=colors)
        self._set_category_ticks(axes, labels)
        self._decorate(axes, title, ylabel, xlabel, spec_min, spec_max)
        return self._finish(figure, out_path)
    
    def box_plot(self, data, keys, labels, title, ylabel, out_path, spec_min=None, spec_max=None, xlabel=None, colors=None):
        if not keys:
            return False
        figure, axes = plt.subplots(figsize=self._figsize(labels))

        values = self._process_samples(data, keys)
        boxplot = axes.boxplot(values, patch_artist=True)

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

    def dot_plot(self, data, keys, labels, title, ylabel, out_path, spec_min=None, spec_max=None, xlabel=None, colors=None):
        if not keys:
            return False
        figure, axes = plt.subplots(figsize=self._figsize(labels))

        samples = self._process_samples(data, keys)
        x = []
        y = []
        position = 1
        for sample in samples:
            for value in sample:
                x.append(position)
                y.append(value)
            position = position + 1
        axes.scatter(x, y, color=colors)

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

    def temp_time_series(self, data, keys, labels, title, ylabel, out_path, spec_min=None, spec_max=None, xlabel=None, colors=None, sensor_points=None):
        if not keys:
            return False
        figure, axes = plt.subplots(figsize=(12, 6))

        series = self._process_time_series(data, keys)
        all_values = []
        for timestamps, values in series:
            all_values.extend(values)
        if sensor_points:
            for timestamp, value in sensor_points:
                all_values.append(value)
        vmin = spec_min if spec_min is not None else min(all_values, default=0)
        vmax = spec_max if spec_max is not None else max(all_values, default=1)
        norm = Normalize(vmin=vmin, vmax=vmax)

        for timestamps, values in series:
            segments = self._segments(timestamps, values)
            if segments:
                line = LineCollection(segments, cmap=self.style["VALUE_CMAP"], norm=norm)
                colors = []
                for segment in segments:
                    colors.append(segment[0][1])
                line.set_array(colors)
                axes.add_collection(line)
                continue
            # isolated samples have no segment to colour — a lone reading, or each half
            # of a merged capture holding one. Show them rather than drawing nothing.
            points_x = []
            points_y = []
            for i in range(len(timestamps)):
                if timestamps[i] == timestamps[i] and values[i] == values[i]:
                    points_x.append(timestamps[i])
                    points_y.append(values[i])
            if points_x:
                axes.scatter(points_x, points_y, c=points_y,
                             cmap=self.style["VALUE_CMAP"], norm=norm, s=18)
        axes.relim()
        axes.autoscale_view()

        if sensor_points:
            sensor_x = []
            sensor_y = []
            for timestamp, value in sensor_points:
                sensor_x.append(timestamp)
                sensor_y.append(value)
            axes.plot(sensor_x, sensor_y, color="black", marker="o", markersize=4, label="Board Sensor", linewidth=1.5)
            axes.legend(loc="upper left", frameon=True)

        axes.grid(True, alpha=0.3)
        self._decorate(axes, title, ylabel, xlabel, spec_min, spec_max)
        self._add_colorbar(figure, axes, norm, ylabel)
        return self._finish(figure, out_path)