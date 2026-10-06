from plotting import Plots
from plotting_runner import OUTPUT_DIR

# its own directory: output/ is what the deck builds from, and a synthetic chart sitting
# there is indistinguishable from one rendered off a real capture
TEST_OUTPUT_DIR = OUTPUT_DIR / "test"
TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_PATH = TEST_OUTPUT_DIR / "test_box_plot.png"
BARGRAPH_OUT_PATH = TEST_OUTPUT_DIR / "test_bargraph.png"
DOT_PLOT_OUT_PATH = TEST_OUTPUT_DIR / "test_dot_plot.png"
TIME_SERIES_OUT_PATH = TEST_OUTPUT_DIR / "test_temp_time_series.png"

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

assert result is True
assert OUT_PATH.exists() and OUT_PATH.stat().st_size > 0
print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)")

flap_counts = {0: 2, "4-33": 5, "4-34": 1}

bargraph_result = plots.bargraph(
    flap_counts,
    keys,
    labels,
    title="Link flaps by switch",
    ylabel="Flaps",
    out_path=BARGRAPH_OUT_PATH,
)
assert bargraph_result is True
assert BARGRAPH_OUT_PATH.exists() and BARGRAPH_OUT_PATH.stat().st_size > 0
print(f"wrote {BARGRAPH_OUT_PATH} ({BARGRAPH_OUT_PATH.stat().st_size} bytes)")


dot_plot_result = plots.dot_plot(
    data,
    keys,
    labels,
    title="Pre-FEC BER by switch",
    ylabel="Pre-FEC BER",
    out_path=DOT_PLOT_OUT_PATH,
    spec_max=2.5,
)
assert dot_plot_result is True  
assert DOT_PLOT_OUT_PATH.exists() and DOT_PLOT_OUT_PATH.stat().st_size > 0
print(f"wrote {DOT_PLOT_OUT_PATH} ({DOT_PLOT_OUT_PATH.stat().st_size} bytes)")

# temp_time_series takes (timestamp, value) pairs per key, not bare values.
temps = {
    0: [(0, 42.1), (5, 42.3), (10, 43.0), (15, 44.2)],
    "4-33": [(0, 40.0), (5, 41.5), (10, 41.2), (15, 41.8)],
    "4-34": [(0, 39.4), (5, 39.9), (10, 40.6), (15, 40.1)],
    "4-35": [],
}

sensor_data = [(0, 39.0), (5, 39.5), (10, 40.2), (15, 40.8)]

time_series_result = plots.temp_time_series(
    temps,
    keys,
    labels,
    title="Module temperature over time",
    ylabel="Temperature (C)",
    out_path=TIME_SERIES_OUT_PATH,
    spec_max=45.0,
    sensor_points=sensor_data,
)
assert time_series_result is True
assert TIME_SERIES_OUT_PATH.exists() and TIME_SERIES_OUT_PATH.stat().st_size > 0
print(f"wrote {TIME_SERIES_OUT_PATH} ({TIME_SERIES_OUT_PATH.stat().st_size} bytes)")
