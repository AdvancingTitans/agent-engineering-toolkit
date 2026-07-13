from pathlib import Path

Path("src").mkdir(exist_ok=True)
Path("src/forbidden.txt").write_text("outside declared scope\n", encoding="utf-8")
