"""How one line reaches the terminal.

A report prints a few hundred lines and a warning has to survive being skimmed, so
the kind of line is a gutter character rather than a word buried in the sentence, and
nothing is left to the terminal's own wrapping - a 265-character warning soft-wrapped
to the margin loses the indent that tells you which capture it belongs to.
"""

from pathlib import Path
import textwrap

WIDTH = 96
PROJECT_ROOT = Path(__file__).parent


def _emit(prefix, message):
    print(textwrap.fill(message, width=WIDTH,
                        initial_indent=prefix,
                        subsequent_indent=" " * len(prefix),
                        break_long_words=False, break_on_hyphens=False))


def warn(message):
    _emit("  ! ", message)


def info(message):
    _emit("  - ", message)


def say(message):
    _emit("    ", message)


def line(message):
    """Printed whole, never wrapped: a path or a row of fields is read and copied as
    one thing, and breaking it mid-field makes the log harder to grep."""
    print(f"    {message}")


def short_path(path):
    """A path inside the project is named relative to it; one outside keeps its full
    name, because which workbook a report charted against is the thing worth knowing."""
    path = Path(path)
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)
