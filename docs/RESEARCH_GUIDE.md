# Hoàn thiện nghiên cứu Q1–Q3

Có hai luồng nghiên cứu: khám phá toàn lịch sử và đánh giá giữ lại theo thời gian 70%/30% bằng `--oos`. Ngưỡng nhận diện giữ nguyên; mức nền Q2 và xác suất Q3 chỉ ước lượng trên train. Không triển khai học máy Q4. SSI đã được giảng viên chấp thuận làm nguồn dữ liệu của đồ án.

## 1. Mã nguồn và cách kiểm tra

Các thay đổi nghiên cứu đã được hợp nhất vào `src/analytics/`, `src/finance/`, `src/app/signal_workspace.py` và các lệnh chạy trong `scripts/`. Sửa trực tiếp module phụ trách chức năng; không chạy lại các trình cài/nâng cấp cũ trong `archive/installers/` vì chúng có thể khôi phục mã cũ.

Chạy kiểm tra trong thư mục gốc đồ án:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_research_protocol.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

### Số kiểm thử của bản bàn giao ngày 22/11/2026

Toàn bộ gói mã hiện có **196 test đạt** (không failed/error/skip), gồm 126 test trước và 70 trường hợp bổ sung trực tiếp cho các lớp lõi:

| Tệp bổ sung | Số trường hợp | Nội dung |
|---|---:|---|
| `tests/test_candles.py` | 16 | Hình học tính tay, ngưỡng dùng lịch sử trước, dữ liệu hỏng/vô cực, tham chiếu và không nhìn trước |
| `tests/test_patterns.py` | 20 | Ca dương tính cho đủ 19 mẫu hình, xu hướng ngược, gap, điểm giữa, setup trước nến xác nhận |
| `tests/test_db.py` | 7 | Khóa upsert, NULL, lọc truy vấn, join theo mã/ngày, rollback, URI tiếng Việt và chỉ đọc |
| `tests/test_quality.py` | 14 | Phân loại error/warning, đối chiếu hai nguồn, ngày thiếu, ngày tham chiếu và độ cũ |
| `tests/test_ssi_client.py` | 13 | Session giả, token, 429, phân trang, định dạng ngày, số và giới hạn chờ |

Nhật ký và JUnit nằm ở `report/verification/`; `test_counts.csv` liệt kê đủ 15 module test và `test_manifest.json` ghi phiên bản thư viện/hash nguồn. Bộ 196 test cũng đạt khi mô phỏng mặc định CP1252 trên Linux; chưa phải lần chạy Windows thật. Không gọi SSI thật trong kiểm thử. Báo cáo có thể ghi 196 cho đúng bản bàn giao này; nếu giữ thêm test riêng trên máy bạn, chạy lại và dùng số thực tế của bản nộp.

Test mới phát hiện bộ mô tả nến chưa chặn `high=+inf`; `validate_ohlc` đã chặn mọi OHLC không hữu hạn trước khi phân loại. Không đổi các ngưỡng nhận diện hoặc tối ưu theo lợi suất. Hash `candles.py` thay đổi: khi chạy lại nghiên cứu đã khóa bằng mã cũ, giữ nguyên thư mục báo cáo cũ trong archive rồi tạo phiên bản nghiên cứu mới; không xóa riêng protocol để trộn bảng cũ/mới.

## 2. Chạy nghiên cứu chính thức

```powershell
.\.venv\Scripts\python.exe scripts/run_study.py --db storage/radar.db --sensitivity
```

Luồng này đọc SQLite, không gọi API và không sửa dữ liệu. Chạy sau khi ingest kết thúc. Mặc định dùng toàn bộ lịch sử đã có của 30 mã trong `src/data/universe_vn30.txt`; ngày cuối không vượt ngày đã đóng theo chốt 15:00 UTC+7. Chốt ngày cụ thể khi hoàn thiện báo cáo, ví dụ:

```powershell
.\.venv\Scripts\python.exe scripts/run_study.py --db storage/radar.db --asof 2026-11-18 --sensitivity --out report/tables_final
```

Chỉ dùng ví dụ 18/11 nếu DB thực sự đã chứa dữ liệu đó. Ngày nghỉ không tự tạo thêm nến. Nếu một mã trong rổ chưa có bất kỳ OHLC nào, chương trình dừng; thiếu phiên riêng lẻ được xử lý ở mức từng quan sát.

Luồng toàn mẫu hiện chỉ xuất mô tả, không tính p/q. Kiểm định chính thức chạy bằng `--oos` ở mục 2b, mặc định 39.999 lượt bootstrap cho mỗi tương phản. Có thể mất vài phút tùy máy; không đóng terminal khi đang tính. p có độ phân giải hữu hạn; với họ 280 giả thuyết, số lượt quá ít làm q rất bảo thủ. Chọn số lượt trước khi xem kết quả, không tăng dần chỉ để đạt ý nghĩa.

Các file đầu ra:

| File | Vai trò trong báo cáo |
|---|---|
| `q1_pattern_year.csv` | Q1: tần suất từng mẫu hình theo năm |
| `q1_pattern_symbol.csv` | Q1: tần suất từng mẫu hình theo mã |
| `signals.csv` | Nhãn lịch sử, gồm mẫu hình hoàn chỉnh và setup |
| `q2_summary.csv` | Q2 trong mẫu: lợi suất, mức nền, hướng lý thuyết; cột CI/p/q để trống |
| `q2_outcomes.csv` | Dữ liệu từng nhãn × kỳ hạn × mức phí, gồm trạng thái loại/chờ |
| `q3_summary.csv` | Q3: tỷ lệ setup hai nến hoàn thành ở phiên tiếp theo, CI Wilson |
| `q3_outcomes.csv` | Từng setup và trạng thái kết quả |
| `sensitivity_counts.csv` | Số nhãn theo 7 cấu hình ngưỡng |
| `sensitivity_q3.csv` | Q3 theo các cấu hình ngưỡng |
| `manifest.json` | Ngày chốt, rổ mã, tham số, phiên bản thư viện, hash mã/dữ liệu/bảng |

Không sửa tay CSV để khớp kết luận. Đóng băng một thư mục `tables_final` cùng manifest; lấy tất cả số liệu nghiên cứu từ lần chạy đó. `input_snapshot_sha256` băm các khung dữ liệu đã đọc trong cùng giao dịch, kể cả khi SQLite dùng WAL; `db_sha256` chỉ băm file DB vật lý tại lúc tạo manifest.

## 2b. Đánh giá ngoài mẫu theo thời gian

### Chạy chính thức trên máy bạn

```powershell
.\.venv\Scripts\python.exe scripts/run_study.py --oos --train-end 2025-05-20 --sensitivity --out report/oos_verified
```

Mốc 20/05/2025 là mốc 70% của bản dữ liệu đến 16/11/2026 đã được dùng để kiểm tra trong phiên làm việc này. Chỉ định mốc đó để so sánh cùng thiết kế khi DB của bạn có thêm ngày mới. Nếu muốn tạo một nghiên cứu khác với tỷ lệ 70% trên DB hiện tại, bỏ `--train-end`; chương trình chọn theo số **phiên thị trường chung**, không theo số nhãn hoặc số dòng từng mã.

Mặc định chạy 39.999 bootstrap. Khối Q2 dài `max(20, 5*h)` phiên; Q3 dài 20 phiên. Cần ít nhất 10 khối lịch ở mỗi phần, ngoài yêu cầu ≥30 nhãn và ≥20 ngày tín hiệu. Với test 374 phiên, h=10/20 chưa đủ 10 khối nên chỉ mô tả, chưa xuất CI/p/q. Đây là cách xử lý bảo thủ với cửa sổ lợi suất chồng lấn, không rút ngắn khối chỉ để có p. Để kiểm tra lệnh, dùng `--resamples 99 --out report/oos_smoke`; bảng thử không dùng làm kết quả chính thức. Không đổi mốc chia hoặc tham số chỉ để tìm ý nghĩa thống kê.

### Cách khóa và tránh dùng tương lai

1. `oos_protocol.json` được lưu trước khi tính Q2. Mốc train/test, rổ mã, ngưỡng, kỳ hạn, phí, số lượt bootstrap, độ dài khối, phiên bản NumPy/pandas và hash mã nghiên cứu được khóa. Dấu vân tay CSV dùng LF thống nhất giữa Windows/Linux. Bản phương pháp mới dùng protocol version 2; không ghi đè protocol cũ, hãy giữ bộ cũ và chạy vào `report/oos_verified`.
2. Lần chạy lại cùng thư mục giữ **nguyên mốc chia**, kể cả DB có thêm phiên. Không tự chia lại 70% trên phần dữ liệu dài hơn. Có thể nối thêm test nếu dữ liệu train không đổi.
3. Ngày cuối của mọi cửa sổ lợi suất train phải <= mốc train. Các nhãn có giá thoát hoặc nến xác nhận vượt ranh giới không được dùng để ước lượng. `purged_boundary` ghi rõ các hàng bị loại ở ranh giới; đây là số hàng nhãn × kỳ hạn × phí, không phải số tín hiệu độc lập.
4. Nhận diện ở đầu test được dùng lịch sử giá trước mốc chia làm warmup. Chỉ dùng dữ liệu đã có đến ngày tín hiệu; ngưỡng và xác suất không được tối ưu lại bằng test.
5. Lịch tham chiếu suy từ các mã đã có dữ liệu trước mốc chia, cố định danh sách đó khi xét phần test. Asset chỉ xuất hiện sau mốc không làm đổi lịch train.
6. Mã chưa có dữ liệu train có `n_baseline=0`. Lợi suất test vẫn mô tả được, nhưng tương phản Q2 không được tự lấy nền từ test để bù. `n_with_baseline` và `n_with_trend_baseline` ghi số quan sát có nền hợp lệ.
7. Dữ liệu train hoặc mã nghiên cứu thay đổi sẽ làm lệnh dừng thay vì âm thầm fit lại protocol cũ. Nếu API điều chỉnh giá lịch sử, giữ bộ kết quả cũ và dùng thư mục mới cho nghiên cứu phiên bản mới; ghi rõ snapshot/vintage khác.

### Q2: đánh giá mức nền đã fit

Giá vào mở cửa t+1, ra đóng cửa t+h, với h=1/3/5/10/20 và phí 20/40 bps. Hai nền cùng mã/kỳ hạn được ước lượng bằng train: nền mọi ngày hợp lệ và nền có điều kiện xu hướng. Chỉ các sự kiện bắt đầu trong test được chấm điểm ngoài mẫu. Train summary chỉ mô tả, không kiểm định rồi chọn các nhãn có p đẹp.

Q2 dùng **bootstrap-t hai mẫu**: lấy mẫu lại lịch train và test độc lập, nhưng dùng cùng khối ngày cho mọi mã trong từng phần để giữ phụ thuộc chéo mã. Mỗi lượt ước lượng lại mức nền bằng train rồi tính tương phản trên test; không dùng test để fit. Ngày không tín hiệu vẫn nằm trong lịch. Studentization dùng phương sai hàm ảnh hưởng theo khối. Khoảng 95% là bootstrap-t; p một phía cho tương phản đúng hướng >0. Họ BY chính cố định 14 hướng × 5 kỳ hạn × 2 phí × 2 nền = 280, kể cả giả thuyết không đủ dữ liệu. Cần ≥30 nhãn có nền, ≥20 ngày tín hiệu và ≥10 khối lịch trong cả train lẫn test. Chốt 10 khối là biện pháp bảo thủ từ chẩn đoán mô phỏng, không bảo đảm mọi p đã hiệu chuẩn. Thiết kế vẫn phụ thuộc tính dừng trong từng phần và cách chọn khối; không phải bằng chứng nhân quả hay lợi nhuận bán khống.

Phí được áp dụng cùng công thức cho tín hiệu và nền. Vì vậy p/q của chênh nền có thể giống nhau ở 20/40 bps do phép biến đổi chung; phí vẫn làm thay đổi lợi suất long ròng. Không chọn mức phí theo p/q.

### Q3: dự báo trước, chấm sau

- Với mỗi loại Sao mai/Sao hôm, từ train lấy k lần hoàn thành trong n lần đủ dữ liệu. Xác suất dự báo dùng Laplace `(k+1)/(n+2)`, định trước để tránh log loss vô hạn khi k=0 hoặc k=n.
- Mô hình nền dùng một xác suất Laplace chung cho cả hai loại, cũng chỉ ước lượng bằng train. Nếu một loại không có train nhưng loại còn lại có, dùng xác suất chung và ghi `pooled_train_fallback`; nếu toàn bộ train trống, không chấm dự báo đó.
- Trong test, giữ nguyên dự báo cho từng loại rồi chấm bằng nhãn đã biết. Pending/thiếu/lỗi nến kế tiếp không được biến thành thất bại hoặc âm thầm đưa vào mẫu số.
- `Brier = mean((p-y)^2)`; log loss là trung bình `-[y*log(p)+(1-y)*log(1-p)]`. Cả hai càng thấp càng tốt. Brier skill = `1 - Brier_model/Brier_baseline`; dương nghĩa sai số nhỏ hơn nền trong tập đã chấm.
- Lấy chênh điểm nền trừ điểm mô hình trên **cùng nhãn test**, rồi bootstrap tỷ số tổng chênh/tổng nhãn theo khối lịch chung cho các mã. Số dương là giảm sai số. Xuất CI/p và BY trong họ phụ định trước: Brier/log loss × Sao mai/Sao hôm/chung = 6. Họ này tách với họ Q2, không tuyên bố FDR chung trên cả hai họ. Suy luận này điều kiện trên hai bộ dự báo train đã khóa, không đo độ bất định của toàn thuật toán học khi thay tập train. CI tỷ lệ hoàn thành theo khối được xuất thêm; Wilson giữ để đối chiếu và không giả vờ xử lý phụ thuộc. Đây là dự báo **hoàn thành ba nến**, không phải xác suất đầu tư có lãi.

### File đầu ra và dashboard

| File | Nội dung |
|---|---|
| `oos_protocol.json`, `manifest.json` | Thiết kế đã khóa, phiên bản mã, hash dữ liệu/bảng và ngày đánh giá |
| `split_assignments.csv` | Từng phiên thuộc train hoặc test |
| `q1_train_*`, `q1_oos_*` | Tần suất mẫu hình ở hai phần |
| `q2_train_baselines.csv` | Các mức nền được fit trước test; có số cửa sổ và ngày fit |
| `q2_train_summary.csv`, `q2_train_outcomes.csv` | Thống kê train, gồm cờ loại ở ranh giới |
| `q2_oos_summary.csv`, `q2_oos_outcomes.csv` | Kết quả và từng quan sát test; q chính ở `all_q_fixed`, `trend_q_fixed` |
| `q2_train_oos_comparison.csv` | So sánh train/test trên cùng mẫu hình/kỳ hạn/phí |
| `q3_train_model.csv` | Xác suất dự báo được fit bằng train |
| `q3_oos_summary.csv`, `q3_oos_predictions.csv` | Điểm dự báo, CI/p/q chênh điểm ghép cặp và từng dự báo ngoài mẫu |
| `execution_stress.csv` | Long mô tả sau phí, thêm trượt giá 0/10/20 bps; số trường hợp không giả định khớp |
| `train_sensitivity_*.csv` | Phân tích độ nhạy chỉ trên train, không chọn ngưỡng theo test |

Mở **Thống kê cảnh báo → Đánh giá ngoài mẫu · train trước, test sau**. Dashboard chỉ đọc báo cáo đã tính, không đổi mốc chia theo bộ lọc. Panel kiểm tra hash bảng/protocol và snapshot DB. Không hiển thị kết quả chốt ở tương lai so với ngày quét lịch sử. Nếu DB có thêm ngày sau ngày chốt nhưng lịch sử cũ không đổi, panel ghi rõ kết quả chưa gồm ngày mới; chạy lại cùng protocol để nối thêm test.

### Kết quả đã chạy trên DB tải lên đến 16/11/2026

- Train 872 phiên: 16/11/2021–20/05/2025; test 374 phiên: 21/05/2025–16/11/2026. Ngưỡng nhận diện được giữ nguyên, không tìm ngưỡng thắng trên test.
- Kỳ hạn 10/20 phiên giữ ở mức mô tả do thiếu số khối test. Bản bootstrap-t cuối có 108 p hợp lệ trên họ 280; không có q BY <0,05. Không dùng số p của bản phương pháp cũ. Nói “chưa đủ bằng chứng theo chuẩn đã chọn”, không nói đã chứng minh hiệu ứng bằng 0.
- TCX và VPL chưa có lịch sử train nên không lấy dữ liệu test để bù mức nền Q2.
- Sao mai: train 5/75, dự báo Laplace 7,79%; test 2/32 = 6,25%.
- Sao hôm: train 18/166, dự báo Laplace 11,31%; test 10/90 = 11,11%.
- Brier chung: mô hình 0,088294; nền 0,088686; skill khoảng +0,44%. Chênh điểm nền−mô hình 0,000392, CI khối 95% −0,001088 đến +0,002024; p≈0,3061, q phụ=1. Khoảng chứa 0: chưa đủ bằng chứng rằng dự báo vượt nền, dù điểm trung bình nhỏ hơn trên 122 nhãn đủ dữ liệu.

Đây là **holdout hồi cứu**: toàn bộ lịch sử đã từng được khám phá trong các lần phân tích trước. Chia theo thời gian ngăn rò rỉ tính toán nhưng không xóa được việc đã xem dữ liệu. Một kiểm chứng tiến cứu thực sự cần giữ nguyên thiết kế và theo dõi các phiên phát sinh sau khi khóa nghiên cứu. Bộ kết quả mẫu nằm riêng, không được chép đè `report/oos_verified` trên DB khác; hãy chạy lại trên DB của bạn.

## 3. Q2 được định nghĩa thế nào?

- Kỳ hạn thống nhất: **1, 3, 5, 10, 20 phiên thị trường**.
- Tín hiệu ở t; vào giá mở cửa t+1; ra giá đóng cửa t+h. h=1 nghĩa là mở cửa và đóng cửa cùng phiên t+1.
- Lợi suất gộp: `close[t+h] / open[t+1] - 1`.
- Nếu tổng phí hai chiều là c (bps), lợi suất long sau phí: `close[t+h]*(1-c/20000)/(open[t+1]*(1+c/20000))-1`. Chạy cả **20 và 40 bps**; đây là giả định chi phí, không phải xác nhận mức phí thực tế của mọi công ty chứng khoán.
- MAE long: `min(0, min(low[t+1:t+h])/open[t+1]-1)`. Đây là mức bất lợi của quan sát long, không phải drawdown danh mục.
- Mức nền thường: cùng mã/kỳ hạn/phí, lấy trung bình các cửa sổ đủ lịch sử và đủ nến tương lai hợp lệ.
- Mức nền điều kiện: với mẫu hình đảo chiều, chỉ lấy cửa sổ có thống kê t xu hướng ngược chiều trước mẫu hình, đúng độ dịch theo số nến của bộ nhận diện. Marubozu và mẫu hình trung tính không có điều kiện đảo chiều này nên dùng nền thường.
- `oriented_excess` = long sau phí trừ nền, nhân +1 với hướng tăng và −1 với hướng giảm. `oriented_conditional_excess` dùng nền điều kiện. Số dương thể hiện hướng tương phản phù hợp lý thuyết. **Đây không phải lợi nhuận bán khống**, và không phải tỷ suất lợi nhuận của một chiến lược được giao dịch thật.
- `direction_hit` = giá tăng với nhãn tăng / giá giảm với nhãn giảm, tính trước phí; giá không đổi không được tính thành công. So sánh với tỷ lệ đúng hướng của các cửa sổ nền cùng mã. Nhãn trung tính không có định nghĩa đúng hướng.
- Ở chế độ khám phá, mức nền dùng toàn bộ lịch sử đóng đến ngày chốt. Ở chế độ `--oos`, mức nền chỉ dùng các cửa sổ trong train và được giữ nguyên khi đánh giá test. Kết quả ngoài mẫu được xuất riêng, không gộp lại với bảng trong mẫu.

Trạng thái quan sát: `pending` nếu chưa có đủ h phiên; `missing` nếu cửa sổ thiếu nến so với lịch thị trường ước lượng; `invalid` nếu OHLC sai hoặc có lỗi chất lượng mức error; `evaluated` nếu đủ dữ liệu hợp lệ. Không tự nhảy qua một phiên thiếu để lấy một ngày muộn hơn.

**Đơn vị lấy trung bình:** long return, MAE, tỷ lệ đúng hướng và chênh tỷ lệ được mô tả theo từng nhãn; các tương phản dùng kiểm định được lấy trung bình chéo mã trong cùng ngày, rồi lấy trọng số đều theo ngày tín hiệu. Do đó không suy ra hai cách tổng hợp phải bằng nhau.

## 4. Cách đọc các cột kiểm định

| Nhóm cột | Ý nghĩa và đơn vị |
|---|---|
| `bias` | bullish/bearish/neutral |
| `all_mean`, `trend_mean` | Chênh nền đã đổi dấu theo hướng; đơn vị tỷ lệ, 0,01 = 1% |
| `all_low/high`, `trend_low/high` | Khoảng bootstrap 95% của tương phản tương ứng |
| `all_p`, `trend_p` | p một phía, giả thuyết đối là tương phản đúng hướng > 0 |
| `all_q_fixed`, `trend_q_fixed` | BY trên toàn bộ họ nghiên cứu đã chốt |
| `direction_hit_rate` | Tỷ lệ giá đi đúng hướng, trước phí, theo nhãn |
| `baseline_direction_rate`, `trend_baseline_direction_rate` | Tỷ lệ đúng hướng của mức nền tương ứng |
| `direction_hit_gap`, `trend_direction_hit_gap` | Chênh tỷ lệ đúng hướng; đây mới là mô tả, chưa có kiểm định riêng |
| Cột tiếng Việt có `(%)` | Đã nhân 100 |
| `p bootstrap`, `q BY` | Cột tương thích cũ, hiện để trống trong luồng sản phẩm; không dùng để kết luận |

Báo cáo Q2 dùng `all_q_fixed` và `trend_q_fixed`. Họ chốt trước: 14 mẫu hình có hướng × 5 kỳ hạn × 2 mức phí × 2 mức nền = **280 giả thuyết**. Các giả thuyết không đủ quan sát vẫn thuộc họ; q của chúng để trống. Nhãn trung tính vẫn có thống kê mô tả nhưng không được ép vào kiểm định hướng lý thuyết. Không chọn riêng mức phí/nền/kỳ hạn có kết quả đẹp nhất.

Chỉ phần ngoài mẫu mới có kiểm định trong luồng sản phẩm; phương pháp hai mẫu ở mục 2b. Phần khám phá dùng bộ lọc giao diện chỉ xuất thống kê mô tả. BY không sửa được p đầu vào sai hoặc thiên lệch lựa chọn; giữ nguyên cả họ định trước khi lọc xem bảng.

### Kịch bản trượt giá và khả năng khớp

`execution_stress.csv` thêm 0/10/20 bps trượt giá hai chiều vào phí đã chọn. Mỗi chiều chịu một nửa. Nếu `net` là lợi suất đã trừ phí và s là bps trượt giá, `net_stress=(1+net)*(1-s/20000)/(1+s/20000)-1`. MAE tính lại theo giá vào tăng do trượt giá. Không giả định khớp nếu nến vào/ra chỉ có một mức giá (O=H=L=C), volume không dương, vô hạn hoặc không biết. Báo cáo số bị loại và không biến thành giao dịch lãi/lỗ giả. Đây là kiểm tra kịch bản trên OHLC ngày, chưa phải sổ lệnh, tác động thị trường, danh mục hay cơ chế thanh toán/chứng khoán về tài khoản. h=1 là phép đo biến động cùng phiên kế tiếp; không mặc nhiên là giao dịch khả thi trên cổ phiếu cơ sở Việt Nam.

## 5. Phân tích độ nhạy

Đổi từng tham số một so với mặc định: doji_k 0,05 / 0,15; trend_t 0,75 / 1,25; avg_window 20; strict_gap True. Cộng với mặc định là 7 cấu hình. Xem số nhãn và Q3 (n, tỷ lệ, CI); không chọn lại cấu hình nhận diện theo xác suất hoặc lợi suất cao nhất. Đây là khảo sát độ vững cục bộ, không phải quét mọi tổ hợp.

Doji và các biến thể có thể trùng nhau trên một nến; tổng số nhãn Q1 không phải số ngày tín hiệu độc lập. `doji_k` không trực tiếp điều khiển mọi điều kiện của Sao mai/Sao hôm, nên Q3 có thể không đổi khi chỉ đổi tham số này.

Các ngưỡng nhận diện là định nghĩa vận hành của đồ án, chưa có bằng chứng chúng tối ưu. Ngưỡng khối lượng 1,2 lần và quy tắc vượt đỉnh/đáy trong thẻ tín hiệu là quy tắc theo dõi do tác giả đặt; ngưỡng khối lượng đã cho chỉnh trên UI. Vùng tô ±0,5% chỉ hỗ trợ hiển thị. Thống kê t 10 phiên mới là tiêu chí xu hướng của bộ nhận diện; lợi suất 5 phiên là mô tả bổ trợ.

## 6. Mô phỏng hiệu chuẩn ngoài mẫu

```powershell
.\.venv\Scripts\python.exe scripts/research/calibrate.py --oos --repetitions 100 --resamples 3999 --days 3400 --symbols 12 --seed-start 40000 --out report/calibration_oos
```

Nếu thư mục đã có kết quả, dùng tên mới; không ghi đè thí nghiệm cũ. Lần chạy chốt 22/11/2026 không đọc SSI: 100 seed mới 40000–40099, 3.999 bootstrap, 12 mã và 3.400 phiên random walk log. Chia 70/30 theo thời gian cho 2.380 phiên train và 1.020 phiên test. Độ dài lớn hơn bản chẩn đoán cũ để h=10/20 có đủ ít nhất 10 khối test; không lấy thêm dữ liệu thị trường hay thay đổi ngưỡng để đạt ý nghĩa thống kê. Hai mục tiêu định trước Bao trùm tăng/giảm, kỳ hạn 1/3/5/10/20, phí 20 bps, hai mức nền, họ BY 20 giả thuyết. Chạy toàn nhận diện, fit train rồi chấm test. Nhánh positive control chỉ cấy +3% sau tín hiệu tăng ban đầu trong TEST, truyền mức giá và dựng OHLC hợp lệ, nhận diện lại; assert dấu vân tay TRAIN không đổi.

Chẩn đoán 100 seed 10000–10099 cho thấy bootstrap chưa studentize có sai lệch ở kỳ hạn dài; sau studentization, h=20 nền thường của Bao trùm giảm vẫn bác bỏ 10/80 (12,5%, Wilson 6,93–21,50%) dưới null. Vì test chỉ khoảng 9 khối dài 40 phiên, phiên bản cuối ngừng xuất p/q khi dưới 10 khối; không giấu chẩn đoán này hoặc chỉ viện BY để nói mọi p đều đúng. Chẩn đoán tiếp theo với seed 20000–20049 vẫn có Bao trùm giảm h=10 bác bỏ 5/43 dưới null (11,63%, Wilson 5,07–24,48%): chưa đủ cơ sở nói các p dài đã hiệu chuẩn tốt. Vì cửa sổ lợi suất chồng lấn, bản cuối tăng khối từ max(20,2*h) lên max(20,5*h) cho mọi mẫu hình; giữ chốt ít nhất 10 khối. Các h dài thiếu khối chỉ còn mô tả. Đây là điều chỉnh từ mô phỏng, không chọn theo lợi nhuận thị trường. Validation trước dùng seed mới 30000–30049, kết quả nằm riêng; CI Monte Carlo vẫn phải được đọc, không xem một lần chạy thuận lợi là chứng nhận phương pháp. Đây là kiểm tra trên mô phỏng cho hai mẫu hình, không chứng nhận toàn bộ 19 mẫu hình, dữ liệu thị trường hoặc tính dừng.

Đọc `calibration_summary.csv` theo từng pattern/kỳ hạn/nền và cả p lẫn q; xem `valid` vì không đủ nhãn/khối sẽ không suy luận. `family_summary.csv` đo tỷ lệ vòng có ít nhất một q<0,05, với CI Monte Carlo. BY bảo thủ nên tỷ lệ này không cần bằng 5%; mục tiêu không phải ép ra đúng một con số đẹp. Dưới null toàn phần, tỷ lệ có bất kỳ bác bỏ là family-wise error và cũng bằng FDR, nhưng không đại diện FDR khi nhiều giả thuyết có hiệu ứng thật. Nhánh +3% chỉ đo độ nhạy với hiệu ứng nhân tạo, không phải lợi nhuận chiến lược.

Validation trước khi mở rộng độ dài chuỗi (50 vòng, 1.999 bootstrap, seed 30000–30049): null có 50/50 vòng đủ ít nhất một kiểm định, 0/50 vòng có bất kỳ q<0,05, Wilson 0–7,13%; nhánh +3% có 37/50 = 74%, Wilson 60,45–84,13%. Từng p ngắn có tỷ lệ bác bỏ khoảng 4,65–11,36%, mẫu số 43/44, CI còn rộng. Đây chưa phải bằng chứng mọi p chính xác ở mức 5%. h=10/20 không xuất kiểm định vì thiếu khối; không gọi đó là “không có hiệu ứng”.

`design.json` lưu seed, thư viện, tham số, hash mã; `source_snapshot/` lưu đúng mã trước khi bắt đầu chạy. Các bản chẩn đoán cũ được giữ riêng để truy vết. Tăng vòng mô phỏng chỉ làm hẹp sai số Monte Carlo, không thay được giả định mô hình.

### Kết quả chốt để điền mục 7.6

Lần chạy 22/11/2026 đã hoàn tất: **100 vòng mỗi nhánh**, 12 mã mô phỏng, 3.400 phiên (2.380 train / 1.020 test), 3.999 lượt bootstrap, seed 40000–40099. Hai mẫu hình Bao trùm tăng/giảm × 5 kỳ hạn × 2 mức nền tạo họ BY **20 giả thuyết**, phí 20 bps. Cả 4.000 hàng kết quả đều có p/q hợp lệ; đã đối chiếu lại từng họ BY và hash của 13 tệp nguồn đóng băng.

| Nhánh | Vòng hợp lệ | Vòng có ít nhất một q BY <0,05 | Tỷ lệ | CI Wilson 95% |
|---|---:|---:|---:|---|
| Random walk không cấy hiệu ứng | 100 | 1 | 1% | 0,18–5,45% |
| Cấy +3% sau tín hiệu Bao trùm tăng ban đầu trong test | 100 | 100 | 100% | 96,30–100% |

Đây là tỷ lệ theo **vòng mô phỏng**, không phải tỷ lệ đúng của từng giao dịch. Dưới null toàn phần, có ít nhất một bác bỏ sai tương ứng FWER và FDR; khoảng Monte Carlo vẫn vượt 5% ở cận trên, nên không khẳng định đã chứng minh FDR ≤5% trong mọi điều kiện. Nhánh +3% kiểm tra khả năng phát hiện một hiệu ứng nhân tạo lớn; không phải độ chính xác dự báo thị trường 100%. Riêng Bao trùm tăng ở h=20 đạt q<0,05 ở 97/100 vòng với nền thường và 98/100 với nền xu hướng; các h=1/3/5/10 đạt 100/100 cho cả hai nền.

Tỷ lệ p thô <0,05 dưới null (mỗi ô có 100 vòng hợp lệ):

| Kỳ hạn | Bao trùm tăng, nền thường | Bao trùm tăng, nền xu hướng | Bao trùm giảm, nền thường | Bao trùm giảm, nền xu hướng |
|---:|---:|---:|---:|---:|
| 1 | 7% | 7% | 3% | 3% |
| 3 | 6% | 6% | 7% | 8% |
| 5 | 4% | 8% | 9% | 7% |
| 10 | 5% | 6% | 9% | 10% |
| 20 | 3% | 3% | 12% | 12% |

**Giới hạn cần giữ trong báo cáo:** Bao trùm giảm h=20 bác bỏ 12/100 vòng bằng p thô, CI Wilson 95% khoảng 7,00–19,81%; h=10 nền xu hướng là 10/100 (5,52–17,44%). Đây là dấu hiệu suy luận ở một số kỳ hạn dài còn thiên về bác bỏ, dù đã đủ số khối. Không viết “mọi p-value đã được hiệu chuẩn ở mức 5%”, không dùng kết quả BY bảo thủ để che hạn chế p đầu vào. Các CI từng ô không phải khoảng đồng thời cho cả 20 giả thuyết. Thiết kế và ngưỡng không được sửa theo kết quả lần chạy này.

Mô phỏng mới đủ độ dài để kiểm tra h=10/20, nhưng không làm tập test thị trường 374 phiên dài thêm. Trong nghiên cứu SSI hiện có, h=10/20 vẫn chỉ mô tả nếu chưa đủ 10 khối lịch. Mô phỏng chỉ khảo sát hai mẫu hình và các chuỗi Gaussian log random walk độc lập; không bao quát toàn bộ 19 mẫu hình, các phụ thuộc/chế độ thị trường hoặc họ 280 giả thuyết của nghiên cứu chính.

Các tệp dùng cho mục 7.6 nằm trong `report/calibration_oos/`: `replications.csv`, `calibration_summary.csv`, `family_summary.csv`, `table_7_6_family.csv`, `table_7_6_raw_p.csv`, `design.json`, `verification.json`, `run.log` và `source_snapshot/`. `design.json` và snapshot giữ nguyên cấu hình/mã đã chạy; `verification.json` ghi kiểm tra toàn vẹn. Bằng chứng 196 test ở `report/verification/`, gồm JUnit, tổng số theo module và nhật ký của bản giải nén sạch.

## 7. Kết quả minh họa trên bản DB được tải lên

Ngày cuối: **16/11/2026**; rổ cố định 30 mã. Đây không phải DB mới nhất trên máy Windows của bạn. Gói kết quả mẫu được đặt trong thư mục riêng, không dùng để ghi đè bảng final.

Audit chỉ đọc trên 30 mã đang nghiên cứu không có lỗi mức error; còn 29 cảnh báo vượt biên độ, 1 khoảng trống dài, 14 phiên thiếu theo lịch chung. DB còn lưu 407 cảnh báo đối chiếu `missing_in_ohlc`. Cần giải thích/đối chiếu nguồn, không tự xóa warning hoặc tạo giá để làm báo cáo sạch. DB gốc còn ECO ngoài rổ nghiên cứu; các bảng Q1–Q3 và dashboard chỉ dùng rổ cố định 30 mã, không tự xóa ECO khỏi bản dữ liệu gốc.

- Không có tương phản hướng lý thuyết nào đạt q<0,05 sau BY trên họ 280 giả thuyết. Điều này không chứng minh hiệu ứng bằng 0; nghiên cứu chưa có đủ bằng chứng theo tiêu chuẩn đã chọn, đặc biệt với mẫu hình hiếm.
- Q3 Sao mai: 7/107 = 6,54%, CI Wilson 3,20–12,89%; Sao hôm: 28/256 = 10,94%, CI 7,68–15,35%. Đây là xác suất **hoàn thành mẫu hình**, không phải xác suất sinh lời. Wilson giả định quan sát Bernoulli độc lập; phụ thuộc giữa mã/ngày có thể làm khoảng này lạc quan.
- Qua 7 cấu hình khảo sát: Sao mai khoảng 6,34–8,74%; Sao hôm 10,94–12,36%; số quan sát và độ rộng CI cũng thay đổi. Không suy diễn “ổn định hoàn toàn” chỉ từ khoảng dao động nhỏ.

## 8. Những việc tiếp theo để nộp bài

1. Cài bản cập nhật, chạy test; nếu có lỗi, giữ nguyên traceback và không tiếp tục lấy bảng lỗi làm kết quả.
2. Nạp dữ liệu đến phiên đã đóng, chạy kiểm tra chất lượng đang có và giải thích các warning còn lại. Không tự xóa warning chỉ để bảng trống.
3. Nếu đã có kết quả chính được khóa, giữ nguyên thư mục đó; dùng các lệnh bổ sung ở mục 10 với đầu ra riêng. Nếu chưa có bộ ngoài mẫu, tạo một nghiên cứu mới theo mục 2b và lưu protocol/manifest. Bảng toàn mẫu chỉ dùng mô tả, không thay kết quả ngoài mẫu.
4. Viết phần phương pháp trước, rồi phần kết quả Q1/Q2/Q3 từ bảng final; nêu rõ không triển khai Q4.
5. Ghi đúng giới hạn còn lại: lịch suy ra đã được đối chiếu với ngày nghỉ công bố trong mục 10, chưa phải danh mục mọi ngừng giao dịch bất thường; thành phần VN30 cố định hiện tại không phải rổ theo từng thời điểm; cần xác minh nguồn giá đã điều chỉnh cổ tức/chia tách chưa; đã có kịch bản trượt giá và chốt không giả định khớp với nến một giá, nhưng OHLC chưa xác nhận được khớp lệnh thực; đánh giá giữ lại hiện là hồi cứu, chưa phải thử nghiệm tiến cứu trên dữ liệu chưa từng xem. Phân tích độ nhạy ngưỡng không thay thế xác minh dữ liệu.
6. Chụp hình dashboard để minh họa thao tác, không lấy số liệu có bộ lọc tùy ý thay cho bảng final. Mở dashboard bằng lệnh dưới.
7. Cuối cùng quay video ingest thật rồi đọc SQLite trên dashboard; che thông tin xác thực, không đưa `.env` vào bài nộp.

```powershell
.\.venv\Scripts\python.exe -m streamlit run src/app/main.py
```

## 9. Tài liệu tham khảo đã kiểm tra thông tin thư mục

Kiểm tra ngày 20/11/2026 qua nhà xuất bản/metadata thư mục. Các tài liệu là nền tảng phương pháp hoặc nghiên cứu liên quan; không phải bằng chứng các ngưỡng tự chọn của đồ án đã được tối ưu.

1. Benjamini, Y., & Yekutieli, D. (2001). The control of the false discovery rate in multiple testing under dependency. *The Annals of Statistics, 29*(4), 1165–1188. https://doi.org/10.1214/aos/1013699998 — thông tin đối chiếu tại https://cris.tau.ac.il/en/publications/the-control-of-the-false-discovery-rate-in-multiple-testing-under/
2. Politis, D. N., & Romano, J. P. (1992). A circular block-resampling procedure for stationary data. In R. LePage & L. Billard (Eds.), *Exploring the Limits of Bootstrap* (pp. 263–270). Wiley. Đối chiếu danh mục tác giả: https://profiles.stanford.edu/joseph-romano?tab=publications . Không nhầm với bài “The Stationary Bootstrap” năm 1994 hoặc một chương khác về confidence regions năm 1992.
3. Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. *Journal of the American Statistical Association, 22*(158), 209–212. https://doi.org/10.1080/01621459.1927.10502953
4. MacKinlay, A. C. (1997). Event studies in economics and finance. *Journal of Economic Literature, 35*(1), 13–39. https://ideas.repec.org/a/aea/jeclit/v35y1997i1p13-39.html — không gán DOI chưa xác minh.
5. Marshall, B. R., Young, M. R., & Rose, L. C. (2006). Candlestick technical trading strategies: Can they create value for investors? *Journal of Banking & Finance, 30*(8), 2303–2323. https://doi.org/10.1016/j.jbankfin.2005.08.001

## 10. Bổ sung nghiên cứu ngày 24/11/2026

Bốn phân tích bổ sung nằm trong `scripts/research/`, đầu ra `report/supplement_20261124/`. Chỉ bổ sung cờ `--exclude` vào trình chạy `scripts/run_study.py`; không sửa các module số học đã khóa, không sửa SQLite và không ghi đè kết quả chính. Đây là phân tích độ vững **hồi cứu**, không biến holdout đã xem thành kiểm chứng tiến cứu.

Bộ kiểm thử hiện tại đạt **229 passed**, gồm 196 test trước đó và 33 test bổ sung về MDE/BY, nhóm nền Q3, bootstrap, ranh giới train/test, lịch nghỉ và chống ghi đè. Nhật ký/JUnit và kiểm tra hash nằm trong `report/supplement_20261124/verification/`. Cảnh báo còn lại khi chạy tại môi trường kiểm tra là deprecation của plugin pytest bên ngoài dự án.

### 10.1. Sức mạnh kiểm định được lượng hóa bằng MDE

`power_diagnostics.py` đọc CI/SE đã lưu, không tính lại lợi suất hoặc bootstrap chính. MDE là hiệu ứng giả định cần có để đạt power 80% theo xấp xỉ chuẩn. Với CI 95%, script suy SE xấp xỉ bằng `(high-low)/(2*z_0.975)`; MDE một phía là `(z_(1-alpha)+z_0.8)*SE`. Đây **không phải observed power tính từ hiệu ứng quan sát**. CI nguồn là bootstrap-t có thể bất đối xứng, nên script xuất cả MDE theo độ rộng CI và MDE theo SE đã lưu, cùng chỉ báo bất đối xứng.

Trung vị qua các tương phản có CI hợp lệ, đơn vị **điểm phần trăm**:

| Kỳ hạn | MDE chưa hiệu chỉnh, CI-width | MDE BY ở hạng 1, CI-width | MDE chưa hiệu chỉnh, SE lưu | MDE BY hạng 1, SE lưu |
|---|---:|---:|---:|---:|
| 1 phiên | 0,658 | 1,287 | 0,582 | 1,139 |
| 3 phiên | 1,529 | 2,992 | 1,321 | 2,585 |
| 5 phiên | 2,156 | 4,218 | 1,833 | 3,585 |

H=10/20 không có CI hợp lệ theo điều kiện số khối của thiết kế chính, vì vậy không điền MDE. Không diễn giải các con số trên thành bảo đảm power thực tế. `hypothetical_power.csv` chứa xấp xỉ cho hiệu ứng định sẵn 0,25/0,5/1/2 điểm %, không lấy hiệu ứng quan sát để chọn cỡ giả định.

Với họ 280, ngưỡng BY hạng 1 khoảng `2,86e-5`, gần sàn p `2,5e-5` của 39.999 lượt. Đây là ngưỡng cho phát hiện đơn lẻ ở hạng 1; **không phải điều kiện bắt buộc cho mọi hạng** của thủ tục step-up. `BY_rank_thresholds.csv` lưu đủ 280 hạng. Chẩn đoán giảm họ còn 27 p hữu hạn ở từng nền/phí: nền mọi ngày có q nhỏ nhất 1; nền xu hướng khoảng **0,858285**, không phải mọi q đều bằng 1. Tất cả vẫn trên 0,05; chẩn đoán này không thay họ chính 280. p thô nhỏ nhất toàn bộ là **0,019525**.

### 10.2. Q3: nhóm nền cùng nến thứ nhất và bootstrap theo ngày

`q3_incremental.py` giữ điều kiện nến thứ nhất thân dài và ngược xu hướng trước đó. Tại nến thứ hai, nhóm cảnh báo thỏa thân ngắn + body gap; nhóm nền không thỏa ít nhất một điều kiện này. Hai nhóm dùng **cùng outcome**: nến thứ ba có màu đảo chiều và đóng vượt trung điểm thân nến thứ nhất. Không buộc nhóm nền phải thành mẫu hình Sao mai/Sao hôm hoàn chỉnh, vì như vậy outcome sẽ thất bại theo định nghĩa nhóm và tạo so sánh vòng tròn.

Script xác nhận từng outcome nhóm cảnh báo trùng bản chính ở cả train/test trước khi xuất so sánh. Ngày setup thuộc train nhưng nến xác nhận vượt 20/05/2025 bị loại khỏi train. Nến thiếu/lỗi/chưa có tương lai giữ trạng thái riêng và không vào mẫu số.

Trên test 21/05/2025–16/11/2026:

| Loại | Có cảnh báo | Nền chỉ có điều kiện nến 1 | Chênh tỷ lệ, điểm % | CI khối 95%, điểm % |
|---|---:|---:|---:|---:|
| Sao mai | 2/32 = 6,25% | 94/351 = 26,78% | −20,53 | [−33,33; −2,23] |
| Sao hôm | 10/90 = 11,11% | 82/314 = 26,11% | −15,00 | [−27,74; −4,66] |

Tỷ lệ bảng này gộp theo nhãn, hai nhóm được resample **cùng khối ngày** dài 20 phiên, gồm ngày không có nhãn, giữ cùng lịch cho tất cả mã; B=39.999, seed=2026. Xuất riêng khoảng Bonferroni xấp xỉ cho họ 6 tương phản định trước (2 chênh tỷ lệ và 4 chênh Brier/log loss). Với khoảng họ này, chênh Sao mai [−36,43; +6,91] điểm %, Sao hôm [−31,55; −1,30] điểm %. Không suy luận nhân quả: nhóm cảnh báo và nhóm nền có thể khác thành phần mã, thời gian và trạng thái thị trường.

Kiểm tra thêm chuẩn hóa nhóm nền về tỷ trọng mã trong nhóm cảnh báo nằm ở `q3_rate_symbol_standardized.csv`. Sao mai không mất nhãn cảnh báo, chênh −22,29 điểm %; Sao hôm loại 2 nhãn không có nhóm nền cùng mã, chênh −13,03 điểm %. Khoảng họ của cả hai chứa 0. Số lượt bootstrap hữu hạn được ghi riêng vì một số lượt không có nhóm nền cho mã hiếm. Đừng chọn cách gộp sau khi xem cách nào cho CI đẹp.

Để đánh giá dự báo, script fit hai xác suất Laplace theo **train**: xác suất của nhóm cảnh báo và xác suất nhóm chỉ có nến 1. Chấm cả hai trên đúng cùng nhãn cảnh báo test; không fit nền bằng tỷ lệ test. Chênh điểm là `loss_control - loss_alarm`, dương nghĩa mô hình có cảnh báo giảm sai số:

| Loại | Brier giảm TB | CI khối 95% | Log loss giảm TB | CI khối 95% |
|---|---:|---:|---:|---:|
| Sao mai | 0,030979 | [−0,024751; +0,051137] | 0,110127 | [−0,116882; +0,192236] |
| Sao hôm | 0,026570 | [+0,001332; +0,055035] | 0,079726 | [−0,005354; +0,175686] |

Cả bốn khoảng họ 6 chứa 0; chưa có bằng chứng vững rằng dự báo giảm sai số ở mức họ đã chọn. Kết quả phản ánh cảnh báo có thể mang thông tin về **tỷ lệ hoàn thành thấp hơn**, không phải lời hứa xác suất cao hơn. Đây là dự báo hoàn thành nến, không phải lợi nhuận đầu tư. Khoảng bổ sung là percentile circular-block có độ phủ xấp xỉ, suy luận điều kiện trên dự báo train cố định; **không xuất p/q chưa hiệu chuẩn từ CI percentile**. Kết quả chính với nền pooled cũ vẫn giữ nguyên, không thay bằng bảng mới này.

### 10.3. Độ vững khi loại BSR, MCH, VPL

Đã chạy cả mô tả toàn mẫu và ngoài mẫu, loại toàn bộ lịch sử của 3 mã được chỉ định. Bộ ngoài mẫu có protocol riêng ở `exclude_oos/`; cùng mốc train 20/05/2025, ngày chốt 16/11/2026, cùng 1.246 phiên, ngưỡng, kỳ hạn, phí và họ 280. Không giảm họ theo số mã: họ kiểm định đếm mẫu hình × kỳ hạn × phí × nền.

| Chỉ tiêu ngoài mẫu | Chính: 30 mã | Loại 3 mã: 27 mã |
|---|---:|---:|
| Nhãn lịch sử trong test, gồm setup | 4.706 | 4.172 |
| p Q2 hợp lệ | 108 | 108 |
| p thô nhỏ nhất | 0,019525 | 0,020150 |
| q BY nhỏ nhất | 1 | 1 |
| Số q <0,05 | 0 | 0 |
| Q3 Sao mai | 2/32 | 0/26 |
| Q3 Sao hôm | 10/90 | 10/78 |

Q3 Sao mai giảm còn 26 nhãn/19 ngày cảnh báo, không đạt điều kiện suy luận của thiết kế; CI/p bootstrap để trống thay vì biến thiếu lực thành kết luận không có hiệu ứng. Ngoài mẫu 27 mã vẫn không có kết quả Q2 vượt BY. Bảng chi tiết trước/sau ở `exclusion_comparison/`. Mô tả toàn mẫu 27 mã có 13.687 nhãn mẫu hình hoàn chỉnh, 323 setup; Q3 Sao mai 4/96 và Sao hôm 27/227.

Bản mã nhận được đầu phiên làm việc đã có sửa kiểm tra OHLC hữu hạn trong `candles.py` ngày 22/11, nên hash file này khác protocol chính cũ. Lần bổ sung này **không sửa file đó**, không viết lại hash cũ. Manifest bổ sung công khai sai khác có sẵn; nhóm alarm Q3 tái tạo đúng outcomes nguồn. Bộ loại mã khóa protocol mới riêng, ghi đúng hash hiện tại. Tám module số học còn lại trùng protocol nguồn. Trường hợp muốn tái chạy chính đúng hash cũ phải dùng snapshot mã/thư viện của lần chính; không sửa protocol để ép chạy.

Loại 3 mã làm giảm lo ngại kết quả bị chi phối bởi các lịch sử này, nhưng chưa giải quyết rổ VN30 theo từng thời điểm, survivor bias hoặc toàn bộ chuyển sàn trong thị trường.

### 10.4. Đối chiếu ngày nghỉ công bố

`calendar_audit.py` đối chiếu lịch đã khóa với CSV tài liệu nghỉ 2021–2026. Xem [nguồn VSD/VSDC và HNX/HOSE](../scripts/research/reference/README.md), gồm các lần điều chỉnh nghỉ 29/04/2024, 02/05/2025, 02/01/2026. Đây là đối chiếu lịch nghỉ thanh toán có kiểm tra chéo lịch nghỉ giao dịch, không tự coi lịch làm bù hành chính là phiên sàn.

Trong phạm vi 16/11/2021–16/11/2026: **1.246/1.246 phiên khớp**, không thiếu phiên dự kiến và không có phiên suy ra rơi vào ngày đóng cửa; **0 dòng OHLC** của 30 mã rơi vào ngày đóng cửa trong phạm vi. Theo năm có 34/249/249/250/249/215 phiên. Một mã thiếu giá riêng lẻ vẫn là vấn đề chất lượng dữ liệu, không tự biến thành ngày nghỉ toàn thị trường. Phần kiểm tra lịch **không xóa** 14 cảnh báo thiếu phiên của từng mã hoặc các cảnh báo khác trong DB.

Đây chưa phải bộ lịch mọi sự cố/ngừng giao dịch bất thường. Tham chiếu ngoài 2021–2026 chưa được xác minh nên script dừng khi yêu cầu vượt phạm vi. Audit không thay lịch cũ, không chạy lại kết quả chính.

### 10.5. Chạy lại trên Windows và sử dụng gói bàn giao

Giải nén mã vào thư mục dự án hiện có. Gói bổ sung không chứa `.env`, khóa API, `radar.db` hay bản ghi đè `report/oos_verified`. Bộ bảng mẫu được tính từ snapshot đến **16/11/2026**, không được giới thiệu là đã tính trên DB mới nhất của bạn.

Gói `vn30-research-supplement-2026-11-24.zip` chỉ chứa các file bổ sung/chỉnh sửa cùng bảng tổng hợp, không chép các module `src/` đã khóa lên máy bạn. Hai gói `vn30-exclude-in-sample-2026-11-24.zip` và `vn30-exclude-oos-2026-11-24.zip` chứa đầy đủ bảng chi tiết của hai lần loại mã; tách riêng để mỗi tệp tải trực tiếp dưới 10 MiB. Giải nén cả ba vào cùng thư mục gốc dự án để đủ các bảng mà manifest dẫn tới. Chúng chỉ ghi kết quả vào `report/supplement_20261124/`, không vào thư mục kết quả chính. Bảng tổng hợp trong gói đầu đủ để đọc kết quả ngay.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/research/power_diagnostics.py --study report/oos_verified --out report/supplement_local/power
.\.venv\Scripts\python.exe scripts/research/q3_incremental.py --study report/oos_verified --db storage/radar.db --out report/supplement_local/q3 --resamples 39999
.\.venv\Scripts\python.exe scripts/research/calendar_audit.py --study report/oos_verified --db storage/radar.db --out report/supplement_local/calendar
```

Chỉ power cần CSV nguồn. Q3/calendar kiểm tra fingerprint dữ liệu lịch sử khớp parent manifest: DB có thêm ngày sau ngày chốt vẫn được, lịch sử cũ thay đổi thì dừng; không âm thầm ghép các vintage khác nhau. Các script mới từ chối thư mục đầu ra đã có dữ liệu: muốn lặp lại, chọn thư mục khác. Không xóa bộ chốt để làm lệnh chạy được.

Độ vững loại mã (dùng đúng ngày chốt của báo cáo chính; ví dụ dưới tương ứng bộ mẫu):

```powershell
.\.venv\Scripts\python.exe scripts/run_study.py --db storage/radar.db --asof 2026-11-16 --exclude BSR,MCH,VPL --sensitivity --out report/supplement_local/exclude_in_sample
.\.venv\Scripts\python.exe scripts/run_study.py --db storage/radar.db --asof 2026-11-16 --oos --train-end 2025-05-20 --exclude BSR,MCH,VPL --resamples 39999 --out report/supplement_local/exclude_oos
.\.venv\Scripts\python.exe scripts/research/compare_robustness.py --study report/oos_verified --excluded-study report/supplement_local/exclude_oos --out report/supplement_local/exclusion_comparison
```

`--exclude` yêu cầu `--out` riêng, chuẩn hóa mã hoa, từ chối mã ngoài rổ và từ chối ghi đè nghiên cứu có rổ khác. Lệnh ngoài mẫu có thể mất vài phút; không rút số lượt chỉ để lấy kết quả chính thức nhanh hơn.

Trong báo cáo, giữ nguyên kết quả chính của Mục 7; thêm tiểu mục/phụ lục độ vững từ các bảng mới và ghi rõ phân tích bổ sung hồi cứu. Các giới hạn đã lượng hóa/đối chiếu không cần tiếp tục ghi là “chưa làm”, nhưng các giới hạn về nghiên cứu hồi cứu, thành phần rổ lịch sử, vintage giá, mẫu hình hiếm và giả định bootstrap vẫn phải trình bày. Q4 chưa triển khai trong gói này; đây là hạng mục tùy chọn có điều kiện thời gian, không phải cách sửa kết quả chính.
