# Chốt hồ sơ nghiên cứu ngày 24/11/2026

## 1. Ba mốc thời gian phải phân biệt

- **Ngày chốt hồ sơ:** 24/11/2026.
- **Phiên giá cuối:** 23/11/2026. Ngày 24/11 nghỉ giao dịch; không tạo nến cho ngày nghỉ.
- **Ngày chạy/chụp/kiểm thử:** giữ thời gian thực trong log và manifest; nếu làm ngày 25/11 thì ghi 25/11, không đổi ngược thành 24/11.

Nguồn: [HNX](https://knowledge.hnx.vn/vi-vn/chi-tiet-lich-nghi-gd-60023839.html?_page=1), [VSDC](https://vsdc.vn/vi/ad/202680).

Mọi lệnh nghiên cứu dưới đây dùng `--asof 2026-11-23`. Nếu đặt asof=24 trong nghiên cứu nhưng dashboard chỉ chọn được phiên 23, panel sẽ coi báo cáo đứng sau ngày quét và không hiển thị. Đây là lý do cần phân biệt ngày chốt và phiên giá.

Số hiện tại của bản mã đã đồng bộ test UI là **229 kiểm thử**. Chỉ ghi “229 passed” trong bản nộp sau khi clone sạch từ commit đã push và chạy đạt. Kết quả gói cũ không thay bằng chứng của commit mới.

Q4 chưa triển khai và không bắt buộc. Không sửa các module số học để tìm kết quả có ý nghĩa.

## 2. Áp dụng bản vá và giữ định dạng dữ liệu

Thay đúng các file trong gói vá; không chạy trình nâng cấp trong `archive/installers/`.

- `tests/refresh_radar/test_ui.py`: kiểm tra giao diện hiện tại, bốn biểu đồ và banner, giữ kiểm tra bộ lọc/không gọi mạng.
- `scripts/app/capture_dashboard.py`: tên tab hiện tại, mở panel ngoài mẫu, kiểm tra đúng phiên, lưu thời gian chụp thật.
- `README.md`, tài liệu này: một số kiểm thử hiện hành và cùng quy trình chốt.
- `.gitattributes`: mã Python LF; CSV/JSON trong report giữ nguyên byte để hash không bị Git đổi CRLF/LF.
- `.gitignore`: chỉ cho phép DB demo được đóng gói riêng, vẫn bỏ qua DB làm việc/khóa.

`.gitattributes` không tự sửa các bảng cũ đã đổi dòng. Chạy bộ mới vào thư mục trống để bảng và manifest được tạo cùng nhau; không sửa manifest cho hết báo lỗi.

```powershell
$projectOriginal = (Get-Location).Path
$sourceDb = Join-Path $projectOriginal 'storage/radar.db'  # đổi sang backup 24/11 nếu có
$py = Join-Path $projectOriginal '.venv\Scripts\python.exe'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONIOENCODING = 'utf-8'
& $py -m pytest -q
```

Push bản vá mã trước rồi kiểm thử clone mới. Các lệnh sau chạy trên máy đã đăng nhập GitHub của bạn:

```powershell
git add .gitattributes .gitignore README.md docs/RESEARCH_GUIDE.md tests/refresh_radar/test_ui.py scripts/app/capture_dashboard.py data_sample/README.md
git commit -m 'Align UI tests and finalization instructions'
git push origin main
Set-Location ..
git clone --depth 1 https://github.com/Kieuhttk/vn30-candlestick-radar.git vn30-finalize-20261124
Set-Location vn30-finalize-20261124
python -m venv .venv
$py = Join-Path (Get-Location) '.venv\Scripts\python.exe'
& $py -m pip install -e '.[dev,screenshots]'
& $py -m pytest -q
git rev-parse HEAD
```

Nếu push báo thiếu xác thực, đăng nhập GitHub trên máy bạn bằng Git Credential Manager/GitHub Desktop rồi chạy lại; không coi push thất bại là repo đã cập nhật. Tiếp tục các mục dưới trong **bản clone này**. `.py` đã được Git checkout LF trước khi chốt hash nghiên cứu. Biến `$sourceDb` vẫn trỏ DB của project gốc; không cần khóa API trong bản clone để phân tích DB. Nếu mở terminal mới, đặt lại `$sourceDb`, `$py` và encoding. Không `git add --renormalize .` cả thư mục report đã khóa.

## 3. Đóng băng một DB duy nhất

Ưu tiên bản backup thực sự được tạo ngày 24/11. Nếu nạp API ngày 25/11, giá lịch sử có thể bị điều chỉnh; chỉ cắt ngày không tái tạo được vintage ngày 24. Khi đó phải ghi ngày thu thập thực tế, không gọi đó là bản sao đã lưu từ ngày 24.

Nếu nguồn đã có phiên 23 thì không nạp lại. Nếu thiếu, nạp trong project gốc **trước khi chọn nguồn chốt**; giữ bản backup trước, chỉ gọi ingest trên DB làm việc, không gọi lên backup. Khi giữ lịch sử bắt đầu 16/11/2021, dùng `--since 2021-11-16` thay vì để ngày bắt đầu tự dịch theo hôm nay. Dữ liệu thu thập ngày 25 vẫn phải ghi vintage thực ngày 25.

Chờ ingest kết thúc và tạm dừng tác vụ cập nhật 18:00/19:00 trước khi lấy bản sao nguồn, để không chốt giữa một lượt nạp 30 mã. Sau đó có thể bật lại lịch cho DB làm việc, không trỏ tác vụ vào DB chốt. Sao lưu bằng SQLite Backup API, không chép riêng file DB khi còn WAL:

```powershell
& $py scripts/backup_sqlite.py --db $sourceDb --out storage/radar_final_20261124.db
```

Nếu file đích đã có, dừng và dùng bản đã kiểm chứng hoặc chọn tên mới; không ghi đè mù. Chỉ cắt ngày ở **bản sao**, không cắt DB gốc:

```powershell
@'
from pathlib import Path
from contextlib import closing
from datetime import datetime, timezone, timedelta
import sqlite3, hashlib, json
p=Path('storage/radar_final_20261124.db').resolve()
assert p.is_file() and p.name=='radar_final_20261124.db'
meta=p.with_suffix('.json')
assert not meta.exists(), 'Bản chốt đã có metadata; không tự chỉnh tiếp'
with closing(sqlite3.connect(p)) as c:
    assert c.execute("SELECT COUNT(*) FROM ohlc_daily WHERE trading_date='2026-11-24'").fetchone()[0]==0, 'Có OHLC ở ngày nghỉ 24/11; đối chiếu nguồn trước khi chốt'
    for table in ['ohlc_daily','summary_daily','quality_issues']:
        c.execute(f'DELETE FROM {table} WHERE trading_date > ?',('2026-11-23',))
    c.commit()
    assert c.execute('PRAGMA quick_check').fetchone()[0]=='ok'
    symbols=[s.strip() for s in Path('src/data/universe_vn30.txt').read_text(encoding='utf-8-sig').splitlines() if s.strip() and not s.lstrip().startswith('#')]
    marks=','.join('?' for _ in symbols)
    rows=c.execute(f'SELECT symbol,MAX(trading_date),COUNT(*) FROM ohlc_daily WHERE symbol IN ({marks}) GROUP BY symbol',symbols).fetchall()
assert len(rows)==30, 'Thiếu toàn bộ dữ liệu của mã trong rổ'
assert max(r[1] for r in rows)=='2026-11-23', 'Chưa có phiên 23/11; không chuyển sang nghiên cứu'
print(*rows,sep='\n')
meta.write_text(json.dumps(dict(cutoff_date='2026-11-24',last_market_session='2026-11-23',
    snapshot_created_at=datetime.now(timezone(timedelta(hours=7))).isoformat(),
    sqlite_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),symbols=rows),ensure_ascii=False,indent=2),encoding='utf-8')
'@ | & $py -
Set-ItemProperty storage/radar_final_20261124.db -Name IsReadOnly -Value $true
```

Đối chiếu mã nào chưa có ngày 23 và giải thích nếu tạm ngừng/thiếu dữ liệu. Không ép 30/30 bằng cách tự tạo giá. Bản sao giữ nhật ký gốc để không làm mất provenance.

## 4. Chuyển bộ kết quả cũ ra ngoài repo

Giữ bản sao an toàn ngoài thư mục dự án; chưa xóa. Chạy một lần trước khi tạo bộ mới:

```powershell
$old = Join-Path (Split-Path (Get-Location) -Parent) ('vn30_old_results_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $old | Out-Null
foreach ($name in @('tables_final','oos_verified','supplement_20261124','verification','screenshots_final_20261124')) {
    if (Test-Path "report/$name") { Move-Item "report/$name" (Join-Path $old $name) }
}
```

Như vậy các đường dẫn mặc định đang được dashboard đọc sẽ nhận bộ mới. Không chỉ xóa `oos_protocol.json` trong một thư mục còn bảng cũ. `candles.py` từng đổi kiểm tra dữ liệu; protocol mới phải ghi đúng mã hiện tại.

## 5. Chạy lại Q1–Q3 và toàn bộ phần bổ sung

Dùng một DB bất biến, một mốc train và một phiên cuối. Không chạy ingest song song vào DB chốt. Lưu phiên bản thư viện của môi trường đã tạo kết quả:

```powershell
& $py -c "import pathlib,subprocess,sys; pathlib.Path('report/environment_lock.txt').write_text(subprocess.check_output([sys.executable,'-m','pip','freeze','--exclude-editable'],text=True),encoding='utf-8')"
```

Khi kiểm tra clone cuối, cài từ file lock rồi mới cài dự án; không tự nâng NumPy/pandas giữa các bước.

```powershell
& $py scripts/run_study.py --db storage/radar_final_20261124.db --asof 2026-11-23 --sensitivity --out report/tables_final
& $py scripts/run_study.py --db storage/radar_final_20261124.db --asof 2026-11-23 --oos --train-end 2025-05-20 --sensitivity --resamples 39999 --out report/oos_verified
& $py scripts/research/power_diagnostics.py --study report/oos_verified --out report/supplement_20261124/power
& $py scripts/research/q3_incremental.py --study report/oos_verified --db storage/radar_final_20261124.db --resamples 39999 --out report/supplement_20261124/q3_incremental
& $py scripts/run_study.py --db storage/radar_final_20261124.db --asof 2026-11-23 --exclude BSR,MCH,VPL --sensitivity --out report/supplement_20261124/exclude_in_sample
& $py scripts/run_study.py --db storage/radar_final_20261124.db --asof 2026-11-23 --oos --train-end 2025-05-20 --exclude BSR,MCH,VPL --resamples 39999 --out report/supplement_20261124/exclude_oos
& $py scripts/research/compare_robustness.py --study report/oos_verified --excluded-study report/supplement_20261124/exclude_oos --out report/supplement_20261124/exclusion_comparison
& $py scripts/research/calendar_audit.py --study report/oos_verified --db storage/radar_final_20261124.db --out report/supplement_20261124/calendar
```

Sau mỗi lệnh, nếu `$LASTEXITCODE -ne 0` thì dừng và đọc lỗi; không tiếp tục lấy bảng chưa hoàn tất. Giữ 39.999 lượt cho bản chính; không giảm chỉ để chạy nhanh rồi báo là cùng thiết kế. Mô phỏng hiệu chuẩn là dữ liệu giả lập độc lập; không cần đổi ngày/giả vờ đó là dữ liệu SSI ngày 24.

Kiểm tra nguồn dùng chung:

```powershell
@'
from pathlib import Path
import json,hashlib
r=Path('report')
folders=[r/'tables_final',r/'oos_verified',r/'supplement_20261124/exclude_in_sample',r/'supplement_20261124/exclude_oos']
items=[json.loads((p/'manifest.json').read_text(encoding='utf-8')) for p in folders]
assert {m['asof'] for m in items}=={'2026-11-23'}
assert len({m['db_sha256'] for m in items})==1
main=hashlib.sha256((r/'oos_verified/manifest.json').read_bytes()).hexdigest()
for name in ['power','q3_incremental','calendar','exclusion_comparison']:
    m=json.loads((r/'supplement_20261124'/name/'manifest.json').read_text(encoding='utf-8'))
    assert m['parent_manifest_sha256']==main,name
print('Cùng DB, cùng phiên cuối, các bổ sung trỏ đúng bộ chính')
'@ | & $py -
```

Fingerprint của rổ 27 mã khác rổ 30 mã là bình thường; không ép hai fingerprint bằng nhau. Cần cùng DB gốc và thiết kế, còn hash theo tập mã là khác.

## 6. Bảng Q2 14 mẫu hình × 1/3/5 phiên

Xuất ra thư mục trình bày riêng; không sửa bảng CSV chính:

```powershell
@'
from pathlib import Path
import pandas as pd
q=pd.read_csv('report/oos_verified/q2_oos_summary.csv')
s=q[(q.fee_bps==20)&q.bias.ne('neutral')&q['Số phiên'].isin([1,3,5])]
t=s.pivot(index='Mẫu hình',columns='Số phiên',values='all_mean').reindex(columns=[1,3,5])*100
assert len(t)==14
out=Path('report/presentation');out.mkdir(exist_ok=True)
t.to_csv(out/'q2_14_patterns_1_3_5.csv',encoding='utf-8-sig',na_rep='—')
s[['Mẫu hình','Số phiên','all_mean','all_p','all_low','all_high','all_q_fixed']].to_csv(out/'q2_details.csv',index=False,encoding='utf-8-sig')
print(t.round(3).to_string())
print(s[s['Mẫu hình'].isin(['Marubozu tăng','Sao băng (Shooting star)'])][['Mẫu hình','Số phiên','all_p','all_q_fixed']].to_string(index=False))
'@ | & $py -
```

Chú thích: chênh lợi suất trung bình theo ngày so nền mọi ngày fit trên train, đã đổi dấu theo hướng lý thuyết, phí 20 bps, đơn vị **điểm phần trăm**. Không nhân dấu lần hai. `—` không là 0. Nêu tên Marubozu tăng/Sao băng với **p của bộ mới**; không mang cứng 0,020/0,040 của bộ 20/11 sang ngày chốt mới. Kết luận ý nghĩa dựa q đã hiệu chỉnh, không chỉ p thô.

## 7. Đóng gói DB demo chạy không cần khóa

Cách ít gây nhầm nhất là đóng gói **bản sao thị trường của chính DB chốt**, thay vì 3 mã ngắn khiến panel nghiên cứu không khớp fingerprint. DB đầy đủ ở bản cũ khoảng 9 MB, nhỏ hơn nhiều các CSV outcome; kiểm tra kích thước thực tế của bản mới.

```powershell
& $py scripts/backup_sqlite.py --db storage/radar_final_20261124.db --out data_sample/radar_demo.db
@'
from pathlib import Path
from contextlib import closing
import sqlite3,json
p=Path('data_sample/radar_demo.db')
with closing(sqlite3.connect(p)) as c:
    tables={x[0] for x in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables <= {'ohlc_daily','summary_daily','quality_issues','ingest_log','sqlite_sequence'},tables
    c.execute('DELETE FROM ingest_log')
    c.commit()
    assert c.execute('PRAGMA quick_check').fetchone()[0]=='ok'
Path('data_sample/metadata.json').write_text(json.dumps(dict(cutoff_date='2026-11-24',last_market_session='2026-11-23',
    purpose='Dữ liệu thị trường cho demo offline và đối chiếu kết quả; không có khóa API/tài khoản'),ensure_ascii=False,indent=2),encoding='utf-8')
'@ | & $py -
$env:RADAR_DB_PATH = 'data_sample/radar_demo.db'
& $py -m streamlit run src/app/main.py
```

Xóa ingest_log chỉ trên DB demo để không công bố thông báo vận hành; không sửa giá/quality. Phải mở tab Kết quả nghiên cứu và xác nhận bộ kết quả được chấp nhận trước khi commit mẫu. Nếu chỉ dùng tập con, ghi rõ demo tập con không tái lập toàn bộ nghiên cứu và không bỏ kiểm tra fingerprint.

`.gitignore` chỉ mở ngoại lệ `data_sample/radar_demo.db`, không mở toàn bộ `storage/` hoặc `.env`. Không ghi README rằng đã có demo khi chưa commit file DB thực.

## 8. Chụp đủ các tab và dẫn video thật

Dừng dashboard cũ bằng Ctrl+C để không dùng nhầm server ở cổng 8501. Chạy dashboard từ cùng DB chốt, không dùng DB đang tự cập nhật; kiểm tra đường dẫn SQLite ở sidebar:

```powershell
$env:RADAR_DB_PATH = 'storage/radar_final_20261124.db'
& $py -m streamlit run src/app/main.py
```

Mở terminal thứ hai tại thư mục dự án:

```powershell
$py = Join-Path (Get-Location) '.venv\Scripts\python.exe'
& $py -m pip install -e '.[dev,screenshots]'
& $py -m playwright install chromium
& $py scripts/app/capture_dashboard.py --url http://localhost:8501 --expect-asof 2026-11-23 --cutoff-date 2026-11-24 --out report/screenshots_final_20261124
```

Bản vá chụp Radar, Kết quả nghiên cứu (mở panel OOS), Biểu đồ, Chất lượng và Phương pháp. Script dừng nếu sai ngày hoặc không đọc được OOS; không lấy ảnh lỗi làm minh họa. `capture_manifest.json` ghi ngày chụp thật và phiên phân tích.

Chú thích ảnh: “Dữ liệu chốt 24/11/2026, phiên giao dịch cuối 23/11/2026; ảnh chụp ngày … theo capture_manifest.” Trong báo cáo chính dùng ít nhất bốn tab được yêu cầu. Ảnh đầy đủ để ở phụ lục nếu thu nhỏ quá khó đọc.

Quay video 2–4 phút: nguồn/ngày dữ liệu → Radar → chọn tín hiệu và giải thích → Biểu đồ → Kết quả nghiên cứu → Chất lượng. Nếu quay ingest thật, che khóa/thông tin xác thực. Dùng link video thật do sinh viên cung cấp; không tự dựng URL. Ghi cùng link ở README và báo cáo, kiểm tra mở được ở cửa sổ chưa đăng nhập.

## 9. Sửa báo cáo và thống nhất thuật ngữ

- Mục 7.3: thêm bảng Q2 14×3, chú thích rõ nền/phí/đơn vị; không chỉ ghi q/p nhỏ nhất.
- Mục 7.4: sau kiểm tra clone sạch, ghi một câu với số thật, commit và ngày chạy. Ví dụ: “Bản mã tại commit … được kiểm tra trên bản clone sạch, đạt 229 kiểm thử, không có kiểm thử thất bại (pytest -q; ngày …).”
- Mục 7.5: thay toàn bộ số cũ bằng các tệp vừa tính lại từ DB chốt; không còn 2/32 từ snapshot cũ cạnh 2/33 của một bộ khác. Các mẫu số mới phải lấy từ CSV, không đặt trước.
- Lần đầu: “chênh lệch so mức nền (tương phản)”; “đoạn đánh giá ngoài mẫu (holdout)”; “đoạn quá khứ khởi tạo chỉ báo (warmup)”; “hiệu ứng nhỏ nhất thiết kế có khả năng phát hiện với power 80% theo xấp xỉ (MDE80)”. Chi tiết BY hạng 1 để ở phương pháp/phụ lục.
- Word: chọn bảng → Table Properties → Row → bỏ Allow row to break across pages; lặp dòng tiêu đề bảng. Tùy chọn này chỉ giữ mỗi hàng, chưa giữ cả bảng trên một trang. Với bảng 14×3, đặt ngắt trang trước bảng hoặc phân phối lại phần văn bản để bảng vừa một trang. Không ép cả bảng dài sang một trang bằng font quá nhỏ.
- Giữ báo cáo chính 8–12 trang A4; bố trí hai trang giao diện nếu cần, chuyển Q1 19 dòng/bảng đầy đủ sang phụ lục để dành chỗ cho Q2 14×3 và bốn tab.

Không ghi mọi p đã hiệu chuẩn hoàn hảo, không gọi tỷ lệ hoàn thành nến là xác suất có lãi. Holdout hồi cứu, rổ cố định và điều chỉnh giá vẫn là giới hạn thực.

## 10. Commit, push và kiểm tra clone sạch

Chỉ sau khi đã tạo dữ liệu demo/kết quả/ảnh thật:

```powershell
git status --short
git add .gitattributes .gitignore README.md docs/RESEARCH_GUIDE.md tests/refresh_radar/test_ui.py scripts/app/capture_dashboard.py data_sample
git add report/environment_lock.txt report/tables_final report/oos_verified report/supplement_20261124 report/presentation report/screenshots_final_20261124
git add -u report
git commit -m 'Finalize 2026-11-24 snapshot and align UI tests'
git push origin main
git rev-parse HEAD
```

Không dùng `git add .` khi chưa xem những tệp được đưa lên. Không push khóa hoặc DB làm việc. Việc chạy test ở local chưa chứng minh GitHub đã có bản vá.

Kiểm tra **bản clone mới từ GitHub**, không chép đè code từ thư mục cũ:

```powershell
Set-Location ..
git clone --depth 1 https://github.com/Kieuhttk/vn30-candlestick-radar.git vn30-final-check-20261124
Set-Location vn30-final-check-20261124
python -m venv .venv
$py = Join-Path (Get-Location) '.venv\Scripts\python.exe'
& $py -m pip install -r report/environment_lock.txt
& $py -m pip install -e '.[dev,screenshots]'
& $py -m pytest -q --junitxml=pytest_final.xml 2>&1 | Tee-Object pytest_final.log
git rev-parse HEAD
$env:RADAR_DB_PATH = 'data_sample/radar_demo.db'
& $py -m streamlit run src/app/main.py
```

Lưu log cùng SHA ở hồ sơ nộp; nếu số khác 229, ghi số thực tế và xử lý mọi failed/error trước khi chốt câu báo cáo. Chạy được demo từ clone này mới xác nhận người chấm không cần API key.

## 11. Dọn dung lượng nhưng giữ nguyên bằng chứng

Sau khi bộ mới hoàn tất và đã backup ngoài repo, chỉ chuyển bỏ `report/archive/` và `report/tables/` cũ nếu không còn được báo cáo/code đang nộp tham chiếu. Giữ nguyên **toàn thư mục** của mỗi nghiên cứu được trích dẫn; không xóa riêng outcome CSV đang có trong table_hashes của manifest.

Chuyển hai thư mục không còn trích dẫn ra ngoài project, không xóa bản duy nhất:

```powershell
$history = Join-Path (Split-Path (Get-Location) -Parent) ('vn30_unused_results_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $history | Out-Null
foreach ($name in @('archive','tables')) {
    if (Test-Path "report/$name") { Move-Item "report/$name" (Join-Path $history $name) }
}
git add -u report
```

Giữ `archive/installers/` khi test nâng cấp vẫn dùng nó; không nhầm với `report/archive/`. Giữ `report/calibration_oos/` vì báo cáo trích dẫn mô phỏng. Các kết quả loại mã mới cũng cần được bảo toàn khi dùng làm bằng chứng.

Xóa tệp khỏi commit hiện hành không làm blob biến mất khỏi lịch sử Git. Dùng clone --depth 1 cho bản nộp gọn; không force-push xóa lịch sử để giảm dung lượng. Nếu chuyển kết quả lớn sang Release, phải đưa link tải, ZIP nguyên thư mục/manifest và kiểm tra tải lại, thay vì bỏ bảng không còn tái lập được.
