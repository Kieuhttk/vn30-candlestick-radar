# Nguồn lịch nghỉ dùng cho đối chiếu nghiên cứu

`vn_market_holidays_2021_2026.csv` lưu các khoảng nghỉ cuối cùng đã công bố, cùng URL nguồn và ngày đối chiếu 24/11/2026. Ngày thứ Bảy/Chủ nhật luôn đóng cửa; không coi ngày làm bù của cơ quan hành chính là phiên chứng khoán. Script không dùng mạng lúc chạy, không phụ thuộc package lịch bên ngoài và không thay lịch của nghiên cứu chính.

VSD/VSDC công bố **lịch nghỉ thanh toán**. Cột `exchange_reference` đối chiếu thêm **lịch nghỉ giao dịch** HNX/HOSE; không dùng lịch thanh toán như bằng chứng duy nhất về ngày giao dịch. Tài liệu HOSE năm 2025 là bản thông báo gốc được lưu trên máy chủ Vietstock. Một số trang HNX chỉ truy cập được qua bản lập chỉ mục khi kiểm tra; giữ URL bài gốc để người đọc xác minh.

| Năm | Nguồn chính | Điểm cần lưu ý |
|---|---|---|
| 2021 | [VSD](https://vsdc.vn/vi/ad/76898), [HNX](https://hnx.vn/vi-vn/chi-tiet-lich-nghi-gd-60010564.html?_page=1) | Khoảng dữ liệu nghiên cứu bắt đầu 16/11, sau các dịp nghỉ của năm |
| 2022 | [VSD](https://vsdc.vn/vi/ad/144999), [HNX](https://hnx.vn/vi-vn/chi-tiet-lich-nghi-gd-60013320.html?_page=1) | Có ngày nghỉ bù 03/01, 11/04, 02–03/05 |
| 2023 | [VSD cập nhật](https://vsdc.vn/vi/ad/155165), [HNX](https://www.hnx.vn/vi-vn/m-tin-tuc-hnx/Thong%20bao%20ve%20viec%20cong%20bo%20lich%20nghi%20giao%20dich%20trong%20nam%202023-60015701-1.html) | Tết 20–26/01; chuỗi nghỉ 29/04–03/05 gồm cuối tuần |
| 2024 | [VSD](https://vsdc.vn/vi/ad/159293), [HNX](https://hnx.vn/vi-vn/m-tin-tuc-hnx/Thong%20bao%20ve%20viec%20cong%20bo%20lich%20nghi%20giao%20dich%20trong%20nam%202024-60017878-1.html) | [Điều chỉnh VSDC](https://vsdc.vn/vi/ad/170099), [HNX](https://www.hnx.vn/vi-vn/chi-tiet-lich-nghi-gd-60018631.html?_page=1): thêm 29/04 vào khoảng nghỉ 29/04–01/05 |
| 2025 | [VSDC cập nhật](https://vsdc.vn/vi/ad/178644), [thông báo HOSE](https://static2.vietstock.vn/vietstock/2024/12/26/20241226_20242612_thong_bao_ve_lich_nghi_2025.pdf) | Nghỉ 30/04–02/05; thứ Bảy 26/04 không giao dịch |
| 2026 | [VSDC](https://vsdc.vn/vi/ad/189388), [HOSE](https://www.hsx.vn/vi/tin-tuc/hose-thong-bao-lich-nghi-giao-dich-nam-2026/2437411) | [Cập nhật Tết Dương lịch](https://vsdc.vn/vi/ad/190545): nghỉ 01–02/01; Quốc khánh 31/08–02/09 |

Ngày 24/11/2026 được bổ sung theo [VSDC](https://vsdc.vn/vi/ad/202680) và [HNX](https://hnx.vn/vi-vn/chi-tiet-lich-nghi-gd-60023839.html?_page=1). Ngày này nằm **sau** ngày chốt 16/11 của bộ kết quả mẫu, vì vậy không ảnh hưởng số phiên của lần audit được bàn giao.

Phạm vi tham chiếu là 01/01/2021–31/12/2026. Ngoài phạm vi này script dừng, không tự ngoại suy. Đây là đối chiếu ngày nghỉ đã công bố, không phải danh mục đầy đủ mọi sự cố/ngừng giao dịch đột xuất hoặc mọi ngày ngừng của từng cổ phiếu. Thông báo được thu thập hồi cứu, không phải bằng chứng lịch này đã được đăng ký trước khi nghiên cứu.
