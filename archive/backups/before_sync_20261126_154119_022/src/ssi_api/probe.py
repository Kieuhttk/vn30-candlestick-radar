"""Thăm dò API (chỉ đọc). Chạy:  python -m ssi_api.probe FPT"""
import logging
import sys
from datetime import date, timedelta

from ssi_api.client import DATE_FORMATS, SSIClient, SSIError, to_date


def main(sym="FPT"):
    logging.basicConfig(level=logging.INFO, format="  [%(levelname)s] %(message)s")
    today = date.today()
    d0 = today - timedelta(days=45)
    api = SSIClient()
    print("Đăng nhập OK")

    o = api.ohlc(sym, d0, today)
    print(f"\n[ohlc] {len(o)} dòng")
    print(o.head(3).to_string())

    s = api.securities_summary(sym, d0, today)
    print(f"\n[securitiesSummary] {len(s)} dòng; cột: {list(s.columns)}")
    print(s.head(3).to_string())

    # 1) Đối chiếu chéo hai endpoint
    o["d"], s["d"] = to_date(o.tradingDate), to_date(s.tradingDate)
    m = o.merge(s, on="d", suffixes=("_o", "_s"))
    print(f"\n[đối chiếu] khớp ngày: {len(m)}/{len(o)}")
    print(m[["d", "close_o", "close_s", "volume", "totalMatch"]].tail(3).to_string())
    print("lệch close:", int((m.close_o - m.close_s).abs().gt(1e-6).sum()),
          "| lệch volume vs totalMatch:", int((m.volume - m.totalMatch).abs().gt(0).sum()))

    # 2) Giả thuyết: giá tham chiếu = close - priceChange
    s = s.sort_values("d").reset_index(drop=True)
    gap = ((s.close - s.priceChange) - s.close.shift(1)).abs()
    print("ngày có tham chiếu ≠ đóng cửa hôm trước:", int((gap > 1e-6).sum()))

    # 3) Sự kiện quyền trong 5 ngày gần nhất
    ca = api.corporate_actions(today - timedelta(days=4), today)
    print(f"\n[corporateActions 5 ngày gần nhất] {len(ca)} dòng")
    print(ca.head(5).to_string())

    # 4) Giới hạn pageSize và rate limit
    f = DATE_FORMATS[api.fmt["/data/ohlc"]][1]
    try:
        r = api.get("/data/ohlc", {"symbol": sym, "from": f(date(2023, 1, 1), False),
                                   "to": f(today, True), "pageSize": 1000, "pageIndex": 1})
        print("\n[pageSize] yêu cầu 1000, nhận", len(r.json().get("data") or []))
        print("[rate limit]", {k: v for k, v in r.headers.items()
                               if k.upper().startswith("X-RATELIMIT")})
    except SSIError as e:
        print("\n[pageSize] 1000 bị từ chối:", e.body)


if __name__ == "__main__":
    # CLI tiếng Việt dùng UTF-8 cả khi stdout/stderr bị chuyển vào pipe trên Windows.
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    main(sys.argv[1] if len(sys.argv) > 1 else "FPT")
