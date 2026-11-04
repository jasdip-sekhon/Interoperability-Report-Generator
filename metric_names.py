"""What each measurement section is called in a sentence - one name per metric, shared
by the converter and the plotting stage so neither drifts from the other."""

METRIC_NAMES = {
    "flaps": "link flaps",
    "ber": "BER",
    "tcode": "T-Code",
    "uncorrected_cw": "uncorrected codewords",
    "link_up": "link-up time",
    "temps": "temperature",
    "sensors": "board sensor",
}
