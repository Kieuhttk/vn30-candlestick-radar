import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

source = Path("storage/radar.db").resolve()
target = Path(
    f"storage/radar_backup_{datetime.now():%Y%m%d_%H%M%S}.db"
).resolve()

if not source.is_file():
    raise FileNotFoundError(source)

if target.exists():
    raise FileExistsError(target)

with closing(
    sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
) as original:
    with closing(sqlite3.connect(target)) as backup:
        original.backup(backup)

print("Đã sao lưu:", target)