# Dữ liệu demo offline — VN30 Candlestick Radar

`radar_demo.db` là DB SQLite đi kèm kho mã, dùng để chạy dashboard offline và đối chiếu bộ nghiên cứu chốt **27/11/2026**. Đây là dữ liệu thị trường SSI FastConnect đã được chuẩn hóa theo cấu trúc của dự án.

## 1. Phạm vi dữ liệu

| Thông tin | Giá trị |
|---|---|
| Nguồn | SSI FastConnect: nến ngày và giao dịch tổng hợp |
| Số mã | 30 |
| Khoảng ngày OHLC | 16/11/2021–27/11/2026 |
| Phiên dữ liệu cuối | **27/11/2026** |
| Số dòng OHLC | 35.759 |
| Số dòng giao dịch tổng hợp | 36.166 |
| Thời điểm đóng gói | 27/11/2026, 20:07:13 (UTC+7) |
| Phiên bản mã tham chiếu | [`6570a33`](https://github.com/Kieuhttk/vn30-candlestick-radar/tree/6570a336f7a950a6e72d8a1e0a5051677ba56536) |

Rổ mã được lưu cố định trong `src/data/universe_vn30.txt`; độ dài lịch sử của từng mã khác nhau. Bộ demo khớp dấu vân tay đầu vào của kết quả ngoài mẫu tại `report/oos_verified/`.

## 2. Các tệp đi kèm

| Tệp | Nội dung |
|---|---|
| `radar_demo.db` | Dữ liệu thị trường, cảnh báo chất lượng và cấu trúc nhật ký. |
| `metadata.json` | Ngày chốt, phiên cuối, thời gian đóng gói, SHA-256 của DB và manifest nguồn. |
| `README.md` | Phạm vi và cách sử dụng bộ demo. |

DB có bốn bảng: `ohlc_daily`, `summary_daily`, `quality_issues` và `ingest_log`. Bảng nhật ký `ingest_log` được làm rỗng khi đóng gói; dữ liệu giá, tổng hợp và chất lượng được giữ lại. Vì vậy, tab **Chất lượng** giải thích rằng demo không chứa nhật ký vận hành.

DB lưu 437 warning: 407 `missing_in_ohlc`, 29 `limit_exceeded` và 1 `long_gap`. Dashboard suy thêm 14 mục thiếu phiên từ lịch thị trường, tạo tổng 451 mục cần đối chiếu. Các mục này không đại diện cho 451 lỗi giá độc lập.

## 3. Chạy dashboard bằng Demo

Các lệnh chạy từ thư mục gốc `vn30-candlestick-radar/`, sau khi cài thư viện theo [README chính](../README.md#cai-dat):

```powershell
$env:RADAR_DB_PATH = "data_sample/radar_demo.db"
.\.venv\Scripts\python.exe -m streamlit run src/app/main.py
```

Mở **http://localhost:8501** và chọn **Demo báo cáo** ở sidebar. Mục **Nguồn dữ liệu** hiển thị `data_sample/radar_demo.db`; phiên mới nhất của demo là **27/11/2026**. Sau khi cài thư viện, chế độ này hoạt động không cần khóa API hoặc kết nối SSI.

Các kết quả toàn mẫu, ngoài mẫu và kiểm tra bổ sung được đọc từ các thư mục `report/` đi kèm. Riêng phần ngoài mẫu kiểm tra protocol, mã băm CSV và dấu vân tay DB trước khi hiển thị.

## 4. Demo và Live

| Chế độ | DB | Cách sử dụng |
|---|---|---|
| **Demo báo cáo** | `data_sample/radar_demo.db` | Giữ dữ liệu cố định đến 27/11/2026 để trình diễn và đối chiếu báo cáo. |
| **Hằng ngày (Live)** | `storage/radar.db` | Tiếp tục nạp các phiên mới bằng ingest hoặc lịch cập nhật SSI. |

Bộ chọn nằm trong phần **Chế độ dữ liệu**. Khi chuyển nguồn, ngày quét về phiên đã đóng mới nhất có trong DB vừa chọn; trang và bộ lọc mã được giữ lại. Dashboard đọc SQLite; việc lấy dữ liệu SSI được thực hiện bằng tác vụ riêng.

DB demo được giữ cố định để bảo toàn nguồn của nghiên cứu. Quy trình cập nhật Live sử dụng `storage/radar.db`, như mô tả trong [hướng dẫn vận hành](../README.md#van-hanh).

## 5. Metadata và kiểm tra tệp

`metadata.json` ghi:

- `cutoff_date`: ngày chốt hồ sơ, `2026-11-27`.
- `last_market_session`: phiên cuối của DB, `2026-11-27`.
- `prepared_at`: thời điểm đóng gói theo UTC+7.
- `demo_sha256`: SHA-256 của tệp demo.
- `source_manifest_sha256`: SHA-256 của `report/oos_verified/manifest.json`.

Kiểm tra ngày phiên và mã băm bằng thư viện chuẩn Python:

```powershell
.\.venv\Scripts\python.exe -c "import hashlib,json; from pathlib import Path; p=Path('data_sample/radar_demo.db'); m=json.loads(p.with_name('metadata.json').read_text(encoding='utf-8')); print('Last session:', m['last_market_session']); print('SHA-256 matches:', hashlib.sha256(p.read_bytes()).hexdigest()==m['demo_sha256'])"
```

Kết quả của bộ đi kèm:

```text
Last session: 2026-11-27
SHA-256 matches: True
```

## 6. Giới hạn sử dụng

Dữ liệu phản ánh phiên bản giá SSI tại thời điểm thu thập, có thể bao gồm điều chỉnh quá khứ. Rổ cố định không tái dựng thành phần VN30 từng ngày. Các cảnh báo thiếu phiên và biên độ được trình bày cùng kết quả, không được điền bằng giá giả.

Bộ demo phục vụ học tập, trình diễn và tái lập nghiên cứu. Tỷ lệ hoàn thành mẫu hình và hướng lý thuyết không phải xác suất có lãi hoặc khuyến nghị mua/bán.
