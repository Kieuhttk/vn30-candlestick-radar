"""Sao lưu SQLite trước khi vá. Chỉ dùng thư viện chuẩn Python; không cần API key."""
import argparse
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Đường dẫn DB nguồn đã tồn tại")
    parser.add_argument("--out", help="File sao lưu mới; không được ghi đè file cũ")
    args = parser.parse_args()
    source = Path(args.db).expanduser().resolve()
    if not source.is_file():
        parser.error(f"Không có DB nguồn: {source}")
    stamp = datetime.now(timezone(timedelta(hours=7))).strftime("%Y%m%d_%H%M%S_%f")
    target = Path(args.out).expanduser().resolve() if args.out else source.parent / "backups" / f"radar_{stamp}.db"
    if target == source or target.exists():
        parser.error("File đích phải khác DB nguồn và chưa tồn tại")
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
        with target.open("xb"):
            pass
        try:
            with closing(sqlite3.connect(target)) as backup:
                original.backup(backup)
                if backup.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise RuntimeError("Bản sao lưu không qua quick_check")
        except Exception:
            target.unlink(missing_ok=True)
            raise
    print(f"Đã sao lưu: {target}")


if __name__ == "__main__":
    # CLI tiếng Việt dùng UTF-8 cả khi stdout/stderr bị chuyển vào pipe trên Windows.
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    main()
