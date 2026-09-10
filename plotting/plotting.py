from pathlib import Path
import yaml

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

STYLE_PATH = Path(__file__).parent / "plotting_style.yaml"
with open(STYLE_PATH) as f:
    STYLE = yaml.safe_load(f)

class Plots:

    def __init__(self, style=None):
        self.style = style if style is not None else dict(STYLE)

    def _process_data(self, data, keys):
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
            height = self.style["MIN_FIG_HEIGHT_IN"] + 0
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

    def _finish(self, figure, out_path):
        figure.tight_layout()
        figure.savefig(out_path, dpi=self.style["DPI"])
        plt.close(figure)
        return True

    def box_plot(self, data, keys, labels, title, ylabel, out_path, spec_min=None, spec_max=None, xlabel=None, colors=None):
        if not keys:
            return False
        figure, axes = plt.subplots(figsize=self._figsize(labels))

        values = self._process_data(data, keys)
        boxplot = axes.boxplot(values, patch_artist=True)

        self._set_category_ticks(axes, labels)
        axes.set_title(title)
        axes.set_ylabel(ylabel)
        if xlabel:
            axes.set_xlabel(xlabel)
        self._draw_limits(axes, spec_min, spec_max)
        colors = colors or [self.style["DEFAULT_COLOR"]] * len(keys)
        boxes = boxplot["boxes"]
        for i in range(len(boxes)):
            patch = boxes[i]
            color = colors[i]
            patch.set_facecolor(color)
        return self._finish(figure, out_path)

    def bargraph(self, data, keys, labels, title, ylabel, out_path, spec_min=None, spec_max=None, xlabel=None, colors=None):
        if not keys:
            return False
        figure, axes = plt.subplots(figsize=self._figsize(labels))

        values = self._process_data(data, keys)
        bars = axes.bar(range(1, len(labels) + 1), values, color=colors or [self.style["DEFAULT_COLOR"]] * len(keys))

        self._set_category_ticks(axes, labels)
        axes.set_title(title)
        axes.set_ylabel(ylabel)
        if xlabel:
            axes.set_xlabel(xlabel)
        self._draw_limits(axes, spec_min, spec_max)
        return self._finish(figure, out_path)

    def dot_plot(self):
        pass

    def temp_time_series(self):
        pass