# VN30 Candlestick Radar

Radar mẫu hình nến cho rổ VN30: **phát hiện** mẫu hình nến Nhật, **cảnh báo sớm** khi mới có 1–2 nến đầu của mẫu hình ba nến và **kiểm định thống kê** xem mẫu hình đó có thật sự báo trước được điều gì không. Dữ liệu lấy từ SSI FastConnect (chỉ đọc).

> Công cụ phân tích học thuật, không phải khuyến nghị đầu tư.

Hướng dẫn nghiên cứu: [Q1–Q3](docs/RESEARCH_GUIDE.md). Cập nhật dữ liệu và lịch Windows: [hướng dẫn](docs/AUTO_UPDATE_REPAIR.md).

Bổ sung nghiên cứu ngày 24/11: [MDE, Q3 có nhóm nền, loại mã và đối chiếu lịch nghỉ](docs/RESEARCH_GUIDE.md#10-bổ-sung-nghiên-cứu-ngày-24112026). Mã mới nằm trong `scripts/research/`, kết quả trong `report/supplement_20261124/`; các module số học đã khóa và bảng chính được giữ nguyên.

## Cài đặt

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Cấu hình

1. Sao chép `.env.example` thành `.env`.
2. Điền `SSI_API_KEY` và `SSI_API_SECRET` (SSI Developer Portal, chỉ cần quyền "All api data").
3. Không commit `.env`. Dự án không dùng Private Key, không dùng OTP, không gọi nhóm Trading.

## Chạy

```powershell
python -m ssi_api.probe FPT                          # thăm dò kết nối và chất lượng dữ liệu
python -m data.ingest --symbols FPT,VCB --since 2023-01-01   # nạp dữ liệu vào SQLite (cập nhật tăng dần)
python -m data.ingest                                # nạp cả rổ trong src/data/universe_vn30.txt (cần điền trước)
python -m data.ingest --status                       # trạng thái dữ liệu từng mã
python -m data.ingest --audit --check ex_event       # kiểm tra chất lượng, liệt kê ngày nghi không hưởng quyền
python -m data.ingest --ref-report FPT,VCB           # chẩn đoán điều chỉnh giá của SSI
python -m data.ingest --log                          # 20 lần nạp gần nhất
python -m data.ingest --issues --symbols FPT         # truy vết dòng bị loại và các cảnh báo
streamlit run src/app/main.py                        # mở giao diện
pytest                                               # chạy kiểm thử
```

## Cập nhật dữ liệu và chạy nghiên cứu

Sau khi cài môi trường, dùng các file hiện có:

```powershell
.\.venv\Scripts\python.exe scripts/data/update_data.py --db storage/radar.db
.\.venv\Scripts\python.exe scripts/system/install_update_task.py --at 18:00 --retry-at 19:00
.\.venv\Scripts\python.exe scripts/system/install_update_task.py --status
.\.venv\Scripts\python.exe scripts/run_study.py --db storage/radar.db --sensitivity
.\.venv\Scripts\python.exe scripts/run_study.py --oos --train-end 2025-05-20 --sensitivity --out report/oos_verified
```

Dashboard đọc SQLite, kiểm tra DB thay đổi mỗi 60 giây khi trang mở. Nếu đang xem phiên mới nhất thì theo dữ liệu mới; ngày lịch sử do bạn chọn được giữ lại, có nút về phiên gần nhất. Lịch Windows chạy ingest khi máy bật, có mạng và người dùng đăng nhập. Khi sửa lỗi, cập nhật trực tiếp file phụ trách chức năng đó. Các script cài/nâng cấp một lần được lưu trong `archive/installers/`, không thuộc luồng chạy ứng dụng.

## Kiểm thử và hiệu chuẩn mô phỏng

Bản ngày 22/11/2026 có đủ test trực tiếp cho nến, mẫu hình, SQLite, chất lượng và client SSI, tổng cộng 196 trường hợp đạt trên bản mã bàn giao. Bằng chứng chạy test nằm trong `report/verification/`; số liệu mô phỏng cho mục 7.6 nằm trong `report/calibration_oos/`, không phải dữ liệu SSI.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/research/calibrate.py --oos --repetitions 100 --resamples 3999 --days 3400 --symbols 12 --seed-start 40000 --out report/calibration_oos
```

Nếu gói đã có kết quả mô phỏng, dùng thư mục `--out` mới khi muốn tái chạy để giữ nguyên bằng chứng cũ. Chi tiết phương pháp và cách diễn giải ở [hướng dẫn nghiên cứu](docs/RESEARCH_GUIDE.md).

## Cấu trúc thư mục

| Thư mục | Vai trò |
|---|---|
| `src/ssi_api/` | Lớp kết nối: xác thực, phân trang, giới hạn tần suất, xử lý lỗi |
| `src/data/` | Lưu SQLite, nạp dữ liệu, kiểm tra chất lượng |
| `src/finance/` | Logic tài chính thuần (nến, mẫu hình, chỉ báo), không I/O |
| `src/analytics/` | Kiểm chứng: lợi suất sau tín hiệu, xác suất có điều kiện, đa kiểm định |
| `src/app/` | Giao diện Streamlit |
| `scripts/` | Các lệnh chạy: cập nhật dữ liệu, đăng ký lịch Windows, chụp ảnh, chạy nghiên cứu |
| `scripts/maintenance/` | Công cụ sắp xếp/hoàn tác thư mục hiện có |
| `archive/` | Trình cài cũ và bản sao lưu; không chạy khi mở dashboard |
| `tests/` | Kiểm thử tự động |
| `data_sample/` | Dữ liệu mẫu nhỏ để chạy không cần API key |
| `docs/` | Ghi chú API đã kiểm chứng, định nghĩa mẫu hình (`pattern_definitions.md`) |
| `report/` | Báo cáo cuối kỳ |

Quy tắc phụ thuộc: `ssi_api` → `data` → `finance` → `analytics` → `app`. `finance` không gọi API và không đọc/ghi dữ liệu. `app` không gọi API trực tiếp.

## Cấu trúc dữ liệu

SQLite (mặc định `storage/radar.db`, đổi bằng biến `RADAR_DB_PATH`), khóa chính `(symbol, trading_date)`, ngày dạng `YYYY-MM-DD`:

| Bảng | Nội dung |
|---|---|
| `ohlc_daily` | Nến ngày từ `/data/ohlc`: open, high, low, close, volume, value |
| `summary_daily` | Tổng hợp giao dịch từ `/data/securitiesSummary`: priceChange, khối lượng khớp, dòng tiền nước ngoài, room... |
| `quality_issues` | Vấn đề chất lượng theo (mã, ngày, loại): lỗi và cảnh báo, để truy vết |
| `ingest_log` | Mỗi lần nạp một mã: thời điểm, khoảng ngày, số dòng, số lỗi/cảnh báo, trạng thái |

Luồng nạp: lấy từ API, bỏ nến chưa đóng (trước 15:00 giờ Việt Nam), kiểm tra chất lượng, loại dòng lỗi, đối chiếu chéo hai nguồn, rồi ghi trong một giao dịch nguyên tử. `db.load_ohlc()` trả nến **sắp xếp tăng dần** để đưa thẳng vào `finance`. Khi API sửa giá lịch sử (có thể do điều chỉnh quyền), `ingest` phát hiện thay đổi ở các phiên chồng lấn và nạp lại toàn bộ mã với chốt an toàn trước khi thay thế. Cần kiểm chứng quy ước điều chỉnh giá của nguồn trước khi diễn giải lợi suất quanh ngày quyền. Bảng `quality_issues` ghi vết mọi dòng bị loại hoặc bị cảnh báo.

## Cách đọc dashboard

Trong Radar, mở **Đọc tín hiệu từng bước**, chọn một tín hiệu rồi đọc ý nghĩa, trạng thái và điều kiện theo dõi. Từ điển và chỉ báo chi tiết nằm trong các mục mở rộng. Trong Thống kê cảnh báo, mở mục **Đánh giá ngoài mẫu · train trước, test sau** để xem báo cáo giữ lại theo thời gian đã chạy bằng `--oos`. Phân biệt tỷ lệ hoàn thành ba nến với kết quả lợi suất sau tín hiệu. Xem [hướng dẫn giao diện](docs/UPGRADE_FEATURES.md).

## Giới hạn đã biết

Xem [hướng dẫn nghiên cứu](docs/RESEARCH_GUIDE.md) và `docs/api_notes.md`. Q2 có bootstrap-t cả train/test, Q3 có đánh giá sai số dự báo ghép cặp, kèm kịch bản trượt giá. Vẫn cần lịch sàn chính thức, thành phần VN30 theo từng thời điểm và xác minh giá điều chỉnh/sổ lệnh để trả lời những câu hỏi dữ liệu ngày chưa hỗ trợ. Holdout hiện là hồi cứu; h=1 là phép đo biến động, chưa phải một giao dịch cổ phiếu Việt Nam khả thi.
