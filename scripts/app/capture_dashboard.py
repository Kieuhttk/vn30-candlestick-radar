"""Chụp 5 mục của dashboard menu dọc, lưu PNG vào report/screenshots."""

import os as _radar_os, sys as _radar_sys
from pathlib import Path as _RadarPath
_radar_root = _RadarPath(__file__).resolve().parents[2]
_radar_sys.path.insert(0, str(_radar_root / "src"))
_radar_os.chdir(_radar_root)
import argparse
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path

from playwright.sync_api import sync_playwright

PAGES = [
    ("nav_radar", "Hiểu tín hiệu giá", "01_radar.png"),
    ("nav_statistics", "Đọc kết quả nghiên cứu", "02_ket_qua_nghien_cuu.png"),
    ("nav_chart", "Đọc diễn biến giá", "03_bieu_do.png"),
    ("nav_quality", "Kiểm tra dữ liệu", "04_chat_luong.png"),
    ("nav_method", "Hiểu phương pháp", "05_phuong_phap.png"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8501")
    parser.add_argument("--out", default="report/screenshots")
    parser.add_argument("--browser", default=None, help="Đường dẫn Chromium có sẵn nếu muốn dùng thay bản Playwright")
    parser.add_argument("--expect-asof", help="Phiên phân tích phải hiển thị, YYYY-MM-DD; dừng nếu sai ngày")
    parser.add_argument("--cutoff-date", help="Ngày chốt hồ sơ, có thể là ngày nghỉ; không thay ngày phiên giá")
    args = parser.parse_args()
    folder = Path(args.out)
    if not folder.is_absolute():
        folder = Path(__file__).resolve().parents[2] / folder
    if folder.exists() and any(folder.iterdir()):
        parser.error('Thư mục ảnh đã có dữ liệu; chọn --out mới để không trộn hai lần chụp.')
    folder.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=args.browser)
        try:
            page = browser.new_page(viewport={"width":1700,"height":1250}, device_scale_factor=1)
            page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
            page.locator(".st-key-nav_radar button").wait_for(timeout=60000)
            recorded = []
            for key, heading, filename in PAGES:
                page.locator(f".st-key-{key} button").click()
                page.get_by_role("heading",name=heading,exact=True).wait_for(timeout=60000)
                if args.expect_asof:
                    expected = datetime.strptime(args.expect_asof, "%Y-%m-%d").strftime("%d.%m.%Y")
                    page.locator('.vr-date strong').filter(has_text=expected).wait_for(timeout=60000)
                if key == "nav_statistics":
                    # Ảnh phải có kết quả thật, không chỉ tiêu đề hoặc cảnh báo thiếu báo cáo.
                    panel = page.get_by_text("Đánh giá ngoài mẫu · train trước, test sau", exact=True)
                    panel.click()
                    page.locator('.st-key-oos_fee').wait_for(state='visible', timeout=60000)
                if key == "nav_radar":
                    page.wait_for_function("""() => {
                        const values = [...document.querySelectorAll('[data-testid="stMetricValue"]')];
                        return values.length >= 4 && values.every(el => el.innerText.trim());
                    }""")
                page.locator('[data-testid="stStatusWidget"]').wait_for(state="hidden", timeout=60000)
                if page.locator('[data-testid="stException"]').count():
                    raise RuntimeError("Dashboard đang báo lỗi; sửa lỗi hiển thị trước khi chụp.")
                page.wait_for_function("""() => [...document.querySelectorAll('.js-plotly-plot')]
                    .filter(p => p.getBoundingClientRect().height > 0).every(p => p._fullLayout && p._fullData)""")
                page.evaluate("document.fonts.ready")
                page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
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
                recorded.append({"page": key, "file": filename,
                                 "analysis_date_label": page.locator('.vr-date strong').inner_text()})
            (folder / 'capture_manifest.json').write_text(json.dumps({
                'captured_at': datetime.now(timezone(timedelta(hours=7))).isoformat(),
                'cutoff_date': args.cutoff_date, 'expected_analysis_session': args.expect_asof,
                'url': args.url, 'pages': recorded,
            }, ensure_ascii=False, indent=2), encoding='utf-8')
        finally:
            browser.close()


if __name__ == "__main__":
    # CLI tiếng Việt dùng UTF-8 cả khi stdout/stderr bị chuyển vào pipe trên Windows.
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    main()
