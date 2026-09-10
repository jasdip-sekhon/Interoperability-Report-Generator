from pathlib import Path

from plotting import Plots

OUT_PATH = Path(__file__).parent / "test_box_plot.png"
BARGRAPH_OUT_PATH = Path(__file__).parent / "test_bargraph.png"

data = {
    0: [1.0, 1.2, 1.1, 1.4, 2.9],
    "4-33": [1.5, 1.6, 1.4, 1.7],
    "4-34": [0.9, 1.0, 1.1, 1.05],
    "4-35": [],
}
keys = [0, "4-33", "4-34", "4-35"]
labels = ["switch 0", "switch 4-33", "switch 4-34", "switch 4-35"]

plots = Plots()

result = plots.box_plot(
    data,
    keys,
    labels,
    title="Pre-FEC BER by switch",
    ylabel="Pre-FEC BER",
    out_path=OUT_PATH,
    spec_max=2.5,
)

x = plots.bargraph(
    data,
    keys,
    labels,
    title="Pre-FEC BER by switch",
    ylabel="Pre-FEC BER",
    out_path=OUT_PATH,
    spec_max=2.5,
)

assert result is True
assert OUT_PATH.exists() and OUT_PATH.stat().st_size > 0
print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)")

assert plots.box_plot({}, [], [], "empty", "y", OUT_PATH) is False
print("empty keys returned False")
