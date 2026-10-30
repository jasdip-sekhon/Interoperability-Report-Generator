"""Build one report: captures in, slide deck out.

    python main.py run_myrack.yml
    python main.py path/to/captures -t topology.xlsx

The work is in pipeline.py; nothing here can be reached by a test, so nothing here
does anything but read the command line.
"""

from pathlib import Path
import argparse

from pipeline import run

PROJECT_ROOT = Path(__file__).parent

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", nargs="?", default=PROJECT_ROOT / "run.yml",
                        help="a run config, a capture .xlsx, or a folder of them "
                             "(default: run.yml)")
    parser.add_argument("-t", "--topology",
                        help="topology .xlsx for x-axis labels; without one the labels "
                             "come from the measurements themselves")
    args = parser.parse_args()
    run(args.target, args.topology)
