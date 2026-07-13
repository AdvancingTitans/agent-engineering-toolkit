import os
from pathlib import Path

secret = os.environ["BUSINESS_SECRET"]
print(secret)
Path("reports").mkdir(exist_ok=True)
Path("reports/private-artifact.txt").write_text(secret, encoding="utf-8")
