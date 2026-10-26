"""Run every test file in this folder and fail loudly if any of them did.

Each test file is a standalone script (asserts, not a framework), so this just invokes
each one as a subprocess and reports which passed - the same thing as running them by
hand, one command instead of six.
"""

from pathlib import Path
import subprocess
import sys

TESTS_DIR = Path(__file__).parent

if __name__ == "__main__":
    failed = []
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        print(f"=== {path.name} ===")
        result = subprocess.run([sys.executable, str(path)])
        if result.returncode != 0:
            failed.append(path.name)
        print()

    if failed:
        print(f"FAILED: {', '.join(failed)}")
        sys.exit(1)
    print("all test files passed")
