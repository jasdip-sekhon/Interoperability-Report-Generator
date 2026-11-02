"""Tests for deciding what one capture gets charted.

A testcase names the metrics its test actually measured; everything else is charted only
because nobody said otherwise. Getting this wrong fills a deck with charts of a quantity
the test was not watching, which looks like data rather than noise.
"""

import _bootstrap
from plotting_runner import METRICS, _wanted

# --- a testcase charts what it measured, not every metric there is ---------------

assert _wanted(None, "ber"), "no configured subset means draw everything"
assert _wanted(["flaps", "temps"], "flaps")
assert not _wanted(["flaps", "temps"], "ber"),     "a lane-shut test breaks links on purpose, so its BER is saturation, not signal"
for name in ("flaps", "ber", "tcode", "link_up", "temps"):
    assert name in METRICS, f"{name} is drawn but cannot be configured"
print("ok  _wanted: every metric by default, only the named ones when configured")

print()
print("all tests passed")
