import os
import subprocess
import sys
from pathlib import Path

environment = os.environ.copy()
environment["PYTHONDONTWRITEBYTECODE"] = "1"
result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], text=True, capture_output=True, check=False, env=environment)
Path("reports").mkdir(exist_ok=True)
Path("reports/validation-tests.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
raise SystemExit(result.returncode)
