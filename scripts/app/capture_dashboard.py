"""Chụp 5 mục của dashboard menu dọc, lưu PNG vào report/screenshots."""

import os as _radar_os, sys as _radar_sys
from pathlib import Path as _RadarPath
_radar_root = _RadarPath(__file__).resolve().parents[2]
_radar_sys.path.insert(0, str(_radar_root / "src"))
_radar_os.chdir(_radar_root)
import argparse
import math
from pathlib import Path

from playwright.sync_api import sync_playwright

PAGES = [
    ("nav_radar", "Diễn biến cổ phiếu", "01_radar.png"),
    ("nav_statistics", "Xác suất hoàn thành trong lịch sử", "02_thong_ke_canh_bao.png"),
    ("nav_chart", "Đọc diễn biến giá", "03_bieu_do.png"),
    ("nav_quality", "Chất lượng dữ liệu", "04_chat_luong.png"),
    ("nav_method", "Phương pháp và giới hạn", "05_phuong_phap.png"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8501")
    parser.add_argument("--out", default="report/screenshots")
    parser.add_argument("--browser", default=None, help="Đường dẫn Chromium có sẵn nếu muốn dùng thay bản Playwright")
    args = parser.parse_args()
    folder = Path(args.out)
    if not folder.is_absolute():
        folder = Path(__file__).resolve().parents[2] / folder
    folder.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=args.browser)
        try:
            page = browser.new_page(viewport={"width":1700,"height":1250}, device_scale_factor=1)
            page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
            page.locator(".st-key-nav_radar button").wait_for(timeout=60000)
            for key, heading, filename in PAGES:
                page.locator(f".st-key-{key} button").click()
                page.get_by_role("heading",name=heading,exact=True).wait_for(timeout=60000)
                page.locator('[data-testid="stStatusWidget"]').wait_for(state="hidden", timeout=60000)
                if page.locator('[data-testid="stException"]').count():
                    raise RuntimeError("Dashboard đang báo lỗi; sửa lỗi hiển thị trước khi chụp.")
                page.wait_for_function("""() => [...document.querySelectorAll('.js-plotly-plot')]
                    .filter(p => p.getBoundingClientRect().height > 0).every(p => p._fullLayout && p._fullData)""")
                page.evaluate("document.fonts.ready")
                page.add_style_tag(content="""
                    html,body,#root,[data-testid="stApp"],[data-testid="stAppViewContainer"],[data-testid="stMain"] {
                        height:auto!important;min-height:100vh!important;overflow:visible!important;
                    }
                    [data-testid="stSidebar"] {position:sticky!important;top:0!important;height:100vh!important;flex-shrink:0!important;}
                """)
                page.evaluate("window.scrollTo(0,0)")
                if key == "nav_radar":
                    next_row = page.locator(".st-key-activity_card")
                    if next_row.count():
                        height = max(900,math.ceil(next_row.bounding_box()["y"]-12))
                        page.set_viewport_size({"width":1700,"height":height})
                        target = folder / "00_tong_quan.png"
                        page.screenshot(path=str(target))
                        print("Đã lưu:",target)
                        page.set_viewport_size({"width":1700,"height":1250})
                target = folder / filename
                page.screenshot(path=str(target),full_page=True)
                print("Đã lưu:",target)
        finally:
            browser.close()


if __name__ == "__main__":
    # CLI tiếng Việt dùng UTF-8 cả khi stdout/stderr bị chuyển vào pipe trên Windows.
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    main()
