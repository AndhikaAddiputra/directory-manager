"""Mengembalikan test_workspace ke kondisi awal (berantakan) untuk pengujian ulang."""
import shutil
from pathlib import Path

BASE = Path(__file__).parent
WS, BACKUP = BASE / "test_workspace", BASE / "test_workspace_backup"

if WS.exists():
    shutil.rmtree(WS)
shutil.copytree(BACKUP, WS)
print("test_workspace sudah di-reset dari test_workspace_backup.")
