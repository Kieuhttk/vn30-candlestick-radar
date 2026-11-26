# Định nghĩa mẫu hình nến

Nguồn khái niệm: slide S7 (Phân tích kỹ thuật - Biểu đồ nến Nhật). Cài đặt: `src/finance/candles.py`, `src/finance/patterns.py`.
Ngưỡng mặc định là quy ước vận hành, **chưa tối ưu**; khảo sát độ nhạy đã được cài trong `src/analytics/study.py` và xuất qua `scripts/run_study.py --sensitivity`.

## Quy ước chung

- Nến tăng: `close > open`. Nến giảm: `close < open`. Thân = |close - open|, biên độ = high - low.
- "Thân dài/ngắn" so với **trung bình thân của 10 nến trước** (không gồm nến đang xét).
- Xu hướng trước mẫu hình: thống kê t của lợi suất log trung bình trong 10 phiên kết thúc tại nến **ngay trước** nến đầu của mẫu hình; tăng nếu t >= 1, giảm nếu t <= -1.
- Tín hiệu gắn vào nến cuối của mẫu hình. Nến chỉ biết sau khi đóng cửa nên chỉ giao dịch được từ **mở cửa phiên kế tiếp**.
- Phiên khóa trần/sàn (O=H=L=C, biên độ 0) không thuộc mẫu hình nào.

## Bảng mẫu hình

| Mẫu hình | Điều kiện chính |
|---|---|
| Doji | thân <= 10% biên độ trung bình 10 nến trước |
| Doji chuồn chuồn / bia mộ | Doji và bóng một phía <= 10% biên độ, bóng phía kia >= 60% biên độ |
| Doji chân dài | Doji và mỗi bóng >= 30% biên độ |
| Marubozu tăng/giảm | thân dài, mỗi bóng <= 5% biên độ |
| Con quay | thân ngắn, không phải Doji, cả hai bóng dài hơn thân |
| Hammer / Hanging man | thân không phải Doji, bóng dưới >= 2 x thân, bóng trên <= 10% biên độ. Hammer sau xu hướng giảm, Hanging man sau xu hướng tăng |
| Inverted hammer / Shooting star | như trên nhưng bóng trên dài, bóng dưới ngắn. Chưa yêu cầu gap của Shooting star |
| Bao trùm tăng/giảm | xu hướng ngược; nến 1 ngược màu; thân nến 2 trùm hết thân nến 1 và lớn hơn |
| Piercing | sau xu hướng giảm; nến 1 giảm, thân dài; nến 2 tăng, mở thấp hơn đóng cửa nến 1, đóng trên điểm giữa thân nến 1 nhưng dưới mở cửa nến 1. Chế độ `strict_gap`: mở thấp hơn **đáy** nến 1 |
| Dark Cloud Cover | đối xứng Piercing sau xu hướng tăng; `strict_gap`: mở cao hơn **đỉnh** nến 1 |
| Harami tăng/giảm | xu hướng ngược; nến 1 thân dài; thân nến 2 nằm trong thân nến 1, ngược màu và nhỏ hơn |
| Sao mai / Sao hôm | nến 1 thân dài ngược xu hướng; nến 2 thân ngắn có gap theo **thân** nến; nến 3 ngược màu nến 1, đóng qua điểm giữa thân nến 1 |
| Cảnh báo "sắp có Sao mai/Sao hôm" | đã có nến 1 và nến 2 như trên, chờ nến 3 ở phiên kế tiếp |

## Chưa cài đặt

Abandoned Baby, Three White Soldiers (có trong slide), mẫu hình giá lớn của slide S8 (hai đỉnh/đáy, vai đầu vai, tam giác).

## Dữ liệu giá và cờ trần/sàn

Giá OHLC từ SSI là giá đã điều chỉnh ngược về hiện tại (xem `api_notes.md`), nên chuỗi liên tục qua ngày đi quyền và hình dạng nến không bị méo bởi chia cổ tức. Giá tham chiếu dùng để tính gap và cờ trần/sàn mặc định là đóng cửa phiên liền trước (đã điều chỉnh).

`limit_up`/`limit_down` đánh dấu nến đóng cửa cách giá tham chiếu từ (biên độ - 0,5%) trở lên. Mặc định biên độ 7% (HOSE); với mã từng niêm yết sàn khác (HNX 10%, UPCOM 15%) phải truyền `limit_pct` tương ứng cho từng thời kỳ.
