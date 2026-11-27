# Chốt dữ liệu và hồ sơ VN30 ngày 27/11/2026

Hướng dẫn cập nhật ngày 27/11/2026. Dùng để thay hướng dẫn cũ trong docs/RESEARCH_GUIDE.md. Mọi bước nghiên cứu chạy tại C:\Users\KIEU\vn30-candlestick-radar; không chuyển sang một project clone khác.

## 1. Mốc chốt mới và những gì giữ nguyên

Báo cáo nghiên cứu cần một mốc hoặc phiên bản dữ liệu xác định để người khác tái lập. Dashboard làm việc vẫn cập nhật hằng ngày. Lần này chọn:

| Nội dung | Giá trị |
|---|---|
| Mốc dữ liệu và phiên giá cuối | 27/11/2026, khi SSI đã có nến đã đóng |
| DB làm việc | storage/radar.db |
| DB chốt mới | storage/radar_final_20261127.db |
| DB demo của bản nộp | data_sample/radar_demo.db, tạo lại từ DB chốt mới |
| Train kết thúc | 20/05/2025, giữ nguyên |
| Test | Từ 21/05/2025 đến 27/11/2026, kiểm tra lại theo protocol mới |
| Ngưỡng, phí, kỳ hạn, họ kiểm định | Giữ thiết kế hiện tại; không chọn lại theo kết quả |
| Lượt lấy mẫu bản chính | 39.999 |
| Thời gian thu thập/chạy/chụp | Ghi ngày giờ thực tế |

Giữ nguyên snapshot 23/11 thuộc hồ sơ 24/11 để đối chiếu. Không đổi tên DB cũ thành DB 27/11 và không sửa asof/hash trong manifest cũ để trông như kết quả mới. Khi thêm các phiên mới, các số quan sát, p/q, CI, Q3 và số kiểm định ước lượng được đều có thể thay đổi.

Phần ngoài mẫu vẫn là cập nhật hồi cứu của thiết kế đã khóa; không gọi đây là tập tương lai chưa từng được quan sát.

### Chuẩn bị terminal

Dừng dashboard và chờ ingest đang chạy hoàn tất. Trong thời gian lấy snapshot, tránh tác vụ cập nhật khác chạy đồng thời. Sau khi snapshot đã đóng băng, lịch cập nhật có thể tiếp tục với DB làm việc.

```powershell
Set-Location 'C:\Users\KIEU\vn30-candlestick-radar'
$ErrorActionPreference = 'Stop'
$py = Join-Path (Get-Location).Path '.venv\Scripts\python.exe'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONIOENCODING = 'utf-8'
function Run-Radar {
    & $py @args
    if ($LASTEXITCODE -ne 0) { throw "Python failed. Stop and inspect the error." }
}
if (-not (Test-Path $py)) { throw "Missing project Python." }
if (-not (Test-Path 'storage/radar.db')) { throw "Missing working DB." }
Get-Location
```

Nếu mở terminal mới, khai báo lại đường dẫn Python và UTF-8. Không cài nâng cấp NumPy/pandas giữa các bước. Các đoạn Python qua pipe dùng ký tự ASCII/Unicode escape để tránh lỗi tên cột tiếng Việt.

## 2. Nạp SSI và tạo DB chốt mới

Nạp vào DB làm việc, script có backup trước khi nạp:
```powershell
Run-Radar scripts/data/update_data.py --db storage/radar.db
Run-Radar scripts/data/update_data.py --db storage/radar.db --status
```

Đối chiếu ngày cuối từng mã trong kết quả. Exit code 0 không tự bảo đảm đã có 27/11. Nếu SSI chưa trả phiên 27, dừng và nạp lại sau; không tạo nến giả hoặc đổi ngày của nến 26.

Lấy bản sao bằng SQLite Backup API:
```powershell
if (Test-Path 'storage/radar_final_20261127.db') {
    throw "Snapshot already exists. Keep it; inspect before retrying."
}
Run-Radar scripts/backup_sqlite.py --db storage/radar.db --out storage/radar_final_20261127.db
```

Kiểm tra và chỉ cắt phần sau ngày 27 trên bản sao:
```powershell
@'
from pathlib import Path
from contextlib import closing
from datetime import datetime, timezone, timedelta
import sqlite3, json, hashlib

p=Path("storage/radar_final_20261127.db").resolve()
meta=p.with_suffix(".json")
assert p.is_file() and p.name=="radar_final_20261127.db"
assert not meta.exists(), "Snapshot metadata already exists"
now=datetime.now(timezone(timedelta(hours=7)))
assert now>=datetime(2026,11,27,15,tzinfo=now.tzinfo), "Session not closed yet"

symbols=[
    s.split("#",1)[0].strip()
    for s in Path("src/data/universe_vn30.txt").read_text(encoding="utf-8-sig").splitlines()
    if s.split("#",1)[0].strip()
]
assert len(set(symbols))==30
with closing(sqlite3.connect(p)) as c:
    for table in ["ohlc_daily","summary_daily","quality_issues"]:
        c.execute(f"DELETE FROM {table} WHERE trading_date > ?",("2026-11-27",))
    c.commit()
    assert c.execute("PRAGMA quick_check").fetchone()[0]=="ok"
    marks=",".join("?" for _ in symbols)
    rows=c.execute(
        f"SELECT symbol,MAX(trading_date),COUNT(*) FROM ohlc_daily "
        f"WHERE symbol IN ({marks}) GROUP BY symbol",symbols
    ).fetchall()
    assert len(rows)==30, "A universe symbol has no data"
    print(*rows,sep="\n")
    lagging=[s for s,last,n in rows if last!="2026-11-27"]
    assert not lagging, ("Missing 27-Nov bars; investigate before finalizing",lagging)
    invalid=c.execute(
        "SELECT COUNT(*) FROM ohlc_daily WHERE open IS NULL OR high IS NULL "
        "OR low IS NULL OR close IS NULL OR open<=0 OR high<=0 OR low<=0 "
        "OR close<=0 OR high<low OR high<open OR high<close "
        "OR low>open OR low>close OR volume<0"
    ).fetchone()[0]
    assert invalid==0, ("Invalid basic OHLC/volume rows",invalid)
    holiday_bars=c.execute("SELECT COUNT(*) FROM ohlc_daily WHERE trading_date=?",("2026-11-24",)).fetchone()[0]
    assert holiday_bars==0, "Bars on announced holiday 24-Nov; investigate SSI data"
    total=c.execute("SELECT COUNT(*) FROM ohlc_daily").fetchone()[0]
    first,last=c.execute("SELECT MIN(trading_date),MAX(trading_date) FROM ohlc_daily").fetchone()
    assert last=="2026-11-27"
    warnings=c.execute("SELECT severity,COUNT(*) FROM quality_issues GROUP BY severity").fetchall()

record=dict(
    cutoff_date="2026-11-27",last_market_session="2026-11-27",
    snapshot_created_at=now.isoformat(),data_start=first,data_end=last,
    n_symbols=len(rows),ohlc_rows=total,latest_by_symbol=rows,
    quality_counts=warnings,sqlite_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
)
meta.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
print("SNAPSHOT_20261127_READY")
print("OHLC_ROWS:",total)
'@ | & $py -
if ($LASTEXITCODE -ne 0) { throw "Snapshot validation failed. Stop here." }
Set-ItemProperty 'storage/radar_final_20261127.db' -Name IsReadOnly -Value $true
```

Chỉ tiếp tục khi thấy SNAPSHOT_20261127_READY. Khối này yêu cầu cả 30 mã có bản ghi 27/11. Nếu mã bị ngừng giao dịch/không có giao dịch hợp lệ, dừng để xác minh nguyên nhân, ghi rõ ngoại lệ trước khi nới điều kiện; không tự bù giá. Nếu snapshot bị lỗi/chưa có metadata, giữ nguyên để kiểm tra hoặc đưa sang backup trước khi tạo lại, không ghi đè mù.

JSON snapshot ghi số dòng và thời gian chuẩn bị thật. Chưa được ghi lại 35.669 dòng của bộ cũ như số mới.

## 3. Lưu bộ cũ và tạo đường dẫn đầu ra trống

Chỉ thực hiện sau khi snapshot mới đã đạt. Khối sau giữ các bộ hiện có trong storage/backups đã được ignore, gồm nguyên manifest/CSV và bằng chứng cũ. Không sửa hoặc chuyển DB chốt 24/11 sang phiên bản mới.

```powershell
$oldVersion = Join-Path (Get-Location).Path (
    'storage\backups\before_cutoff_20261127_' +
    (Get-Date -Format 'yyyyMMdd_HHmmss_fff')
)
New-Item -ItemType Directory -Path $oldVersion | Out-Null
$items = @(
    'report/tables_final'
    'report/oos_verified'
    'report/supplement_20261124'
    'report/supplement_20261127'
    'report/presentation'
    'report/screenshots_final_20261124'
    'report/screenshots_final_20261127'
    'report/environment_lock.txt'
    'report/verification'
    'data_sample/radar_demo.db'
    'data_sample/metadata.json'
)
foreach ($relative in $items) {
    if (Test-Path -LiteralPath $relative) {
        $dest=Join-Path $oldVersion $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null
        Move-Item -LiteralPath $relative -Destination $dest
    }
}
Write-Host "Old version saved: $oldVersion"
Run-Radar -c "import pathlib,subprocess,sys; pathlib.Path('report').mkdir(exist_ok=True); pathlib.Path('report/environment_lock.txt').write_text(subprocess.check_output([sys.executable,'-m','pip','freeze','--exclude-editable'],text=True),encoding='utf-8')"
```

Các đường dẫn hoạt động tables_final và oos_verified được giữ để dashboard đọc đúng mà không sửa code. Bộ bổ sung và thư mục ảnh mới dùng nhãn 20261127. Thư mục backup ở trên là bản lịch sử, không đưa vào Git.

## 4. Chạy lại nghiên cứu theo mốc 27/11

Chạy từng dòng, chờ hoàn tất trước dòng tiếp theo. Không tự giảm lượt bootstrap hoặc đổi train-end. Các script có mặc định tên thư mục cũ, nên luôn truyền --out như dưới đây.

```powershell
Run-Radar scripts/run_study.py --db storage/radar_final_20261127.db --asof 2026-11-27 --sensitivity --out report/tables_final
Run-Radar scripts/run_study.py --db storage/radar_final_20261127.db --asof 2026-11-27 --oos --train-end 2025-05-20 --sensitivity --resamples 39999 --out report/oos_verified
Run-Radar scripts/research/power_diagnostics.py --study report/oos_verified --out report/supplement_20261127/power
Run-Radar scripts/research/q3_incremental.py --study report/oos_verified --db storage/radar_final_20261127.db --resamples 39999 --out report/supplement_20261127/q3_incremental
Run-Radar scripts/run_study.py --db storage/radar_final_20261127.db --asof 2026-11-27 --exclude BSR,MCH,VPL --sensitivity --out report/supplement_20261127/exclude_in_sample
Run-Radar scripts/run_study.py --db storage/radar_final_20261127.db --asof 2026-11-27 --oos --train-end 2025-05-20 --exclude BSR,MCH,VPL --resamples 39999 --out report/supplement_20261127/exclude_oos
Run-Radar scripts/research/compare_robustness.py --study report/oos_verified --excluded-study report/supplement_20261127/exclude_oos --out report/supplement_20261127/exclusion_comparison
Run-Radar scripts/research/calendar_audit.py --study report/oos_verified --db storage/radar_final_20261127.db --out report/supplement_20261127/calendar
```

Không dùng lại protocol 24/11 trong thư mục hoạt động: bước 3 đã giữ toàn bộ bản cũ để lần này tạo protocol mới cùng DB và asof mới. Số học/thiết kế không đổi; dữ liệu train có thể đổi vintage nếu SSI điều chỉnh lịch sử, vì vậy bản mới phải có fingerprint mới khi cần.

## 5. Kiểm chứng bộ mới

### 5A. Kiểm tra DB, bảng, protocol, mã nguồn và bộ bổ sung

```powershell
@'
from pathlib import Path
from contextlib import closing
import sys, json, sqlite3, hashlib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path("scripts/research").resolve()))
from _support import parent_report, snapshot

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

r = Path("report")
db = Path("storage/radar_final_20261127.db").resolve()
with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as c:
    assert c.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    last = c.execute("SELECT MAX(trading_date) FROM ohlc_daily").fetchone()[0]
    assert last == "2026-11-27", ("Frozen DB last date", last)

folders = [
    r/"tables_final", r/"oos_verified",
    r/"supplement_20261127/exclude_in_sample",
    r/"supplement_20261127/exclude_oos",
]
actual_db = sha(db)
for folder in folders:
    m = json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    assert m.get("status") == "complete", ("Incomplete report", folder)
    assert m["asof"] == "2026-11-27", ("Wrong asof", folder)
    assert m["db_sha256"] == actual_db, ("Different DB bytes", folder)
    for name, expected in m["table_hashes"].items():
        assert sha(folder/name) == expected, ("CSV changed", folder, name)
    snapshot(db, m)
    if m["mode"] == "oos":
        parent_report(folder)
        protocol = m["protocol"]
        assert protocol["train_end"] == "2025-05-20"
        assert protocol["resamples"] == 39999
        for name, expected in protocol["numerical_code_hashes"].items():
            assert sha(name) == expected, ("Numerical code changed", name)
        assert protocol["numerical_libraries"] == {
            "numpy": np.__version__, "pandas": pd.__version__,
        }, ("Numerical library versions changed", folder)
    print("OK:", folder)

main = sha(r/"oos_verified/manifest.json")
for name in ["power", "q3_incremental", "calendar", "exclusion_comparison"]:
    folder = r/"supplement_20261127"/name
    m = json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    assert m.get("status") == "complete", ("Incomplete supplement", name)
    assert m["parent_manifest_sha256"] == main, ("Wrong parent", name)
    scripts = {
        "power":"power_diagnostics.py", "q3_incremental":"q3_incremental.py",
        "calendar":"calendar_audit.py", "exclusion_comparison":"compare_robustness.py",
    }
    assert sha(Path("scripts/research")/scripts[name]) == m["script_sha256"], ("Supplement script changed; rerun this supplement", name)
    assert sha("scripts/research/_support.py") == m["support_sha256"], ("Supplement support code changed", name)
    for filename, expected in m["tables"].items():
        assert sha(folder/filename) == expected, ("Supplement CSV changed", name, filename)
    print("OK:", folder)

print("ALL_FINAL_CHECKS_OK")
'@ | & $py -
if ($LASTEXITCODE -ne 0) { throw "Verification failed. Stop and inspect the failing check." }
```

Chỉ sang mục 6 khi có ALL_FINAL_CHECKS_OK. Đọc thêm calendar_by_year.csv và bars_on_closed_days.csv của bộ calendar; mọi chênh lịch/phiên ở ngày đóng cửa phải được đối chiếu nguồn trước khi kết luận dữ liệu đã đạt. Nếu có lỗi, dừng đúng bộ bị lỗi. Không tự sửa hash.

- Thiếu file: lệnh tạo bộ đó chưa hoàn tất hoặc sai đường dẫn.
- CSV changed: có file thay đổi byte; lấy lại bản nguyên vẹn hoặc tạo lại đúng bộ, không lưu lại CSV bằng Excel.
- Numerical code/library changed: phục hồi đúng code/môi trường đã dùng hoặc tạo lại phiên bản nghiên cứu có provenance đúng.
- Supplement script changed: chạy lại phần bổ sung tương ứng sau khi lưu bộ cũ và làm trống đường dẫn đầu ra.
- Wrong parent: bộ bổ sung đang trỏ một bộ chính khác.
- Different DB bytes/fingerprint: cần dùng đúng snapshot, không thay bằng DB làm việc.

### 5B. Mô phỏng hiệu chuẩn

Đổi mốc dữ liệu thị trường không làm đổi dữ liệu mô phỏng random walk. Giữ bộ calibration_oos hiện có nếu thiết kế, kết quả, snapshot nguồn vẫn đúng mã số học đang dùng. Không đổi ngày lịch sử hoặc design.json của mô phỏng thành 27/11.

```powershell
@'
from pathlib import Path
import json,hashlib
p=Path("report/calibration_oos/design.json")
assert p.is_file(), "Calibration design missing"
d=json.loads(p.read_text(encoding="utf-8"))
assert d.get("simulated") is True
for name, expected in d.get("source_hashes",{}).items():
    snapshot=Path("report/calibration_oos/source_snapshot")/name
    assert snapshot.is_file(), ("Calibration source missing",name)
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest()==expected, ("Calibration source changed",name)
changed=[name for name,expected in d["source_hashes"].items()
    if Path(name).is_file() and hashlib.sha256(Path(name).read_bytes()).hexdigest()!=expected]
print("CALIBRATION_DESIGN:", {k:d.get(k) for k in ["mode","repetitions","resamples","days","symbols","family"]})
print("CURRENT_CODE_DIFFERENCES:",changed)
for name in ["replications.csv","calibration_summary.csv","family_summary.csv"]:
    assert (p.parent/name).is_file(), ("Calibration result missing",name)
print("CALIBRATION_FILES_PRESENT")
'@ | & $py -
if ($LASTEXITCODE -ne 0) { throw "Calibration evidence incomplete or changed." }
```

Nếu mã số học thay đổi hoặc bộ mô phỏng chưa hoàn tất, mới cần mô phỏng phiên bản mới theo hướng dẫn hiệu chuẩn trước. Bộ kiểm tra hai mẫu hình với họ 20 không được mô tả thành hiệu chuẩn đủ họ 280. Không chạy lại mô phỏng chỉ để thay ngày trong tài liệu.

## 6. Xuất bảng Q2 và số liệu Q3 cho báo cáo

Đây là các bảng trình bày riêng, không sửa CSV thuộc manifest của nghiên cứu.
```powershell
@'
from pathlib import Path
import pandas as pd

q = pd.read_csv("report/oos_verified/q2_oos_summary.csv", encoding="utf-8-sig")
h = "S\u1ed1 phi\u00ean"
p = "M\u1eabu h\u00ecnh"
s = q.loc[
    q["fee_bps"].eq(20) & q["bias"].ne("neutral") & q[h].isin([1,3,5])
].copy()
t = s.pivot(index=p, columns=h, values="all_mean").reindex(columns=[1,3,5])*100
assert len(t) == 14, f"Expected 14 patterns, got {len(t)}"
out = Path("report/presentation")
out.mkdir(parents=True, exist_ok=True)
t.to_csv(out/"q2_14_patterns_1_3_5.csv", encoding="utf-8-sig", na_rep="\u2014")
cols = [p,h,"all_mean","all_p","all_low","all_high","all_q_fixed"]
s[cols].to_csv(out/"q2_details.csv", index=False, encoding="utf-8-sig")
print(t.round(3).to_string())
names = ["Marubozu t\u0103ng","Sao b\u0103ng (Shooting star)"]
print(s.loc[s[p].isin(names),[p,h,"all_p","all_q_fixed"]].to_string(index=False))
q3 = pd.read_csv("report/oos_verified/q3_oos_summary.csv", encoding="utf-8-sig")
q3.to_csv(out/"q3_for_report.csv", index=False, encoding="utf-8-sig")
print(q3[["name_vi","n_test_evaluated","n_test_completed","test_probability"]].to_string(index=False))
import json
snapshot_info=json.loads(Path("storage/radar_final_20261127.json").read_text(encoding="utf-8"))
manifest=json.loads(Path("report/oos_verified/manifest.json").read_text(encoding="utf-8"))
all_q=pd.concat([q["all_q_fixed"],q["trend_q_fixed"]]).dropna()
all_p=pd.concat([q["all_p"],q["trend_p"]]).dropna()
numbers={
    "asof":manifest["asof"],
    "cutoff_date":"2026-11-27",
    "data_start":snapshot_info["data_start"],
    "n_symbols":snapshot_info["n_symbols"],
    "ohlc_rows":snapshot_info["ohlc_rows"],
    "quality_counts":snapshot_info["quality_counts"],
    "train_end":manifest["protocol"]["train_end"],
    "test_start":manifest["protocol"]["test_start"],
    "primary_family":manifest["protocol"]["primary_family"],
    "finite_q":int(len(all_q)),
    "q_below_005":int(all_q.lt(0.05).sum()),
    "minimum_q":float(all_q.min()) if len(all_q) else None,
    "minimum_raw_p":float(all_p.min()) if len(all_p) else None,
    "q3_oos":[dict(
        name=row.name_vi,
        evaluated=int(row.n_test_evaluated),
        completed=int(row.n_test_completed),
        probability=float(row.test_probability) if pd.notna(row.test_probability) else None
    ) for row in q3.itertuples(index=False)],
}
(out/"report_numbers_20261127.json").write_text(
    json.dumps(numbers,ensure_ascii=False,indent=2),encoding="utf-8"
)
print(json.dumps(numbers,ensure_ascii=False,indent=2))
print("PRESENTATION_TABLES_READY")
'@ | & $py -
if ($LASTEXITCODE -ne 0) { throw "Presentation export failed." }
```

Các file mới trong `report/presentation/`:

- `q2_14_patterns_1_3_5.csv`: 14 mẫu hình × 1/3/5 phiên, hiệu ứng theo hướng lý thuyết, nhân 100 thành **điểm phần trăm**.
- `q2_details.csv`: hiệu ứng, khoảng tin cậy, p thô và q; các cột lợi suất/CI giữ **đơn vị tỷ lệ gốc**, cần nhân 100 khi trình bày bằng điểm phần trăm.
- `q3_for_report.csv`: bản sao bảng Q3 ngoài mẫu để tra số quan sát và tỷ lệ.
- `report_numbers_20261127.json`: số liệu thật của bộ mới để điền README/báo cáo; không gõ lại các số cũ.

Chú thích bảng Q2: chênh lệch so nền mọi ngày được fit trên train, đã đổi dấu theo hướng lý thuyết, phí 20 bps. Không đổi dấu lần hai. Dấu gạch là chưa ước lượng được, không phải 0.

Nêu tên Marubozu tăng và Sao băng với kỳ hạn, độ lớn hiệu ứng, p và q của **bộ vừa kiểm chứng**. Không giữ cứng 0,020/0,040 của bộ cũ. Kết luận kiểm định dùng q và khoảng tin cậy, không chỉ p thô.

## 7. Đóng gói demo không cần khóa API

Dùng bản thị trường của DB chốt để demo có đúng rổ và lịch sử, giữ fingerprint khớp báo cáo ngoài mẫu. Nếu demo đã có, khối dưới sẽ kiểm tra trước khi làm sạch nhật ký. Nếu demo không khớp, dừng, sao lưu file demo cũ rồi mới tạo bản khác; không ghi đè mù.
```powershell
if (-not (Test-Path 'data_sample/radar_demo.db')) {
    Run-Radar scripts/backup_sqlite.py --db storage/radar_final_20261127.db --out data_sample/radar_demo.db
}
@'
from pathlib import Path
from contextlib import closing
from datetime import datetime, timedelta, timezone
import sqlite3, json, hashlib, sys

sys.path.insert(0, str(Path("scripts/research").resolve()))
from _support import parent_report, snapshot

p = Path("data_sample/radar_demo.db").resolve()
assert p.is_file(), "Demo DB missing"
_, m = parent_report("report/oos_verified")
snapshot(p, m)
with closing(sqlite3.connect(p)) as c:
    tables = {x[0] for x in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables <= {"ohlc_daily","summary_daily","quality_issues","ingest_log","sqlite_sequence"}, tables
    c.execute("PRAGMA secure_delete=ON")
    c.execute("DELETE FROM ingest_log")
    c.commit()
    c.execute("VACUUM")
    assert c.execute("PRAGMA quick_check").fetchone()[0] == "ok"
snapshot(p, m)
Path("data_sample/metadata.json").write_text(json.dumps({
    "cutoff_date":"2026-11-27",
    "last_market_session":"2026-11-27",
    "prepared_at":datetime.now(timezone(timedelta(hours=7))).isoformat(),
    "demo_sha256":hashlib.sha256(p.read_bytes()).hexdigest(),
    "source_manifest_sha256":hashlib.sha256(Path("report/oos_verified/manifest.json").read_bytes()).hexdigest(),
    "purpose":"Offline market-data demo; operational ingest log removed",
}, indent=2), encoding="utf-8")
print("DEMO_MATCHES_OOS_REPORT")
'@ | & $py -
if ($LASTEXITCODE -ne 0) { throw "Demo validation failed." }
```

Khối này chỉ xóa nhật ký vận hành trên **DB demo**, dùng secure_delete/VACUUM để dọn dữ liệu đã xóa; không sửa giá/quality và không tác động DB chốt. Thành công phải có `DEMO_MATCHES_OOS_REPORT`.

Kiểm tra `.gitignore` có ngoại lệ `!data_sample/radar_demo.db` đặt sau quy tắc `*.db`. Chỉ đóng gói DB demo này, không mở ngoại lệ toàn bộ storage.

Mở dashboard từ demo; giữ terminal này chạy để chụp ở mục 8:
```powershell
$env:RADAR_DB_PATH = 'data_sample/radar_demo.db'
& $py -m streamlit run src/app/main.py
```

Trong sidebar phải là `data_sample/radar_demo.db`; ngày phân tích chọn 27/11/2026. Mở tab Kết quả nghiên cứu, mở phần ngoài mẫu và kiểm tra có số liệu, không có cảnh báo fingerprint/manifest khác nguồn. Không gọi API khi chỉ trình diễn bộ đã chốt. README chỉ được nói clone chạy offline sau khi DB demo và các bảng thực đã commit.

## 8. Chụp ảnh và quay video

### 8A. Chụp đủ tab

Dùng dashboard từ mục 7 tại cổng 8501. **Terminal thứ nhất** giữ server. Mở **terminal thứ hai**, chạy:
```powershell
Set-Location 'C:\Users\KIEU\vn30-candlestick-radar'
$py = Join-Path (Get-Location).Path '.venv\Scripts\python.exe'
$env:PYTHONIOENCODING = 'utf-8'
& $py -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "Browser installation failed." }

$shots = 'report/screenshots_final_20261127'
if ((Test-Path $shots) -and (Get-ChildItem -LiteralPath $shots -Force | Select-Object -First 1)) {
    $saved = Join-Path (Get-Location).Path ('storage\backups\screenshots_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
    New-Item -ItemType Directory -Force -Path (Split-Path $saved -Parent) | Out-Null
    Move-Item -LiteralPath $shots -Destination $saved
}
& $py scripts/app/capture_dashboard.py --url http://localhost:8501 --expect-asof 2026-11-27 --cutoff-date 2026-11-27 --out $shots
if ($LASTEXITCODE -ne 0) { throw "Capture failed; inspect the dashboard and error." }
Get-ChildItem $shots
```

Nếu module Playwright chưa có, cài extra screenshots theo pyproject nhưng giữ các thư viện số học trong lock; thường phần chuẩn bị đã cài đủ. Nếu script không nhận `--expect-asof`, bản công cụ chụp chưa được cập nhật.

Đầu ra bắt buộc:

- `01_radar.png`
- `02_ket_qua_nghien_cuu.png`
- `03_bieu_do.png`
- `04_chat_luong.png`
- `05_phuong_phap.png`
- `capture_manifest.json`

Script có thể thêm `00_tong_quan.png`. Kiểm tra bằng mắt: chữ đọc được, biểu đồ đã tải, panel ngoài mẫu có bảng thật. Nếu ảnh quá dài, cắt phần cần dùng để dàn trang nhưng giữ ảnh gốc và manifest; không sửa con số trong ảnh.

Chú thích: “Hồ sơ chốt 27/11/2026, phiên giao dịch cuối 27/11/2026; ảnh chụp ngày … theo capture_manifest.” Không đổi thời gian chụp thành ngày chốt nếu ảnh thực tế được chụp sau đó.

### 8B. Video thật, 2–4 phút

Quay nguồn/ngày dữ liệu → Radar và một tín hiệu cụ thể → Biểu đồ → Kết quả nghiên cứu → Chất lượng. Giải thích hướng lý thuyết, trạng thái xác nhận và giới hạn. Nếu demo ingest thật, che khóa và dùng DB làm việc, không ingest vào DB chốt.

Đưa video lên nơi chia sẻ được; lấy URL thật, thử mở ở cửa sổ chưa đăng nhập. Ghi cùng URL trong README và báo cáo. Đường dẫn localhost không phải link video và người chấm không truy cập được localhost trên máy bạn.

## 9. Chốt nội dung báo cáo 8–12 trang A4

### 9A. Nguồn số liệu duy nhất

| Nội dung | Nguồn |
|---|---|
| Phạm vi dữ liệu, mốc train/test, rổ, phí, kỳ hạn | `report/oos_verified/manifest.json`, `oos_protocol.json` |
| Q1 toàn mẫu | `report/tables_final/q1_pattern_year.csv`, `q1_pattern_symbol.csv` |
| Q1 riêng ngoài mẫu | `report/oos_verified/q1_oos_pattern_year.csv`, `q1_oos_pattern_symbol.csv` |
| Q2 14×3 | `report/presentation/q2_14_patterns_1_3_5.csv` |
| Q2 chi tiết/40 bps/nền theo xu hướng | `report/oos_verified/q2_oos_summary.csv` |
| Q3 tỷ lệ hoàn thành | `report/oos_verified/q3_oos_summary.csv` |
| Sức mạnh kiểm định/MDE | `report/supplement_20261127/power/mde_median_by_horizon.csv` và `family_diagnostics.csv` |
| Q3 có nhóm nền và bootstrap | `report/supplement_20261127/q3_incremental/q3_rate_comparison.csv`, `q3_rate_symbol_standardized.csv` |
| Độ vững loại BSR/MCH/VPL | `report/supplement_20261127/exclusion_comparison/` |
| Lịch nghỉ | `report/supplement_20261127/calendar/calendar_by_year.csv`, `bars_on_closed_days.csv` |
| Mô phỏng | `calibration_summary.csv`, `family_summary.csv`, `design.json` của đúng bộ được dùng |
| Số kiểm thử | log và XML từ bước 10 |
| Ảnh | `report/screenshots_final_20261127/` |

Đếm số nhãn ngoài mẫu từ `signals_oos.csv`, không cộng các dòng q2 qua nhiều kỳ hạn/phí vì sẽ đếm lặp. Với Q3 trình bày số hoàn thành / số đã đánh giá, tách pending/excluded; không dùng số train làm mẫu số test.

### 9B. Gợi ý phân bổ 12 trang chính

1. Trang 1: tên đề tài, tóm tắt, vấn đề và Q1–Q3.
2. Trang 2: dữ liệu, rổ, thời gian, nguồn SSI và chất lượng.
3. Trang 3: định nghĩa/nhận diện mẫu hình và ngưỡng.
4. Trang 4: thiết kế ngoài mẫu, lợi suất, nền, phí và kiểm định.
5. Trang 5: kiến trúc và vận hành.
6. Trang 6: giao diện Radar/Biểu đồ với hình đủ đọc.
7. Trang 7: giao diện Kết quả nghiên cứu/Chất lượng, URL video.
8. Trang 8: Q1 và Q3 cốt lõi.
9. Trang 9: bảng Q2 14×3 và diễn giải p/q/CI.
10. Trang 10: sức mạnh kiểm định, Q3 so nền, loại mã, lịch nghỉ và mô phỏng.
11. Trang 11: kiểm thử, giới hạn còn lại và kết luận.
12. Trang 12: tài liệu tham khảo.

Đây là ngân sách trang gồm tên đề tài và tham khảo. Nếu thầy quy định bìa/mục lục/phụ lục cũng nằm trong 8–12 trang, phải phân bổ trong cùng giới hạn; không tự thêm phụ lục dài vào PDF chính. Có thể bàn giao bảng CSV đầy đủ riêng trong repo.

### 9C. Sửa các mục đang lệch

- 7.3: có bảng Q2 và tên mẫu hình/kỳ hạn/độ lớn, không chỉ p nhỏ nhất.
- 7.4: lấy số thực tế từ clone cuối; bộ hiện tại dự kiến 234 test, không còn dùng 196/229 của bản cũ như số hiện hành. Nêu nền tảng/Python/ngày test. SHA chính xác lưu cùng log kiểm chứng; báo cáo có thể trỏ đến hồ sơ kiểm chứng để tránh vòng lặp sửa báo cáo rồi commit làm SHA thay đổi.
- 7.5: tất cả bổ sung cùng bộ chính; không giữ các phân số của snapshot 16/11 cạnh snapshot mới.
- 7.6: dùng kết quả mô phỏng thật, kèm thiết kế, số lần hợp lệ và bất định Monte Carlo; không để “đang chờ” rồi trình bày như đã thực hiện.
- Lần đầu giải thích: tương phản = chênh lệch so mức nền; holdout = đoạn đánh giá ngoài mẫu; warmup = quá khứ dùng khởi tạo chỉ báo; MDE80 = hiệu ứng nhỏ nhất có thể phát hiện với power 80% theo xấp xỉ. BY là hiệu chỉnh nhiều kiểm định.
- Vẫn nêu rổ cố định, chia ngoài mẫu hồi cứu, giá có thể được điều chỉnh và giới hạn giao dịch bằng dữ liệu ngày. Phần đã giải quyết bằng bổ sung phải chuyển thành kết quả/kiểm tra độ vững, không tiếp tục ghi “chưa làm”.

### 9D. Dàn trang và xuất PDF

Trong Word: A4, dùng font/giãn dòng/lề theo yêu cầu thầy; nếu không có quy định riêng, chọn một kiểu nhất quán và chữ bảng đủ đọc. Table Properties → Row → bỏ Allow row to break across pages; bật Repeat Header Rows. Tùy chọn này chỉ giữ mỗi hàng, không giữ toàn bảng. Bố trí ngắt trang trước bảng 14×3 nếu cần; tránh chia bảng hoặc thu chữ quá nhỏ.

Kiểm tra PDF xuất ra thực tế đủ 8–12 trang: hình không nhòe, bảng không bị cắt, liên kết video hoạt động, ký hiệu %/điểm phần trăm nhất quán. Tệp Word cũ chưa tự cập nhật khi CSV thay đổi. Lưu DOCX và PDF cuối vào vị trí báo cáo đang dùng trong `report/`, bỏ trích dẫn đến bản cũ.


## 9E. Sửa tài liệu cũ theo ngữ cảnh, không thay ngày toàn repo

Chỉ cập nhật các mô tả của bộ nghiên cứu hiện hành sau khi 5A và demo đã đạt.

| File/vị trí | Sửa như thế nào |
|---|---|
| README.md mục 4.5 | Đường dẫn DB thành storage/radar_final_20261127.db; mọi lệnh nghiên cứu dùng --asof 2026-11-27 |
| README.md mục 4.7 | Demo được tạo lại từ bộ 27/11; lệnh chụp dùng cả --expect-asof 2026-11-27 và --cutoff-date 2026-11-27 |
| README.md mục 7.1 | Trạng thái bộ chốt 27/11 chỉ ghi đã kiểm chứng sau khi hoàn thành các bước |
| README.md mục 7.2 | Thời gian dữ liệu tới 27/11; số dòng, Q3, số q hợp lệ/kết luận lấy từ report_numbers_20261127.json; test lấy log mới |
| README.md bảng đầu ra | supplement_20261127, screenshots_final_20261127; các đường dẫn hoạt động oos_verified và tables_final giữ nguyên |
| docs/RESEARCH_GUIDE.md | Thay bằng chính hướng dẫn 27/11 này |
| data_sample/README.md | Ghi demo có dữ liệu tới 27/11; lấy số dòng đúng từ metadata/snapshot, không giữ 35.669 của bản trước |
| data_sample/metadata.json | Do lệnh tạo demo sinh lại; không sửa ngày/hash bằng tay |
| Báo cáo Word/PDF | Sửa phạm vi dữ liệu, bảng Q1/Q2/Q3, độ vững, kết luận, ảnh và chú thích; giữ đúng 8–12 trang |
| src/app/signal_workspace.py | Giữ render_verdict lấy family và số kết quả hợp lệ động; không ghi cứng 108 hoặc số kết luận cũ |

Mẫu đoạn mô tả, chỉ điền sau khi có kết quả:

“Dữ liệu nghiên cứu được chốt đến phiên 27/11/2026. Mốc kết thúc train giữ tại 20/05/2025; đánh giá ngoài mẫu từ 21/05/2025 đến 27/11/2026. Bộ dữ liệu gồm [số mã] mã và [số dòng] dòng OHLC. Các bảng nghiên cứu, dữ liệu demo và hình minh họa được tạo từ cùng snapshot đã kiểm chứng.”

Thay các chỗ trong ngoặc bằng số từ bộ mới trước khi nộp. Không mặc định rằng số dòng, 108 kiểm định hợp lệ, 3/34 và 10/90 hoặc kết luận q của bộ trước vẫn đúng. Họ định trước vẫn giữ theo thiết kế (hiện tại 280), nhưng số kiểm định hợp lệ do dữ liệu quyết định.

Các ngày KHÔNG được đổi chỉ vì chốt sang 27/11:

- Ngày nghỉ giao dịch thật 24/11/2026 trong lịch tham chiếu và các URL nguồn.
- verified_on là ngày thực sự kiểm tra nguồn; không biến thành ngày 27 nếu chưa kiểm tra lại.
- Mốc train 20/05/2025, test_start được protocol tính, ngưỡng và thiết kế đã khóa.
- Timestamp/hash của bộ lịch sử, nguồn mô phỏng và các log cũ.
- Mọi giá trị trong CSV/manifest/protocol cũ; chỉ giữ trong backup để đối chiếu.

Khi chạy lại ngày sau 27/11, số liệu vẫn chỉ lấy đến 27/11, nhưng ngày thu thập/chạy/chụp phải ghi ngày thật. Không gọi dữ liệu tải ngày sau đó là snapshot đã được thu thập đúng ngày 27.


## 10. Kiểm thử, commit/push và kiểm chứng GitHub

### 10A. Kiểm thử dự án chính

Dừng dashboard nếu cần rồi dùng terminal dự án chính đã chạy phần chuẩn bị:
```powershell
New-Item -ItemType Directory -Force -Path report/verification | Out-Null
& $py -m pytest -q --junitxml=report/verification/pytest_final.xml 2>&1 |
    Tee-Object -FilePath report/verification/pytest_final.log
if ($LASTEXITCODE -ne 0) { throw "Tests failed. Do not finalize." }
```

Sau khi test đạt, tạo metadata từ XML thực tế:

```powershell
@'
from pathlib import Path
from datetime import datetime,timezone,timedelta
import xml.etree.ElementTree as ET
import json,hashlib,platform
import numpy as np
import pandas as pd
folder=Path("report/verification")
xml=folder/"pytest_final.xml"
cases=list(ET.parse(xml).getroot().iter("testcase"))
failed=sum(c.find("failure") is not None for c in cases)
errors=sum(c.find("error") is not None for c in cases)
skipped=sum(c.find("skipped") is not None for c in cases)
assert cases and failed==0 and errors==0
sources=[p for base in ["src","scripts","tests","archive/installers"] for p in Path(base).rglob("*.py")]
record=dict(
    generated_at=datetime.now(timezone(timedelta(hours=7))).isoformat(),
    total=len(cases),passed=len(cases)-failed-errors-skipped,
    failed=failed,errors=errors,skipped=skipped,
    python=platform.python_version(),platform=platform.platform(),
    numpy=np.__version__,pandas=pd.__version__,
    junit_sha256=hashlib.sha256(xml.read_bytes()).hexdigest(),
    source_hashes={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(sources)}
)
(folder/"test_manifest.json").write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
print("TEST_MANIFEST_READY",record["passed"])
'@ | & $py -
if ($LASTEXITCODE -ne 0) { throw "Test manifest creation failed." }
```

Kỳ vọng bộ hiện tại là 234 passed; số thực tế mới là bằng chứng. Nếu chưa phải 234, kiểm tra bản vá watchlist và source tests đã đồng bộ; không sửa báo cáo cho bằng con số mong muốn.

README phải ghi đúng demo đã có, kết quả đã kiểm chứng và số test. Thay câu trạng thái cũ “chưa chốt” chỉ khi thực sự đã hoàn tất các kiểm tra. Giữ lịch sử kiểm chứng 229 ở tài liệu lịch sử nếu nêu đúng ngày/phiên bản, không dùng như tổng hiện hành.

### 10B. Kiểm tra những gì sẽ lên Git

**Làm mục 11 trước lần commit cuối nếu quyết định dọn bộ cũ.** Sau đó quay lại đây.

`.gitattributes` cần giữ `report/**/*.csv -text` và `report/**/*.json -text` để không đổi hash khi clone. Không chạy renormalize cả report. `.gitignore` phải bỏ qua `storage/`, `.env`, `.venv/`, `archive/backups/`, `report/update_logs/`, và mở ngoại lệ DB demo. Thêm dòng thiếu vào `.gitignore` bằng editor; không bỏ qua dữ liệu nghiên cứu đang trích dẫn.

Tám nhóm script/code và file vá đều được stage bên dưới, tránh lặp lỗi chỉ add danh sách cũ rồi thiếu ba file watchlist/calendar:
```powershell
git status --short
git --no-pager -c core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol diff --check
git check-attr text -- report/oos_verified/q2_oos_summary.csv

git add src scripts tests assets .streamlit docs data_sample README.md pyproject.toml .env.example .gitignore .gitattributes archive/installers
git add report/environment_lock.txt report/tables_final report/oos_verified report/supplement_20261127 report/presentation report/screenshots_final_20261127 report/verification
if (Test-Path report/calibration_oos/design.json) { git add report/calibration_oos }
if (Test-Path report/calibration_oos_current/design.json) { git add report/calibration_oos_current }
git rm -r --cached --ignore-unmatch report/update_logs
foreach ($oldPath in @('report/supplement_20261124','report/screenshots_final_20261124')) {
    $tracked = git ls-files -- $oldPath
    if ($tracked) { git add -u -- $oldPath }
}

git --no-pager diff --cached --stat
git --no-pager diff --cached --name-only
```

`git check-attr` cần cho biết CSV được unset text. Kiểm tra danh sách staged không có `.env`, DB làm việc, lock vận hành, log chứa thông tin riêng hoặc thư mục backup. DB demo cần hiện trong staged ở lần đầu. `git rm --cached report/update_logs` chỉ bỏ nhật ký khỏi Git, giữ file cục bộ; quy tắc ignore cần có trước.

Lệnh trên không tự stage tên DOCX/PDF cuối vì tên thực tế tùy bạn. Add đúng hai file báo cáo cuối bằng đường dẫn đặt trong dấu nháy; không dùng wildcard gom cả bản cũ. Nếu script cài cũ trong archive/installers vẫn được test dùng thì giữ nó.

Commit/push:
```powershell
git commit -m "Finalize VN30 study snapshot and dashboard evidence"
if ($LASTEXITCODE -ne 0) { throw "Commit failed. Inspect git status." }
git push origin main
if ($LASTEXITCODE -ne 0) { throw "Push failed. GitHub is not yet verified." }
git rev-parse HEAD
```

Nếu commit báo không có thay đổi vì các bước đã commit trước, kiểm tra status/HEAD; không coi lỗi đó là một commit mới. Nếu push lỗi thì dừng, chưa ghi rằng GitHub đã cập nhật.

### 10C. Clone sạch để xác minh — chỉ dùng thư mục TEMP

Khối này giữ dự án chính là nơi làm việc; clone kiểm tra được tạo trong TEMP, không sinh thêm project cạnh thư mục chính. Nó tạo venv riêng, cài đúng lock, test đúng code tải từ GitHub rồi quay lại dự án chính:
```powershell
$mainProject = 'C:\Users\KIEU\vn30-candlestick-radar'
$verifyDir = Join-Path $env:TEMP ('vn30-verify-' + [guid]::NewGuid().ToString('N'))
git clone --depth 1 https://github.com/Kieuhttk/vn30-candlestick-radar.git "$verifyDir"
if ($LASTEXITCODE -ne 0) { throw "Clone failed." }
python -m venv "$verifyDir\.venv"
if ($LASTEXITCODE -ne 0) { throw "Venv creation failed." }
$verifyPy = Join-Path $verifyDir '.venv\Scripts\python.exe'

Push-Location $verifyDir
try {
    & $verifyPy -m pip install -r report/environment_lock.txt
    if ($LASTEXITCODE -ne 0) { throw "Locked environment installation failed." }
    & $verifyPy -m pip install -e '.[dev,screenshots]'
    if ($LASTEXITCODE -ne 0) { throw "Project installation failed." }
    & $verifyPy -m pytest -q --junitxml=pytest_clean.xml 2>&1 | Tee-Object pytest_clean.log
    if ($LASTEXITCODE -ne 0) { throw "Clean-clone tests failed." }
    git rev-parse HEAD
    git status --short --untracked-files=no
    if (git status --porcelain --untracked-files=no) { throw "Tracked files changed during verification." }
}
finally {
    Pop-Location
}
Set-Location $mainProject
Write-Host "Verification clone: $verifyDir"
```

So SHA clone với SHA vừa push. Log/XML của lần kiểm tra sạch nằm trong `$verifyDir`; lưu cùng bộ hồ sơ nộp bên ngoài repo hoặc bằng chứng bàn giao. Không sửa nội dung log để đổi SHA/ngày/số test. Bước test không tạo thêm commit chỉ để nhúng hash của chính commit vào trong nó.

Kiểm tra demo GitHub từ chính clone, dùng cổng 8502 để tách server cũ:
```powershell
$env:RADAR_DB_PATH = Join-Path $verifyDir 'data_sample\radar_demo.db'
& $verifyPy -m streamlit run "$verifyDir\src\app\main.py" --server.port 8502
```

Mở http://localhost:8502, kiểm tra đủ tab, DB mẫu và panel ngoài mẫu; không chép `.env`/DB làm việc vào clone. Ctrl+C để dừng. Terminal vẫn đang ở dự án chính sau bước kiểm chứng; không chuyển nghiên cứu sang clone này.

Nếu clone lỗi Git hoặc không tải được demo, đó là vấn đề bản bàn giao cần xử lý trước khi kết luận người chấm chạy được. Những file bị chỉnh trước khi commit có thể làm thay đổi source/CSV hash, vì vậy chạy lại 5A trên bộ chính khi có thay đổi liên quan.

### 10D. ZIP nộp

Sau khi toàn bộ tài liệu, code, demo và kết quả cần dùng đã commit, tạo ZIP trực tiếp từ HEAD (không gom .venv/.env/DB làm việc):
```powershell
$zip = 'C:\Users\KIEU\VN30_code_final_20261127.zip'
if (Test-Path $zip) { throw "Submission ZIP already exists. Keep it or choose a new name." }
git archive --format=zip --output="$zip" HEAD
if ($LASTEXITCODE -ne 0) { throw "ZIP export failed." }
```

ZIP này chỉ chứa file đã commit. Kiểm tra tên file đích trước khi chạy lại để không thay nhầm bản đã bàn giao. Hash của commit/test được giữ trong hồ sơ kiểm chứng bên ngoài ZIP hoặc kèm bản nộp; ghi rõ commit của ZIP.

## 11. Dọn kết quả cũ, giữ nguyên bằng chứng

Mục này tùy chọn; thực hiện **trước 10B** nếu muốn giảm file trong bản nộp. Chỉ chuyển `report/archive/` và `report/tables/` sau khi xác nhận không còn được báo cáo nộp trích dẫn và bộ mới đã qua 5A. Không áp dụng cho `archive/installers/` hoặc `report/tables_final/`.

Đưa bản cũ vào `storage/backups/` đã được ignore, thay vì xóa bản duy nhất:
```powershell
$history = Join-Path (Get-Location).Path ('storage\backups\unused_reports_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
New-Item -ItemType Directory -Path $history | Out-Null
foreach ($name in @('archive','tables')) {
    if (Test-Path "report/$name") {
        Move-Item -LiteralPath "report/$name" -Destination (Join-Path $history $name)
    }
}
$trackedOld = git ls-files -- report/archive report/tables
if ($trackedOld) { git add -u -- report/archive report/tables }
```

Không xóa riêng CSV có trong manifest của bộ đang dùng. Giữ toàn bộ `oos_verified`, các bộ bổ sung và bộ mô phỏng được trích dẫn. `archive/backups/` do lần đồng bộ code tạo có thể còn rất nặng; chỉ bỏ theo dõi Git khi đã xác định không phải tài liệu/bằng chứng đang được dẫn, và giữ bản cục bộ. Không stage backup vào bản nộp.

Xóa file khỏi commit hiện hành không xóa blob lịch sử. ZIP từ HEAD và clone --depth 1 gọn hơn; không force-push sửa lịch sử chỉ để giảm dung lượng. Không nén lại CSV trong thư mục nghiên cứu rồi xóa bản gốc mà manifest còn yêu cầu.

## Hoàn tất khi nào?

- Làm việc ở dự án chính; 5A in `ALL_FINAL_CHECKS_OK`.
- Có bảng Q2 14×3, Q3 và phần bổ sung cùng bộ chốt; dùng đúng số CSV trong báo cáo.
- Demo offline có fingerprint khớp; clone GitHub chạy được mà không có `.env`.
- Có đủ ảnh thật và video thật, thời gian thực, phiên cuối 27/11.
- Log clone sạch không có failed/error; số test, commit và ngày được ghi đúng.
- DOCX/PDF thực tế trong 8–12 trang; không còn số/bảng/ảnh của snapshot cũ bị trình bày thành bộ mới.
- Các giới hạn còn lại được nêu đúng; không khẳng định đã chứng minh sinh lời khi thống kê không hỗ trợ.

Chưa có CSV/DOCX/PDF mới từ máy bạn trong phiên hướng dẫn này, nên tài liệu này không xác nhận thay rằng kết quả hay báo cáo cuối đã hoàn tất. Khi mọi dấu kiểm trên đạt, mới chốt bản nộp.
