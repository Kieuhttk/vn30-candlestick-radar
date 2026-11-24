# Tính năng dashboard và cách bảo trì

Bản ngày 22/11/2026 bổ sung đủ 5 tệp test lõi còn thiếu, tổng cộng 196 trường hợp đạt. Bằng chứng chạy nằm trong `report/verification/`. Thư mục `report/calibration_oos/` chứa lần mô phỏng ngoài mẫu dùng 100 seed mới, 3.400 phiên, 12 mã và 3.999 bootstrap để phục vụ mục 7.6 của báo cáo. Đây là kết quả mô phỏng, không phải dữ liệu SSI. Xem thông số và cách diễn giải trong `docs/RESEARCH_GUIDE.md`.

Radar có phần **Đọc tín hiệu từng bước**, giải thích đủ 19 mẫu hình và hai cảnh báo sớm theo ba câu hỏi: nến cho thấy gì, trạng thái là gì, tiếp theo cần quan sát gì. Bảng chỉ báo, bộ lọc và danh sách quan tâm được gấp lại để mở khi cần.

Có từ điển nến/thân/bóng/EMA/khối lượng; biểu đồ tập trung tối đa 20 phiên trước và 10 phiên sau tín hiệu, không vượt ngày quét. Các số tiền được trình bày theo dấu phân cách Việt Nam. “Đã xác nhận” chỉ là đạt quy tắc theo dõi, chưa đảm bảo sinh lời. Với Sao mai/Sao hôm đã hoàn chỉnh ba nến, thẻ nói rõ xác nhận phiên kế tiếp là bước bổ sung, khác Q3.

Thống kê cảnh báo cho chọn một mẫu hình và kỳ hạn rồi diễn giải số quan sát, lợi suất long giả định và mức bất lợi bằng lời. Bảng p/q, CI và CSV nằm trong phần chi tiết. Q1 đếm theo năm/mã; Q2 theo 1/3/5/10/20 phiên. Định nghĩa và giới hạn xem [RESEARCH_GUIDE.md](RESEARCH_GUIDE.md). Cập nhật dữ liệu xem [AUTO_UPDATE_REPAIR.md](AUTO_UPDATE_REPAIR.md).

## Áp dụng thay đổi giao diện

Dừng Streamlit, chép đè các file hiện có theo đúng đường dẫn trong gói. Không cần chạy script nâng cấp mới. Mỗi chức năng được sửa trong module đang phụ trách chức năng đó.

Bản hoàn thiện 21/11/2026 sửa trực tiếp cả `main.py` để theo dõi SQLite và ngày mới, cùng các module dữ liệu/nghiên cứu hiện có. Trước khi chép, lưu mã cũ vào `archive/backups/`; không chép DB mẫu đè DB đang dùng. Gói mã không chứa `.env`, `radar.db` hoặc CSV báo cáo.

Các file giao diện chính: `src/app/main.py`, `src/app/signal_workspace.py`, `src/finance/context.py`; theme nằm ở `src/app/premium.py`. Kiểm thử giao diện/bối cảnh trong `tests/test_signal_features.py` và `tests/refresh_radar/test_ui.py`. Nghiên cứu và cập nhật dữ liệu sửa trong các module/lệnh hiện có tương ứng.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m streamlit run src/app/main.py
```

### Sửa lỗi import khi pytest thu thập test

Nếu gặp `attempted relative import with no known parent package` hoặc `No module named 'refresh_radar.conftest'`, chép đầy đủ `tests/refresh_radar/conftest.py` và `tests/refresh_radar/__init__.py` từ gói sửa. Hai file này đã bị thiếu trong gói 23 file trước; không tự tạo conftest rỗng vì bộ test cần `FakeClient`, dữ liệu mô phỏng và fixture `seeded`/`ui_db`.

Trong `pyproject.toml`, phần `[tool.pytest.ini_options]` dùng `pythonpath = ["src", "tests"]`. `test_refresh.py` và `test_radar.py` import qua `refresh_radar.conftest`; `tests/test_auto_update.py` giữ import tuyệt đối đang có. Không tạo thêm một khối `[tool.pytest.ini_options]` trùng tên hoặc thay đổi các tùy chọn pytest khác của bạn.

Gói sửa import không đổi mã ứng dụng, SQLite hoặc phương pháp nghiên cứu. Sau khi chép, chạy lại `python -m pytest -q` từ thư mục gốc. Có thể kiểm tra thêm `python -m pytest -q --import-mode=importlib`; bản mã kiểm tra đạt 121 test ở cả hai chế độ. Khi cố ý bỏ file đánh dấu package trong bản sao thử nghiệm, nhóm refresh/radar/update vẫn đạt 42 test ở cả hai chế độ nhờ import tuyệt đối và đường dẫn test được cấu hình rõ.

Nếu tiếp tục báo `No module named 'data.radar_store'`, cần bổ sung module `src/data/radar_store.py` cùng `src/data/db.py` tương thích có `connect_readonly()`. Gói mã đồng bộ đã gồm các module nội bộ, bộ test, dữ liệu mô phỏng/fixture, lệnh chạy và tài nguyên giao diện. Nội dung được kiểm tra sau khi giải nén vào thư mục trống: 121 test đạt, 29 module nội bộ được xác nhận nạp từ chính thư mục giải nén. File cũ trong `archive/installers/` chỉ được giữ để phục vụ test hồi quy lịch sử; ứng dụng chạy trực tiếp từ `src/app/main.py`.

Giải nén nội dung gói vào thư mục gốc đồ án, gộp thư mục và ghi đè file trùng tên; bảo đảm đường dẫn cuối là `src/data/radar_store.py`, không nằm lồng trong một thư mục ZIP khác. Gói không chứa `.env`, DB, báo cáo đã sinh, venv hoặc bộ nhớ đệm. Kiểm tra `Test-Path .\src\data\radar_store.py` phải trả `True`, rồi chạy lại `.\.venv\Scripts\python.exe -m pytest -q`.

### Sửa lỗi tiếng Việt/CP1252 trên Windows

Kết quả `115 passed, 4 failed` đã được xác định: hai test đọc log UTF-8 bằng encoding mặc định CP1252; hai test thu stdout/stderr của trình cài cũ bị lỗi khi in tiếng Việt qua pipe. `tests/test_auto_update.py` hiện đọc log và JSON trạng thái bằng `encoding="utf-8"`. Test CLI đọc đầu ra bằng UTF-8 rõ ràng; các entry point Python cấu hình stdout/stderr UTF-8 khi chạy trực tiếp, không đổi stream khi được import làm module. Dữ liệu, ngưỡng nhận diện và công thức nghiên cứu giữ nguyên.

Test hồi quy chạy cả `PYTHONIOENCODING=utf-8` và `cp1252:strict`, gồm tên thư mục tiếng Việt, sao lưu, thông báo lỗi cú pháp và trạng thái SQLite chỉ đọc. Bộ mã có 126 test đạt ở môi trường thường và mô phỏng Windows CP1252 trên Linux (mặc định đọc/ghi text của Path là CP1252, tiến trình con bị ép CP1252). Đây không phải khẳng định đã chạy trên Windows thật; hãy chạy lại pytest trên máy bạn sau khi chép bản sửa.

Thông báo `RefreshSafetyError: thiếu ... ngày cũ` trong test `test_auto_update_exposes_failed_refresh_and_preserves_history` là tình huống lỗi API cố ý mô phỏng để kiểm tra dữ liệu cũ được giữ nguyên. Các ngày tháng 09/2026 trong log test là dữ liệu giả của fixture, không phải kết quả nạp SSI hoặc ngày cuối DB thật của bạn.

Gói sửa chỉ thay file hiện có. Giải nén vào gốc dự án rồi chạy `.\.venv\Scripts\python.exe -m pytest -q`. File trong `archive/installers/` được pytest sử dụng cho test hồi quy cũ, không phải bước nâng cấp cần chạy thủ công.

Sau khi thay phương pháp suy luận, giữ nguyên báo cáo/protocol cũ trong `report/archive/` rồi chạy lại vào `report/oos_verified`. Nếu thư mục này đã có protocol không khớp mã mới, chuyển cả thư mục cũ sang archive; không chỉ xóa file khóa rồi trộn các CSV cũ/mới.

Muốn lưu ảnh bằng công cụ hiện có:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[screenshots]"
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe scripts/app/capture_dashboard.py
```

Chạy dashboard ở terminal khác trước khi chụp. Ảnh vào `report/screenshots/`. Đây là phụ thuộc tùy chọn, không cần cho việc đọc SQLite hoặc tính Q1–Q3.

Bản sửa cũng chặn xác nhận ở thẻ khi phiên kế tiếp có cờ lỗi chất lượng, kể cả khi hình dạng OHLC nhìn có vẻ hợp lệ. Bối cảnh được tính trên lịch phiên chung: EMA bắt đầu lại sau khoảng thiếu/lỗi; hỗ trợ/kháng cự và khối lượng TB20 cần đủ 20 phiên liên tiếp. Danh sách quan tâm lưu bằng file tạm riêng và thay nguyên tử để tránh hai phiên trình duyệt ghi đè file tạm của nhau.

## Trạng thái hoàn thiện

Đã có nguyên mẫu chạy được: nạp/lưu/kiểm tra dữ liệu, 19 mẫu hình và hai setup, dashboard, danh sách quan tâm, xuất CSV, Q1–Q3, holdout theo thời gian và khảo sát độ nhạy. Bộ test gồm UI không gọi API, dữ liệu lỗi/tương lai, ngày quét theo dữ liệu mới và giữ ngày lịch sử. Kết quả kiểm tra mã không có nghĩa dữ liệu trên máy Windows đã cập nhật đầy đủ.

Trước khi chốt bài cần: (1) xác nhận task Windows chạy thật và log/ngày DB mới nhất; (2) chạy lại bảng final trên DB mới nhất, giải thích warning dữ liệu và lưu manifest; (3) nhờ một vài người mới làm thử các tác vụ chọn mã, đọc trạng thái và đọc Q3, rồi hoàn thiện báo cáo/video. Đã có holdout theo thời gian bằng `scripts/run_study.py --oos`; chưa triển khai Q4 và chưa chứng minh mô hình có hiệu quả giao dịch. Các giới hạn thống kê còn lại được ghi trong RESEARCH_GUIDE.md.

## File cần sửa theo chức năng

| Chức năng | File hiện có |
|---|---|
| Bố cục và điều hướng dashboard | `src/app/main.py` |
| Màu sắc, kiểu chữ, thẻ tổng quan | `src/app/premium.py` |
| Thẻ tín hiệu, bộ lọc, nghiên cứu trên UI | `src/app/signal_workspace.py` |
| Tính bối cảnh, mức xác nhận | `src/finance/context.py` |
| Nhận diện nến/mẫu hình | `src/finance/candles.py`, `src/finance/patterns.py` |
| Nạp SSI và bảo vệ refresh | `src/data/ingest.py` |
| Sao lưu, gọi ingest và ghi log cập nhật | `scripts/data/update_data.py` |
| Đăng ký/kiểm tra lịch Windows | `scripts/system/install_update_task.py` |
| Sắp xếp và hoàn tác di chuyển file | `scripts/maintenance/organize_project.py` |

## Dọn các trình cài cũ

Công cụ sắp xếp hiện có nhận diện các script nâng cấp ở gốc, cùng `upgrade_project.py`, `upgrade_research.py`, `repair_auto_update.py` trong `scripts/maintenance/` và đưa vào `archive/installers/`. Không xóa DB hoặc thông tin xác thực. Nếu đích đã tồn tại, công cụ dừng để tránh ghi đè.

```powershell
.\.venv\Scripts\python.exe scripts/maintenance/organize_project.py
.\.venv\Scripts\python.exe scripts/maintenance/organize_project.py --apply
```

Lệnh đầu chỉ xem trước; lệnh sau di chuyển và in manifest để hoàn tác. Nếu di chuyển file cập nhật từ gốc vào scripts, đăng ký lại lịch bằng file `scripts/system/install_update_task.py` hiện có.

```powershell
.\.venv\Scripts\python.exe scripts/maintenance/organize_project.py --undo "archive/migrations/<thời-điểm>/moves.json"
```

## Đánh giá ngoài mẫu

Chạy `scripts/run_study.py --oos --train-end 2025-05-20 --sensitivity --out report/oos_verified`, rồi mở panel ngoài mẫu trong Thống kê cảnh báo. Mốc chia, mô hình, mã và phiên bản thư viện được khóa trong protocol; UI không fit lại theo bộ lọc. Q2 lấy mẫu lại cả train lẫn test; Q3 có CI chênh điểm dự báo ghép cặp. Mục kịch bản khớp lệnh trình bày thêm trượt giá 0/10/20 bps và số trường hợp không giả định khớp. Phần khám phá trong mẫu chỉ mô tả, không đưa p/q tương tác thành kết luận. Chi tiết ở mục 2b của [RESEARCH_GUIDE.md](RESEARCH_GUIDE.md).

Dashboard tự kiểm tra thay đổi SQLite mỗi 60 giây khi mở, giữ ngày lịch sử do người dùng chọn và có nút về phiên gần nhất. Bảng ngày cuối từng mã và trạng thái nạp giúp nhận ra DB cũ/lần nạp lỗi; không đánh đồng đổi ngày trên giao diện với tải thêm giá.
