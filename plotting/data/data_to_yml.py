from pathlib import Path
from matplotlib.pylab import record
from openpyxl import load_workbook
import yaml

def _find_sheet(wb, sheet_name, required=True):
    # Search for a sheet by name, allowing for a numeric prefix before an underscore
    for name in wb.sheetnames:
        parts = name.split("_", 1)
        if len(parts) == 2 and parts[1] == sheet_name:
            return wb[name]
    if required:
        raise ValueError(f"Sheet '{sheet_name}' not found in workbook.")
    return None

def _read_sheet(sheet):
    rows = []
    for row in sheet.iter_rows(values_only=True):
        rows.append(row)
    if not rows:
        return []

    headers = rows[0]
    data = []
    for row in rows[1:]:
        record = {}
        i = 0
        for header in headers:
            if i < len(row):
                record[header] = row[i]
            i = i + 1
        data.append(record)
    return data

def _norm_switch(value):
    # Normalize switch values to strings
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()

def _group_by_lane(records, column):
    # TreeL1/L2/L3 is switch/port/lane; one capture samples each lane many times, so
    # every reading for a lane lands in that lane's list
    lanes = {}
    for record in records:
        key = (_norm_switch(record["TreeL1"]), record["TreeL2"], record["TreeL3"])
        if key not in lanes:
            lanes[key] = []
        lanes[key].append(record[column])
    return lanes

def collect_link_flaps(flap_records, test_type):
    lanes = _group_by_lane(flap_records, "Down->Up")

    flap_data = []
    for key in lanes:
        switch, port, lane = key
        flap_data.append({
            "switch": switch,
            "port": port,
            "lane": lane,
            "values": lanes[key],
        })
    return flap_data

def collect_pre_fec_ber(ber_records):
    lanes = _group_by_lane(ber_records, "FEC_BER")

    ber_data = []
    for key in lanes:
        switch, port, lane = key
        ber_data.append({
            "switch": switch,
            "port": port,
            "lane": lane,
            "values": lanes[key],
        })
    return ber_data


def collect_ber_from_vdm(module_records):
    pass

def collect_temps(module_records):
    pass

def collect_sensors(sensor_records):
    pass

def collect_meta_data(log_records, module_records):
    pass


def data_to_yml(data, yml_file):
    wb = load_workbook(data)

    log_sheet = _find_sheet(wb, "log") # meta (device model, IP, start time)
    flap_sheet = _find_sheet(wb, "get_link_flap") # bargraph 
    module_sheet = _find_sheet(wb, "get_module_info") # box_plot + dot_plot (VDM Fallback), temps, spec_max
    sensor_sheet = _find_sheet(wb, "get_switch_sensor")
    fec_sheet = _find_sheet(wb, "get_fec_counter", required=False) # box_plot + dot_plot (ASIC BER)

    log_records = _read_sheet(log_sheet)
    flap_records = _read_sheet(flap_sheet)
    module_records = _read_sheet(module_sheet)
    sensor_records = _read_sheet(sensor_sheet)

    # reset by default has 1 Down->Up, soak does not
    if _find_sheet(wb, "module_reset", required=False) is None:
        test_type = "soak"
    else:
        test_type = "reset"

    # reset captures have no FEC sheet so fallback to the module's own VDM reading
    if fec_sheet is None:
        ber = collect_ber_from_vdm(module_records) # reset_dut, reset_ref
    else:
        ber = collect_pre_fec_ber(_read_sheet(fec_sheet)) # soak only

    measurements = {
        "meta": collect_meta_data(log_records, module_records),
        "flaps": collect_link_flaps(flap_records, test_type),
        "ber": ber,
        "temps": collect_temps(module_records),
        "sensors": collect_sensors(sensor_records),
    }

    with open(yml_file, "w") as f:
        yaml.dump(measurements, f, default_flow_style=False, sort_keys=False)

    return measurements


if __name__ == "__main__":
    references = Path(__file__).parent.parent.parent / "references"
    captures = ["soak_sample.xlsx", "reset_dut_sample.xlsx", "reset_ref_sample.xlsx"]
    for capture in captures:
        output_yml = Path(__file__).parent / (Path(capture).stem + ".yml")
        data_to_yml(references / capture, output_yml)
        print(f"Wrote {output_yml}")