from pathlib import Path
import yaml
from plotting import Plots

plots = Plots()

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"

def ensure_output_dir():
    OUTPUT_DIR.mkdir(exist_ok=True)

def output_path(filename):
    ensure_output_dir()
    return OUTPUT_DIR / filename

def load_interconnects(interconnects_file):
    with open(interconnects_file, 'r') as f:
        return yaml.safe_load(f)

def build_per_port_label_chart_x_axis(interconnects):
    keys = []
    labels = []
    for record in interconnects:
        keys.append((record["Rx Switch"], record["Rx Port-Lane"]))
        labels.append(record["FEC-BER / T-Code x-axis label"])
    return keys, labels

def collect_per_switch_label_x_axis(interconnects):
    keys = []
    for record in interconnects:
        switch = record["Rx Switch"]
        if switch not in keys:
            keys.append(switch)
    labels = []
    for switch in keys:
        labels.append(f"switch {switch}")
    return keys, labels

def generate_plots():
    interconnects_yml = Path(__file__).parent / "interconnects" / "interconnects.yml"
    interconnects = load_interconnects(interconnects_yml)
    interconnect_keys, interconnect_labels = build_per_port_label_chart_x_axis(interconnects)
    switch_keys, switch_labels = collect_per_switch_label_x_axis(interconnects)


    plots.bargraph(flap_counts, switch_keys, switch_labels,
                   title="Link flaps by switch", ylabel="Flaps",
                   out_path=output_path("flaps.png"))

    plots.box_plot(ber_data, interconnect_keys, interconnect_labels,
                   title="Pre-FEC BER by interconnect", ylabel="Pre-FEC BER",
                   out_path=output_path("pre_fec_ ber.png"), spec_max=2.5)

    plots.dot_plot(ber_data, interconnect_keys, interconnect_labels,
                   title="Pre-FEC BER by interconnect", ylabel="Pre-FEC BER",
                   out_path=output_path("ber_dot.png"), spec_max=2.5)

    plots.temp_time_series(temp_data, switch_keys, switch_labels,
                   title="Module temperature over time", ylabel="Temperature (C)",
                   out_path=output_path("temp_time_series.png"),
                   sensor_points=sensor_points)