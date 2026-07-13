import subprocess
import sys

try:
    subprocess.run([sys.executable, "-c", "import time; time.sleep(1)"], timeout=0.01, check=False)
except subprocess.TimeoutExpired:
    print("TOOL_TIMEOUT: result is UNKNOWN")
    raise SystemExit(124)
