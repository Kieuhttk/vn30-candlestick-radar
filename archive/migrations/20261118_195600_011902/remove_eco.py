from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3


path = Path("storage/radar.db").resolve()

if not path.is_file():
    raise FileNotFoundError(
        f"Không tìm thấy DB: {path}"
    )

tables = (
    "ohlc_daily",
    "summary_daily",
    "quality_issues",
    "ingest_log",
)

stamp = datetime.now(
    timezone(timedelta(hours=7))
).strftime("%Y%m%d_%H%M%S_%f")

backup = path.parent / (
    f"radar_before_remove_ECO_{stamp}.db"
)

with closing(
    sqlite3.connect(
        path.as_uri() + "?mode=rw",
        uri=True,
        timeout=10,
    )
) as conn:
    existing = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table'"
        )
    }

    if not set(tables).issubset(existing):
        raise RuntimeError(
            "DB không đúng schema dự kiến; "
            "chưa xóa dữ liệu."
        )

    # Tạo bản sao lưu, không ghi đè file đã có.
    with backup.open("xb"):
        pass

    with closing(sqlite3.connect(backup)) as target:
        conn.backup(target)

        if target.execute(
            "PRAGMA quick_check"
        ).fetchall() != [("ok",)]:
            raise RuntimeError(
                "Bản sao lưu không đạt; "
                "chưa xóa dữ liệu."
            )

    print("Đã sao lưu:", backup)

    # Một lỗi trong khối này sẽ rollback cả giao dịch.
    with conn:
        conn.execute("BEGIN IMMEDIATE")

        before = {
            table: conn.execute(
                f"SELECT COUNT(*) FROM {table} "
                "WHERE symbol <> ?",
                ("ECO",),
            ).fetchone()[0]
            for table in tables
        }

        deleted = {}

        for table in tables:
            deleted[table] = conn.execute(
                f"DELETE FROM {table} "
                "WHERE symbol = ?",
                ("ECO",),
            ).rowcount

        for table in tables:
            remaining = conn.execute(
                f"SELECT COUNT(*) FROM {table} "
                "WHERE symbol = ?",
                ("ECO",),
            ).fetchone()[0]

            others = conn.execute(
                f"SELECT COUNT(*) FROM {table} "
                "WHERE symbol <> ?",
                ("ECO",),
            ).fetchone()[0]

            if remaining or others != before[table]:
                raise RuntimeError(
                    "Kiểm tra sau xóa không đạt; "
                    "rollback giao dịch."
                )

    print("Đã xóa ECO:", deleted)
    print("Các mã khác giữ nguyên số dòng.")