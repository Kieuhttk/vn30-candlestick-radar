"""Client đọc dữ liệu thị trường SSI FastConnect (chỉ đọc, không gọi nhóm Trading).

Các điểm đã kiểm chứng khi chạy thật (xem docs/api_notes.md):
- /data/ohlc đòi ngày dạng "YYYY/MM/DD HH:mm:ss"; /data/securitiesSummary và
  /data/corporateActions nhận "YYYY/MM/DD". Client tự dò và nhớ định dạng theo từng endpoint.
- Mọi trường số trả về dạng chuỗi -> ép sang số.
- Phản hồi 204 nghĩa là không có dữ liệu; 429 là vượt giới hạn tần suất.
"""
import logging
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from ssi_api.config import get_credentials

log = logging.getLogger(__name__)

BASE = "https://api.ssi.com.vn/api/v3"
VN = timezone(timedelta(hours=7))


def _epoch(d, end):
    t = datetime(d.year, d.month, d.day, tzinfo=VN)
    return str(int((t + (timedelta(seconds=86399) if end else timedelta())).timestamp()))


# Thứ tự thử khi server báo lỗi định dạng ngày (mã 400213).
DATE_FORMATS = [
    ("YYYY/MM/DD", lambda d, end: d.strftime("%Y/%m/%d")),
    ("YYYY/MM/DD HH:mm:ss",
     lambda d, end: d.strftime("%Y/%m/%d") + (" 23:59:59" if end else " 00:00:00")),
    ("YYYY-MM-DD", lambda d, end: d.strftime("%Y-%m-%d")),
    ("DD/MM/YYYY", lambda d, end: d.strftime("%d/%m/%Y")),
    ("YYYY-MM-DDTHH:mm:ss",
     lambda d, end: d.strftime("%Y-%m-%d") + ("T23:59:59" if end else "T00:00:00")),
    ("epoch giây (UTC+7)", _epoch),
]


def to_date(s):
    """Chuẩn hóa cột ngày trả về (thử lần lượt vài định dạng)."""
    s = s.astype(str).str[:10]
    out = pd.to_datetime(s, format="%Y/%m/%d", errors="coerce")
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        out = out.fillna(pd.to_datetime(s, format=fmt, errors="coerce"))
    return out


def to_num(df, skip=("symbol", "tradingDate")):
    """API trả mọi trường dạng chuỗi -> ép sang số (lỗi thành NaN)."""
    for c in df.columns:
        if c not in skip:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def wait_seconds(headers, default=1.0):
    """X-RATELIMIT-RESET có thể là mốc epoch hoặc số giây: xử lý cả hai.
    Không có header (phản hồi thực tế của SSI không thấy header này) thì dùng `default`."""
    try:
        v = float(headers.get("X-RATELIMIT-RESET"))
    except (TypeError, ValueError):
        return default
    wait = v - time.time() if v > 1e9 else v
    return min(max(wait, 1.0), 60.0)


class SSIError(Exception):
    def __init__(self, status, body, url):
        super().__init__(f"HTTP {status}: {body} ({url})")
        self.status, self.body = status, body


class SSIClient:
    def __init__(self, api_key=None, api_secret=None):
        if api_key is None or api_secret is None:
            api_key, api_secret = get_credentials()
        self._key, self._secret = api_key, api_secret
        self.s = requests.Session()
        self.s.headers["Content-Type"] = "application/json"
        self.exp = 0
        self.fmt = {}  # endpoint -> chỉ số định dạng ngày đã được chấp nhận
        self.login()

    def login(self):
        """Lấy access token chỉ để đọc dữ liệu (không truyền otp)."""
        r = self.s.post(
            f"{BASE}/auth/token",
            json={"apiKey": self._key, "apiSecret": self._secret},
            timeout=30,
        )
        r.raise_for_status()
        j = r.json()
        self.s.headers["Authorization"] = f"Bearer {j['accessToken']}"
        self.exp = j["expiresAt"]

    def get(self, path, params):
        if time.time() > self.exp - 60:
            self.login()
        for attempt in range(5):
            r = self.s.get(f"{BASE}{path}", params=params, timeout=30)
            if r.status_code == 429:
                # Chưa biết chu kỳ giới hạn là giây hay phút: lùi dần 2, 4, 8, 16, 32 giây (tổng ~1 phút)
                wait = wait_seconds(r.headers, default=2.0 ** (attempt + 1))
                log.warning("429 tại %s, chờ %.0f giây", path, wait)
                time.sleep(wait)
                continue
            if r.status_code >= 400:  # 204 (không có dữ liệu) vẫn hợp lệ
                raise SSIError(r.status_code, r.text[:500], r.url)
            if r.headers.get("X-RATELIMIT-REMAINING") == "0":
                time.sleep(wait_seconds(r.headers))
            time.sleep(0.2)
            return r
        raise RuntimeError(f"Bị giới hạn tần suất liên tục: {path}")

    def paged(self, path, params, page_size=100, max_pages=200):
        """Thử pageSize lớn trước; nếu bị 400 (không phải lỗi ngày) thì thử cỡ nhỏ hơn."""
        sizes = [page_size] + [x for x in (500, 100, 50, 20, 10) if x < page_size]
        for size in sizes:
            try:
                df = self._paged(path, params, size, max_pages)
                log.debug("%s: pageSize=%s chạy được", path, size)
                return df
            except SSIError as e:
                retry = e.status == 400 and "400213" not in e.body and size != sizes[-1]
                if not retry:
                    raise
                log.warning("%s: pageSize=%s bị từ chối (%s), thử cỡ nhỏ hơn", path, size, e.body)

    def _paged(self, path, params, page_size, max_pages):
        """Chỉ trả kết quả khi đã gặp trang rỗng; lỗi nếu chưa chứng minh được đã lấy hết."""
        rows, first_prev = [], None
        for page in range(1, max_pages + 1):
            r = self.get(path, {**params, "pageIndex": page, "pageSize": page_size})
            data = [] if r.status_code == 204 else (r.json().get("data") or [])
            if not data:
                break
            if data[0] == first_prev:
                raise RuntimeError(f"{path}: trang {page} lặp lại; chưa xác nhận đã lấy đủ dữ liệu")
            first_prev = data[0]
            rows += data
        else:
            raise RuntimeError(f"{path}: chạm max_pages={max_pages}; chưa lấy đủ dữ liệu")
        return pd.DataFrame(rows)

    def _dated(self, path, d_from, d_to, extra, page_size=100):
        """Gọi endpoint có from/to. Mỗi endpoint có thể đòi định dạng ngày khác nhau:
        thử lần lượt các định dạng (ưu tiên định dạng đã chạy được) khi gặp 400213."""
        order = list(range(len(DATE_FORMATS)))
        if path in self.fmt:
            order.remove(self.fmt[path])
            order.insert(0, self.fmt[path])
        last = None
        for i in order:
            name, f = DATE_FORMATS[i]
            params = {**extra, "from": f(d_from, False), "to": f(d_to, True)}
            try:
                df = self.paged(path, params, page_size)
            except SSIError as e:
                if e.status == 400 and "400213" in e.body:
                    log.info("%s: định dạng ngày '%s' bị từ chối", path, name)
                    last = e
                    continue
                raise
            if self.fmt.get(path) != i:
                log.info("%s: định dạng ngày được chấp nhận = %s", path, name)
            self.fmt[path] = i
            return df
        raise last

    def ohlc(self, symbol, d_from, d_to, tf="1d", page_size=100):
        """Nến OHLCV. Kết quả trả về mới nhất trước: người dùng hàm cần tự sắp xếp.
        page_size lớn (ví dụ 1000) giúp lấy cả lịch sử dài trong một lần gọi; bị từ chối thì tự giảm."""
        return to_num(self._dated("/data/ohlc", d_from, d_to,
                                  {"symbol": symbol, "timeFrame": tf}, page_size))

    def securities_summary(self, symbol, d_from, d_to, page_size=100):
        """Tổng hợp giao dịch theo ngày (có dòng tiền nước ngoài, priceChange...)."""
        return to_num(self._dated("/data/securitiesSummary", d_from, d_to,
                                  {"symbol": symbol}, page_size))

    def corporate_actions(self, d_from, d_to, symbol=None, page_size=100):
        """Sự kiện quyền. Theo docs, khoảng from-to không được quá 5 ngày."""
        return self._dated("/data/corporateActions", d_from, d_to,
                           {"symbol": symbol} if symbol else {}, page_size)
