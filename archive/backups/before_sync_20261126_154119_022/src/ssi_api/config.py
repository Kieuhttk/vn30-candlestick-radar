"""Đọc thông tin xác thực từ biến môi trường hoặc tệp .env (không bao giờ ghi cứng vào mã)."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv chưa cài: vẫn đọc được biến môi trường hệ thống
    pass


def get_credentials():
    """Trả về (api_key, api_secret); báo lỗi rõ ràng nếu thiếu biến."""
    missing = [k for k in ("SSI_API_KEY", "SSI_API_SECRET") if not os.environ.get(k)]
    if missing:
        raise RuntimeError(
            f"Thiếu biến môi trường: {', '.join(missing)}. "
            "Sao chép .env.example thành .env và điền giá trị."
        )
    return os.environ["SSI_API_KEY"], os.environ["SSI_API_SECRET"]
