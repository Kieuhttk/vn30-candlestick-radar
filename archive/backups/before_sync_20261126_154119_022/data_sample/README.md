# Dữ liệu demo offline

Tạo `radar_demo.db` từ **chính DB đã chốt hồ sơ 24/11/2026, phiên cuối 23/11/2026**, theo mục 7 của `docs/RESEARCH_GUIDE.md`. Bản vá không tự sinh dữ liệu thị trường hoặc giả rằng đã có DB ngày đó.

DB chỉ dùng schema thị trường của dự án; xóa ingest_log trên bản demo, giữ giá và quality để đối chiếu fingerprint. Commit cả DB và metadata.json sau khi kiểm tra tab Kết quả nghiên cứu chấp nhận snapshot.

Mở không cần khóa API:

```powershell
$env:RADAR_DB_PATH = 'data_sample/radar_demo.db'
.\.venv\Scripts\python.exe -m streamlit run src/app/main.py
```

Nếu chưa có `radar_demo.db` trong bản clone thì chỉ có tài liệu hướng dẫn, chưa phải bộ demo hoàn chỉnh. Không dùng dữ liệu giả gắn nhãn là dữ liệu SSI.
