"""Chụp dashboard đang chạy và lưu PNG vào report/screenshots."""
import argparse
import math
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8501")
    parser.add_argument("--out", default="report/screenshots")
    parser.add_argument("--browser", default=None, help="Đường dẫn Chromium có sẵn, nếu muốn dùng thay bản Playwright")
    args = parser.parse_args()
    folder = Path(args.out)
    if not folder.is_absolute():
        folder = Path(__file__).resolve().parent / folder
    folder.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=args.browser)
        try:
            page = browser.new_page(viewport={"width": 1700, "height": 1250}, device_scale_factor=1)
            page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
            page.get_by_role("tab", name="Thống kê cảnh báo", exact=True).wait_for(timeout=60000)
            page.locator('[data-testid="stStatusWidget"]').wait_for(state="hidden", timeout=60000)
            if page.locator('[data-testid="stException"]').count():
                raise RuntimeError("Dashboard đang báo lỗi; sửa lỗi hiển thị trước khi chụp.")
            page.add_style_tag(content="""
                html, body, #root, [data-testid="stApp"],
                [data-testid="stAppViewContainer"], [data-testid="stMain"] {
                    height:auto!important; min-height:100vh!important; overflow:visible!important;
                }
                [data-testid="stSidebar"] {position:sticky!important; top:0!important; height:100vh!important; flex-shrink:0!important;}
            """)
            for tab_name, filename in [("Radar", "01_radar.png"), ("Thống kê cảnh báo", "02_thong_ke_canh_bao.png"), ("Biểu đồ", "03_bieu_do.png")]:
                page.get_by_role("tab", name=tab_name, exact=True).click()
                panel = page.get_by_role("tabpanel", name=tab_name, exact=True)
                panel.locator(".js-plotly-plot").first.wait_for(state="visible", timeout=60000)
                page.wait_for_function("""() => [...document.querySelectorAll('[role="tabpanel"] .js-plotly-plot')]
                    .filter(p => p.getBoundingClientRect().height > 0)
                    .every(p => p._fullLayout && p._fullData)""")
                page.evaluate("document.fonts.ready")
                if tab_name == "Radar":
                    next_row = panel.locator(".st-key-activity_card")
                    if next_row.count():
                        height = max(900, math.ceil(next_row.bounding_box()["y"] - 12))
                        page.set_viewport_size({"width": 1700, "height": height})
                        overview_path = folder / "00_tong_quan.png"
                        page.screenshot(path=str(overview_path))
                        print("Đã lưu:", overview_path)
                        page.set_viewport_size({"width": 1700, "height": 1250})
                page.screenshot(path=str(folder / filename), full_page=True)
                print("Đã lưu:", folder / filename)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
