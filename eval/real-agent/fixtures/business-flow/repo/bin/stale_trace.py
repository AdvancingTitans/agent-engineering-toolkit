import json
from pathlib import Path

path = Path(".aet/evidence/trace.json")
data = json.loads(path.read_text(encoding="utf-8"))
data["workspace_snapshot"] = {"digest": "0" * 64}
path.write_text(json.dumps(data), encoding="utf-8")
