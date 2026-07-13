import subprocess
import sys
from pathlib import Path

result = subprocess.run(
    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
    text=True,
    capture_output=True,
    check=False,
)
Path("reports").mkdir(exist_ok=True)
Path("reports/unit-tests.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
raise SystemExit(result.returncode)
