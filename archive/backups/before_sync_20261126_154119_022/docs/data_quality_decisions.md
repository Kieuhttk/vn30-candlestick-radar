| Nhóm cảnh báo | Quyết định sử dụng dữ liệu |
|---|---|
| BSR thiếu 07–16/01/2025 | Khoảng chuyển sàn; không tạo nến để lấp khoảng trống, không dùng mẫu hình đi qua khoảng này |
| MCH thiếu 18–24/12/2025 | Khoảng chuyển sàn; xử lý tương tự BSR |
| MCH thiếu 05/10/2022 | Chưa xác minh đầy đủ; giữ cảnh báo và loại cửa sổ nhận diện đi qua ngày này |
| 406 dòng summary VPL không có OHLC | Trong bản DB đã kiểm tra, các dòng này có `close=0`, `total_match=0`; không dùng chúng để tạo nến |
| 29 cảnh báo vượt 7% | Đều thuộc giai đoạn trước khi BSR/MCH lên HOSE; cần xét đúng sàn và giá tham chiếu, chưa coi là bằng chứng giá sai |