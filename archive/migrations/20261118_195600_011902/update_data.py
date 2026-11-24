"""Nạp SSI bằng module ingest hiện có; sao lưu, ghi log và in ngày mới nhất."""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
VN = timezone(timedelta(hours=7))


@contextmanager
def update_lock(path):
    with path.open("a+b") as handle:
        handle.seek(0, 2)
        if not handle.tell():
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError("Đang có một lần cập nhật khác chạy trên DB này.") from exc
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("Đang có một lần cập nhật khác chạy trên DB này.") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def backup_sqlite(source, stamp):
    target = source.parent / "backups" / f"radar_auto_{stamp}.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=30)) as original:
        if original.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise RuntimeError("SQLite nguồn không qua quick_check; chưa nạp dữ liệu.")
        with target.open("xb"):
            pass
        try:
            with closing(sqlite3.connect(target)) as copied:
                original.backup(copied)
                if copied.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise RuntimeError("Bản sao lưu không qua quick_check; chưa nạp dữ liệu.")
        except Exception:
            target.unlink(missing_ok=True)
            raise
    return target


def latest_dates(path, symbols):
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=30)) as conn:
        marks = ",".join("?" for _ in symbols)
        rows = conn.execute(
            f"SELECT symbol, MAX(trading_date), COUNT(*) FROM ohlc_daily WHERE symbol IN ({marks}) GROUP BY symbol",
            symbols,
        ).fetchall()
    return {symbol: (last, count) for symbol, last, count in rows}


def run_update(root, db_path, runner=subprocess.run):
    root = Path(root).resolve()
    source = Path(db_path).expanduser()
    source = (source if source.is_absolute() else root / source).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Không tìm thấy DB đang dùng: {source}. Kiểm tra --db trước khi chạy.")
    universe = root / "src/data/universe_vn30.txt"
    symbols = list(dict.fromkeys(line.split("#", 1)[0].strip().upper()
                                for line in universe.read_text(encoding="utf-8-sig").splitlines()))
    symbols = [symbol for symbol in symbols if symbol]
    if not symbols or any(not symbol.isalnum() for symbol in symbols):
        raise ValueError("Danh sách cổ phiếu trống hoặc không hợp lệ.")
    stamp = datetime.now(VN).strftime("%Y%m%d_%H%M%S_%f")
    folder = root / "report/update_logs"
    folder.mkdir(parents=True, exist_ok=True)
    log_path = folder / f"update_{stamp}.log"
    with update_lock(source.with_suffix(source.suffix + ".update.lock")), log_path.open("w", encoding="utf-8") as log:
        def report(message):
            print(message, flush=True)
            print(message, file=log, flush=True)

        report(f"Bắt đầu: {datetime.now(VN):%d/%m/%Y %H:%M:%S} (UTC+7)")
        report(f"SQLite: {source}")
        report(f"Nhật ký: {log_path}")
        before = latest_dates(source, symbols)
        backup = backup_sqlite(source, stamp)
        report(f"Đã sao lưu: {backup}")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        env["PYTHONIOENCODING"] = "utf-8"
        command = [sys.executable, "-m", "data.ingest", "--db", str(source), "--symbols-file", str(universe)]
        report("Đang nạp SSI. Chi tiết tiến trình được ghi trong file nhật ký ở trên...")
        result = runner(command, cwd=str(root), env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
        log.flush()
        after = latest_dates(source, symbols)
        report("Mã       Ngày cuối        Số dòng OHLC")
        for symbol in symbols:
            last, count = after.get(symbol, (None, 0))
            report(f"{symbol:<8} {last or 'chưa có':<15} {count}")
        newest = max((last for last, _ in after.values() if last), default=None)
        advanced = sum(after.get(s, (None, 0))[0] is not None and
                       (before.get(s, (None, 0))[0] is None or after[s][0] > before[s][0]) for s in symbols)
        report(f"Ngày mới nhất đã lưu trong nhóm: {newest or 'chưa có'}; {advanced}/{len(symbols)} mã có ngày cuối tăng.")
        if not advanced:
            report("Chưa thêm phiên mới. Có thể là ngày nghỉ hoặc SSI chưa trả phiên mới; xem log nếu ngày lưu vẫn cũ.")
        lagging = [s for s in symbols if after.get(s, (None, 0))[0] != newest]
        if lagging:
            report("Cần đối chiếu các mã có ngày cuối khác ngày mới nhất của nhóm: " + ", ".join(lagging))
        if result.returncode:
            report(f"Có lỗi nạp (exit code {result.returncode}). Xem nhật ký; các mã thành công đã được giữ lại.")
        else:
            report("Lệnh ingest hoàn tất. Ngày cuối ở bảng trên là kết quả thực tế, không phải cam kết SSI đã có phiên hôm nay.")
        report("Trên dashboard: Đọc lại SQLite, rồi chọn ngày quét mới.")
        return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="storage/radar.db", help="Đường dẫn DB đang dùng trên dashboard")
    args = parser.parse_args()
    try:
        return run_update(ROOT, args.db)
    except Exception as exc:
        print(f"Cập nhật thất bại: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
