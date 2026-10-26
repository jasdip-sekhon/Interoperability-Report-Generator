"""plotting.py is meant to be liftable into another project unchanged.

That only stays true if nothing leaks into it: not an import from this project, and not
a word from this project's problem domain. Both have happened before - a chart method
was once called temp_time_series and hardcoded a legend reading "Board Sensor" - so the
rule is enforced here rather than left to care.

The runner is where switches, interconnects and optics belong. The library sees data,
keys and labels.
"""

import ast
import re
from pathlib import Path

PLOTTING_DIR = Path(__file__).parent.parent / "plotting"
LIBRARY = PLOTTING_DIR / "plotting.py"
STYLE = PLOTTING_DIR / "plotting_style.yaml"

# anything this project's problem domain would call a thing. A chart library that knows
# these words is a chart library that cannot be reused.
#
# Matched on word boundaries: 'port' must not flag 'import', 'ber' must not flag
# 'number'. "module" is deliberately absent - in Python it means something innocent.
DOMAIN_WORDS = (
    "switch", "switches", "interconnect", "interconnects", "lane", "lanes",
    "port", "ports", "sensor", "sensors", "optic", "optics",
    "fec", "ber", "tcode", "flap", "flaps", "codeword", "codewords", "linkup",
    "capture", "captures", "soak", "rack", "temperature", "temp",
)

# every module the library is allowed to reach for
ALLOWED_IMPORTS = ("pathlib", "yaml", "matplotlib")

source = LIBRARY.read_text(encoding="utf-8")
tree = ast.parse(source)


# --- it may not import anything from this project ---------------------------------

imported = []
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        for alias in node.names:
            imported.append(alias.name)
    elif isinstance(node, ast.ImportFrom):
        imported.append(node.module or "")

for module in imported:
    root = module.split(".")[0]
    assert root in ALLOWED_IMPORTS, (
        f"plotting.py imports '{module}'. It may only use {ALLOWED_IMPORTS}; anything "
        f"else ties the library to this project and stops it being liftable.")
print(f"ok  imports: only {', '.join(sorted(set(m.split('.')[0] for m in imported)))}")


# --- nor name anything from this project's domain ---------------------------------

PATTERN = re.compile(r"\b(" + "|".join(DOMAIN_WORDS) + r")\b", re.IGNORECASE)


def offending_lines(text, pattern=PATTERN):
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = pattern.search(line)
        if match:
            found.append((number, match.group(0), line.strip()[:70]))
    return found

leaks = offending_lines(source)
assert not leaks, (
    "plotting.py mentions this project's domain:\n" +
    "\n".join(f"  line {n}: '{w}' in {text}" for n, w, text in leaks) +
    "\nMove the word to plotting_runner.py and pass it in as a parameter.")
print(f"ok  vocabulary: none of {len(DOMAIN_WORDS)} domain words appear")


# --- the style file travels with it, so it has to stay generic too ----------------

leaks = offending_lines(STYLE.read_text(encoding="utf-8"))
assert not leaks, (
    "plotting_style.yaml mentions this project's domain:\n" +
    "\n".join(f"  line {n}: '{w}' in {text}" for n, w, text in leaks))
print("ok  plotting_style.yaml is generic too")


# --- the public surface should read as a chart library, not a report generator ----

methods = []
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
        if node.name != "__init__":
            methods.append(node.name)
for name in methods:
    match = PATTERN.search(name.replace("_", " "))
    assert not match, (
        f"the method '{name}' is named after this project's domain ('{match.group(0)}' "
        f"if it matched); a chart type should be named for its shape, not for what "
        f"this report happens to put in it.")
print(f"ok  public methods read generically: {', '.join(sorted(methods))}")

print()
print("all tests passed")
