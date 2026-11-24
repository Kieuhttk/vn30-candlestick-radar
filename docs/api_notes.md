# Ghi chú kiểm chứng API SSI FastConnect

Nguồn: tài liệu SSI Developer Portal và các lần chạy thật bằng `python -m ssi_api.probe FPT` (06/11/2026).
Phần "chưa kiểm chứng" cần ghi rõ trong báo cáo, không coi là sự thật.

## Đã kiểm chứng khi chạy thật

| Nội dung | Kết quả |
|---|---|
| Xác thực | `POST /api/v3/auth/token` với `apiKey` + `apiSecret`, không truyền `otp` (chỉ đọc dữ liệu) |
| Ngày của `/data/ohlc` | Phải là `YYYY/MM/DD HH:mm:ss`. Dạng `YYYY/MM/DD` (như docs ghi) bị lỗi `400213` |
| Ngày của `/data/securitiesSummary`, `/data/corporateActions` | `YYYY/MM/DD` chạy được |
| `pageSize` | 100 chạy được; yêu cầu 1000 vẫn được chấp nhận (một lần trả 956 dòng từ 01/2023) |
| Thứ tự dòng của `ohlc` | Mới nhất trước |
| Đơn vị | Giá tính theo đồng (ví dụ 53900), khối lượng theo cổ phiếu, giá trị theo đồng |
| Kiểu dữ liệu | Mọi trường số trả về dạng chuỗi |
| Đối chiếu chéo | FPT, 34 phiên: `close` và `volume` (ohlc) khớp `close` và `totalMatch` (securitiesSummary) ở 34/34 ngày |
| Giới hạn tần suất | Header `X-RateLimit-Limit: 20`; chưa thấy header RESET |
| `corporateActions` | 5 ngày gần nhất trả 432 dòng cho toàn thị trường, nhiều dòng không phải sự kiện giá (ví dụ đăng ký giao dịch nội bộ) và `exrightDate`, `ratio` có thể rỗng |

## Phát hiện quan trọng: giá OHLC của SSI là giá ĐÃ ĐIỀU CHỈNH ngược (chạy `--ref-report` ngày 07/11/2026)

| Bằng chứng | Kết luận |
|---|---|
| Giá đóng cửa FPT ngày 03/01/2023 là 44.607,233 (không phải bội số của bước giá 10/50/100 đồng) | `close` không phải giá thô |
| `priceChange` cùng ngày là số nguyên (3.100) | `priceChange` là giá thô, khác thang với `close` |
| `priceChange / (close - đóng cửa hôm trước)` của FPT giảm bậc thang theo thời gian (1,79 → 1,54 → 1,52 → 1,32 → 1,13 → 1,10) rồi về đúng 1,0 ở quý gần nhất | Tỷ số là nghịch đảo hệ số điều chỉnh tích lũy; mỗi bậc là một lần đi quyền |
| ECO: đóng cửa 03/11/2026 là 18.726,49 = 19.850 x 0,9434, với 0,9434 là `ratio` của đợt cổ tức 6% có ngày đi quyền 05/11/2026 | SSI điều chỉnh bằng đúng `ratio` của `corporateActions` (làm tròn 4 chữ số), áp dụng cho cả phiên trước ngày đi quyền |
| FPT: chỉ 1 trên 957 phiên lệch giữa lợi suất theo `close` và `priceChangePercentage` | Chuỗi điều chỉnh nhất quán |

Hệ quả:

- Chuỗi giá liên tục qua ngày đi quyền: không có nến giả do chia cổ tức. Cả bốn giá của một phiên nhân cùng một hệ số nên hình dạng nến không đổi.
- **Giá lưu trong CSDL phụ thuộc thời điểm nạp**: mỗi ngày đi quyền mới làm đổi thang của toàn bộ lịch sử. `ingest` phát hiện (phiên chồng lấn bị đổi giá) và tự nạp lại toàn bộ lịch sử của mã đó.
- Giả thuyết cũ "giá tham chiếu = `close - priceChange`" **sai** (trừ hai đại lượng khác thang) và đã bị bỏ. Giá tham chiếu cùng thang với `close` có thể lấy gần đúng bằng đóng cửa phiên liền trước (đã điều chỉnh).
- `volume` và `value` nhiều khả năng là số thô (chưa điều chỉnh): chưa kiểm chứng. So sánh khối lượng qua ngày đi quyền có thể lệch.

## Điểm lạ chưa giải thích được

- ECO thiếu hai phiên 04/11 và 05/11/2026 trong CSDL dù phiên 06/11 cho thấy 05/11 có giao dịch (tham chiếu thô 18.750). Dùng `--log` và `--issues --symbols ECO` để truy vết (dòng bị loại vì lỗi chất lượng sẽ có ghi nhận).
- ECO lệch `priceChangePercentage` ở 370 phiên và có nhiều biên độ trên 7,5% ở năm 2024: nhiều khả năng do ECO từng niêm yết UPCOM (biên độ ±15%, giá tham chiếu là bình quân phiên trước, chưa kiểm chứng). Với mã chuyển sàn, biên độ `limit_pct` đổi theo thời kỳ; mặc định 0,07 chỉ đúng cho HOSE.

## Chưa kiểm chứng

- `ratio` trong `corporateActions`: có vẻ là hệ số điều chỉnh giá với cổ tức cổ phiếu (6% cho 0,9434; 15% cho 0,8696), chưa rõ với cổ tức tiền mặt.
- API không có endpoint rõ ràng cho thành phần rổ VN30: dùng danh sách hiện hành từ HOSE, ghi nguồn và ngày lấy.
- Chu kỳ của giới hạn tần suất (giây hay phút).
