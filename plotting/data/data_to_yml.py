from datetime import datetime
from pathlib import Path
from openpyxl import load_workbook
import yaml

VDM_PREFEC_PREFIX = "VDM_Pre-FEC_BER_Average_Media_Input_Lane_"
SENSOR_COLUMN = "mb_asc5_temp1_Q88_frontrighttop_C"

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
    # TreeL1/L2/L3 is switch/port/lane; one capture samples each lane many times
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
        raw_values = lanes[key]

        # Fixes the "Down->Up" count by subtracting 1 from each value
        count = 0
        for raw in raw_values:
            if raw is None:
                continue
            corrected = max(0, raw - 1)
            if corrected > count:
                count = corrected

        # Determine if the link never recovered (all raw values are 0)
        if test_type == "soak":
            never_recovered = None
        else:
            never_recovered = True
            for raw in raw_values:
                if raw != 0:
                    never_recovered = False

        flap_data.append({
            "switch": switch,
            "port": port,
            "lane": lane,
            "count": count,
            "never_recovered": never_recovered,
        })
    return flap_data

def _lanes_to_records(lanes):
    records = []
    for key in lanes:
        switch, port, lane = key
        records.append({
            "switch": switch,
            "port": port,
            "lane": lane,
            "values": lanes[key],
        })
    return records

def collect_pre_fec_ber(ber_records):
    return _lanes_to_records(_group_by_lane(ber_records, "FEC_BER"))


def collect_ber_from_vdm(module_records):
    # has the same structure as collect_pre_fec_ber but uses the VDM columns instead of a single FEC_BER column
    lanes = {}
    for record in module_records:
        switch = _norm_switch(record["TreeL1"])
        port   = record["TreeL2"]
        for lane in range(1, 9):
            column = VDM_PREFEC_PREFIX + str(lane)
            if column not in record:
                continue
            key = (switch, port, lane)
            if key not in lanes:
                lanes[key] = []
            lanes[key].append(record[column])

    return _lanes_to_records(lanes)

def _parse_time(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.strptime(str(value).strip(), "%Y-%m-%d %H:%M:%S")

def _log_timestamps(log_records):
    # measurement sheets carry no clock of their own — each row joins back to the log
    # on (Repeat, test_step, TreeL1). Repeat can be 'init', so all three go in as strings.
    timestamps = {}
    for record in log_records:
        if not record["test_start_time"]:
            continue
        key = (str(record["Repeat"]), str(record["test_step"]),
               str(_norm_switch(record["TreeL1"])))
        timestamps[key] = _parse_time(record["test_start_time"])
    return timestamps

def _elapsed_hours(timestamps):
    start = None
    for key in timestamps:
        when = timestamps[key]
        if start is None or when < start:
            start = when
    return start

def collect_temps(module_records, timestamps):
    # one optic per PORT, so there is no lane here — all 8 lanes share this reading
    start = _elapsed_hours(timestamps)
    modules = {}
    unmatched = 0
    for record in module_records:
        switch = _norm_switch(record["TreeL1"])
        port   = record["TreeL2"]
        key = (str(record["Repeat"]), str(record["test_step"]), str(switch))
        when = timestamps.get(key)
        if when is None or start is None:
            unmatched = unmatched + 1
            continue

        hours = (when - start).total_seconds() / 3600.0
        temp = _parse_temp(record["ModuleMonitorsModuleMonitorInternalTemperature"])

        module_key = (switch, port)
        if module_key not in modules:
            modules[module_key] = []
        modules[module_key].append([round(hours, 4), temp])

    if unmatched:
        print(f"Info: {unmatched} module temperature reading(s) had no matching log "
              f"timestamp and were dropped.")

    temp_data = []
    for module_key in modules:
        switch, port = module_key
        # a value-coloured line is drawn segment by segment, so order matters
        points = sorted(modules[module_key])
        temp_data.append({
            "switch": switch,
            "port": port,
            "points": points,
        })
    return temp_data

def collect_sensors(sensor_records, timestamps):
    # one reading per switch, not per port — this is a sensor on the switch board
    start = _elapsed_hours(timestamps)
    switches = {}
    unmatched = 0
    for record in sensor_records:
        switch = _norm_switch(record["TreeL1"])
        value = record[SENSOR_COLUMN]
        # only some switch models carry this sensor; on the rest the column is blank
        if value is None:
            continue
        key = (str(record["Repeat"]), str(record["test_step"]), str(switch))
        when = timestamps.get(key)
        if when is None or start is None:
            unmatched = unmatched + 1
            continue

        hours = (when - start).total_seconds() / 3600.0
        if switch not in switches:
            switches[switch] = []
        switches[switch].append([round(hours, 4), float(value)])

    if unmatched:
        print(f"Info: {unmatched} sensor reading(s) had no matching log timestamp "
              f"and were dropped.")

    sensor_data = []
    for switch in switches:
        sensor_data.append({
            "switch": switch,
            "name": SENSOR_COLUMN,
            "points": sorted(switches[switch]),
        })
    return sensor_data

def _parse_temp(value):
    # readings carry a unit suffix with inconsistent spacing: '70 C', '72.9141C'
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.endswith("C"):
        text = text[:-1].strip()
    if not text:
        return None
    return float(text)

def collect_meta_data(log_records, module_records, test_type):
    # model and IP differ per switch
    switches = {}
    for record in log_records:
        switch = _norm_switch(record["TreeL1"])
        if switch is None:
            continue
        if switch not in switches:
            switches[switch] = {"device_model": None, "device_ip": None}
        if switches[switch]["device_model"] is None:
            switches[switch]["device_model"] = record["device_model"]
        if switches[switch]["device_ip"] is None:
            switches[switch]["device_ip"] = record["device_ip"]

    start_time = None
    for record in log_records:
        if record["test_start_time"]:
            start_time = str(record["test_start_time"])
            break

    temp_min = None
    temp_max = None
    for record in module_records:
        if temp_min is None:
            temp_min = _parse_temp(record["MinModuleTemperature"])
        if temp_max is None:
            temp_max = _parse_temp(record["MaxModuleTemperature"])

    return {
        "test_type": test_type,
        "start_time": start_time,
        "switches": switches,
        "spec": {"temp_min": temp_min, "temp_max": temp_max},
    }


def data_to_yml(data, yml_file):
    wb = load_workbook(data)

    log_sheet = _find_sheet(wb, "log") # meta (device model, IP, start time)
    flap_sheet = _find_sheet(wb, "get_link_flap") # bargraph 
    module_sheet = _find_sheet(wb, "get_module_info") # box_plot + dot_plot (VDM Fallback), temps, spec_max
    sensor_sheet = _find_sheet(wb, "get_switch_sensor")
    fec_sheet = _find_sheet(wb, "get_fec_counter", required=False) # box_plot + dot_plot (ASIC BER)

    log_records = _read_sheet(log_sheet)
    timestamps = _log_timestamps(log_records)
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
        ber_source = "vdm"
    else:
        ber = collect_pre_fec_ber(_read_sheet(fec_sheet)) # soak only
        ber_source = "fec_counter"

    # the ASIC counter and the optic's own reading are different instruments and must
    # never be pooled, so the chart has to be able to say which one it is showing
    meta = collect_meta_data(log_records, module_records, test_type)
    meta["ber_source"] = ber_source

    measurements = {
        "meta": meta,
        "flaps": collect_link_flaps(flap_records, test_type),
        "ber": ber,
        "temps": collect_temps(module_records, timestamps),
        "sensors": collect_sensors(sensor_records, timestamps),
    }

    with open(yml_file, "w") as f:
        yaml.dump(measurements, f, default_flow_style=False, sort_keys=False)

    return measurements


if __name__ == "__main__":
    references = Path(__file__).parent.parent.parent / "references"
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    captures = ["soak_sample.xlsx", "reset_dut_sample.xlsx", "reset_ref_sample.xlsx"]
    for capture in captures:
        output_yml = output_dir / (Path(capture).stem + ".yml")
        data_to_yml(references / capture, output_yml)
        print(f"Wrote {output_yml}")