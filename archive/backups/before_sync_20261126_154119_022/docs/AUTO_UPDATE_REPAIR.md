# Sửa lịch cập nhật SSI sau khi sắp xếp thư mục

## Vì sao DB có thể vẫn dừng ở 18/11?

Chọn ngày đã đóng là quy tắc giới hạn nến khi ingest/hiển thị. Quy tắc đó chỉ có tác dụng **khi ingest thực sự chạy**. Dashboard đang đọc SQLite; mở trình duyệt hoặc bấm “Đọc lại SQLite” không gọi SSI.

Lịch Windows đã đăng ký trước khi di chuyển file có thể vẫn chứa `...\update_data.py` ở thư mục gốc. Sau khi file được chuyển vào `scripts/data/`, lịch cũ không tự cập nhật đường dẫn. Đây là một nguyên nhân có cơ sở từ mã đã kiểm tra, chưa phải kết luận về trạng thái Task Scheduler trên máy của bạn.

Các nguyên nhân khác cần đối chiếu: chưa đăng ký task, máy tắt/ngủ hoặc chưa đăng nhập, tác vụ bị Disable, SSI lỗi/chưa công bố, hoặc dashboard đọc một DB khác. Một tiến trình kết thúc với mã 0 không đảm bảo dữ liệu đã mới.

## Cách áp dụng

Bản sửa cập nhật trực tiếp hai file hiện có: `scripts/data/update_data.py` và `scripts/system/install_update_task.py`. Không cần chạy trình cài hoặc tạo script sửa lỗi mới. Nếu nhận gói file thay thế, dừng các lần cập nhật đang chạy, lưu bản cũ vào `archive/backups/`, rồi chép đè theo đúng đường dẫn trong gói.

Chạy từng dòng PowerShell, không dán dấu PS>, >> hoặc dấu gạch chéo cuối dòng:

```powershell
Set-Location C:\Users\KIEU\vn30-candlestick-radar
.\.venv\Scripts\python.exe scripts/data/update_data.py --db storage/radar.db
.\.venv\Scripts\python.exe scripts/system/install_update_task.py --at 18:00 --retry-at 19:00
.\.venv\Scripts\python.exe scripts/system/install_update_task.py --status
```

Lệnh `update_data.py` ở trên chạy bù **ngay trong terminal**, sao lưu SQLite trước và in ngày cuối của từng mã khi xong. Nó nạp qua module ingest hiện có, giữ cơ chế bảo vệ refresh. Nếu module/API gặp lỗi, xem đúng file log được in ra. Không dùng full-refresh chỉ để chữa lỗi lịch.

Lệnh đăng ký dùng `Register-ScheduledTask -Force` thay task cũ `VN30Radar-UpdateSSI` bằng đường dẫn mới. Chạy chính 18:00, chạy lại 19:00 từ thứ Hai đến thứ Sáu để lấy dữ liệu công bố muộn, chạy bù khi người dùng đăng nhập Windows, bật StartWhenAvailable và thử lại khi tiến trình lỗi. Có thể thêm `--run-now` khi đăng ký để yêu cầu Windows chạy bù trong nền; không cần nếu vừa chạy cập nhật trực tiếp ở bước trước.

**Các giờ trên theo múi giờ của máy Windows.** Nếu muốn 18:00 Việt Nam, máy phải đặt đúng múi giờ UTC+7. Script hiển thị múi giờ nhưng không tự thay cài đặt hệ thống. Máy phải bật, thức, có mạng và người dùng đã đăng nhập; task này không thể tải dữ liệu khi máy tắt. Không đánh thức máy hoặc lưu mật khẩu Windows.

## Đọc kết quả kiểm tra task

`--status` chỉ kiểm tra, không tạo task và không gọi SSI:

- `CHUA CAI LICH`: chưa tìm thấy task; mã thoát 3.
- `SAI DUONG DAN`: action còn trỏ file cũ hoặc Python không đúng venv; mã thoát 4; đăng ký lại bằng lệnh ở trên.
- `DUONG DAN LICH DUNG`: action dùng đúng script hiện tại. Đọc thêm State, LastRunTime, LastTaskResult, NextRunTime. State Disabled nghĩa là lịch đang bị tắt; đăng ký lại sẽ tạo cấu hình bật mới.
- LastTaskResult = 0 chỉ nghĩa tiến trình lần trước thành công. Khi task đang Running, giá trị LastTaskResult có thể còn thuộc lần trước; kiểm tra log sau khi chạy xong.

Xem lại ngày DB mà không nạp API:

```powershell
.\.venv\Scripts\python.exe scripts/data/update_data.py --db storage/radar.db --status
```

Lệnh này in đường dẫn DB tuyệt đối và ngày cuối đã đóng của từng mã. Dùng đúng đường dẫn đó trong trường “File SQLite” của dashboard. Khi trang đang mở, dashboard kiểm tra thay đổi DB/WAL mỗi 60 giây rồi đọc lại. Nếu trước đó đang xem phiên mới nhất, ngày quét đi theo phiên mới được nạp; nếu chủ động xem một ngày lịch sử, ứng dụng giữ ngày đó. Nút **Về phiên gần nhất** trở về ngày mới nhất thực sự đã lưu. Có thể bấm **Đọc lại SQLite** để cập nhật ngay; các nút này không tự gọi API.

Wrapper ghi `report/update_logs/latest_status.json` bằng thay file nguyên tử: thời điểm bắt đầu/kết thúc, DB, log, trạng thái tiến trình và ngày đã lưu từng mã. Dashboard chỉ đọc trạng thái nếu đường dẫn DB khớp, báo khi nạp thất bại hoặc chưa xác nhận đủ mốc đối chiếu. Nếu tiến trình bị ngắt trước khi ghi hoàn tất, trạng thái có thể còn `running`; đối chiếu thời điểm và log, không hiểu là cam kết tiến trình còn sống. File không chứa khóa API hay nội dung phản hồi xác thực.

Bộ lọc nến hiện loại mọi ngày sau mốc đóng, kể cả dữ liệu gắn ngày tương lai hoặc cuối tuần, và quy đổi timestamp có múi giờ về UTC+7. Audit ghi `unclosed_or_future_date` thay vì tự xóa dữ liệu. Dashboard ẩn các nến đó và hiển thị số lượng để truy vết. Khối lượng âm/vô hạn được đánh dấu lỗi; thiếu khối lượng không tự biến thành khối lượng bằng 0.

Mốc đối chiếu của wrapper là ngày thường đã qua 15:00 UTC+7, lùi qua cuối tuần. Đây **không phải lịch nghỉ lễ chính thức** và không ép SSI phải có dữ liệu. Ngày 20/11 trước 15:00 đối chiếu 19/11; sau 15:00 đối chiếu 20/11 nếu là phiên giao dịch bình thường. Không tự tạo nến để lấp phiên thiếu.

## Nếu vẫn dừng ở 18/11

1. Nếu task không có lần chạy sau 18/11 hoặc trỏ script cũ: lỗi thuộc lịch/đường dẫn, đăng ký lại.
2. Nếu log wrapper được tạo nhưng tiến trình ingest không chạy hoặc lỗi: xem lỗi ở `report/update_logs/update_*.log`.
3. Nếu ingest có chạy nhưng ngày cuối không tăng: đối chiếu trạng thái từng mã, ngày SSI trả về, lỗi xác thực/mạng và cảnh báo refresh. Không coi việc mở dashboard là ingest đã chạy.
4. Nếu terminal báo DB đã lên 19/20 nhưng giao diện vẫn hiển thị 18: kiểm tra đường dẫn DB, bấm đọc lại và đổi ngày quét.

Các test đi kèm kiểm tra đường dẫn, tham số đăng ký, mốc giờ UTC+7, trạng thái chỉ đọc và điều phối nạp bằng dữ liệu giả. Tác vụ Windows thật và API SSI phải được kiểm tra trên máy Windows của bạn; môi trường tạo bản vá là Linux.
