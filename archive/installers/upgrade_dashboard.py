"""Nâng cấp giao diện VN30 Radar, có sao lưu và kiểm tra phiên bản main.py."""
from pathlib import Path
from datetime import datetime
import shutil
import re

import ast
import textwrap


def upgrade_source(source):
    if "from app.premium import" in source:
        return source
    tree = ast.parse(source)
    main = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"), None)
    if main is None or "all_outcomes" not in source:
        raise ValueError("Cần bản main.py có hàm main() và tab Thống kê cảnh báo từ bước trước. Chưa ghi đè tệp nào.")
    lines = source.splitlines(keepends=True)
    starts = [0]
    for line in lines: starts.append(starts[-1] + len(line))
    changes = []

    def replace(node, text):
        indent = " " * node.col_offset
        changes.append((starts[node.lineno-1], starts[node.end_lineno], textwrap.indent(text.rstrip()+"\n", indent)))

    def st_call(node, name):
        return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "st" and node.func.attr == name

    def text_of(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str): return node.value
        if isinstance(node, ast.JoinedStr): return "".join(n.value for n in node.values if isinstance(n, ast.Constant) and isinstance(n.value, str))
        return ""

    sidebar_index = next(i for i,n in enumerate(main.body) if isinstance(n, ast.With) and any(isinstance(item.context_expr, ast.Attribute) and item.context_expr.attr == "sidebar" for item in n.items))
    found_style = found_header = found_sidebar = found_selected = found_overview = False
    for statement in main.body[:sidebar_index]:
        if not isinstance(statement, ast.Expr): continue
        call = statement.value
        if st_call(call, "markdown") and call.args and "<style>" in text_of(call.args[0]):
            replace(statement, "apply_theme()")
            found_style = True
        elif st_call(call, "caption") or st_call(call, "title"):
            replace(statement, "")
    for node in ast.walk(main):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            text = text_of(call.args[0]) if call.args else ""
            if st_call(call, "header") and text == "Bộ lọc phân tích":
                replace(node, "sidebar_brand()")
                found_sidebar = True
            elif st_call(call, "info") and text.startswith("Ngày phân tích:"):
                replace(node, "hero(asof, stored_last, len(selected))")
                found_header = True
        if isinstance(node, ast.Assign) and any(isinstance(t,ast.Name) and t.id == "selected" for t in node.targets) and st_call(node.value, "multiselect"):
            original = "".join(lines[node.lineno-1:node.end_lineno])
            body = textwrap.indent(textwrap.dedent(original), "    ")
            replace(node, 'with st.expander("Nhóm cổ phiếu", expanded=False):\n'+body+'st.caption(f"{len(selected)}/{len(universe)} mã được chọn")')
            found_selected = True
        if isinstance(node, ast.With) and any(isinstance(item.context_expr,ast.Name) and item.context_expr.id == "tab1" for item in node.items):
            first = node.body[0]
            if not isinstance(first,ast.Expr) or not st_call(first.value,"subheader"):
                raise ValueError("Bố cục tab Radar khác bản dự kiến; chưa thay tệp.")
            replace(first, 'render_overview(frames, latest, events, current, all_outcomes, selected, asof, start, radar.market_days)\nst.subheader("Bảng quét cổ phiếu")')
            found_overview = True
    if not all([found_style, found_header, found_sidebar, found_selected, found_overview]):
        raise ValueError("Không tìm đủ vị trí cần sửa trong main.py. Chưa ghi đè tệp nào.")
    imports = [node for node in tree.body if isinstance(node,(ast.Import,ast.ImportFrom))]
    position = starts[imports[-1].end_lineno]
    changes.append((position, position, "from app.premium import apply_theme, sidebar_brand, hero, render_overview\n"))
    for begin,end,text in sorted(changes, key=lambda item:item[0], reverse=True):
        source = source[:begin] + text + source[end:]
    ast.parse(source)
    return source

PREMIUM_CODE = r'''"""Trình bày dashboard; số liệu luôn lấy từ các kết quả phân tích đã tính."""
from html import escape

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from analytics.setup_probability import summarize_setups

TEAL = "#087f78"
CSS = """
<style>
.stApp{background:radial-gradient(ellipse at 88% 0%,#e2f0ef 0,transparent 38%),#f3f6f7}
.block-container{padding-top:3.4rem;padding-bottom:3rem;max-width:1780px}
[data-testid="stSidebar"]{background:#fbfdfd;border-right:1px solid #dce8e8}
[data-testid="stHeader"]{background:rgba(243,246,247,.8)}
.vr-brand{display:flex;align-items:center;gap:12px;margin:0 0 26px}
.vr-logo{width:42px;height:42px;border-radius:13px;background:#064e55;color:#fff;display:grid;place-items:center;font-size:25px;font-weight:800}
.vr-brand b{font-size:19px;color:#153d45}.vr-brand small{display:block;color:#799096;font-size:10px;letter-spacing:1.5px;margin-top:3px}
.vr-hero{position:relative;overflow:hidden;padding:30px 34px 32px;border-radius:24px;background:radial-gradient(ellipse at 96% 110%,#b8e3d4 0,transparent 46%),linear-gradient(110deg,#003e4c,#076a72 65%,#4a9995);box-shadow:0 12px 35px #063a4512;color:white}
.vr-hero:after{content:'';position:absolute;width:330px;height:330px;border:1px solid #ffffff15;border-radius:50%;right:40px;top:-170px;pointer-events:none}
.vr-topline{font-size:10px;letter-spacing:2px;color:#bce2df;margin-bottom:12px}
.vr-hero-grid{display:flex;align-items:center;justify-content:space-between;gap:22px;position:relative;z-index:1}
.vr-hero h1{font-size:2.05rem!important;line-height:1.2!important;letter-spacing:-1.2px!important;color:white!important;margin:0!important;padding:0!important}
.vr-hero p{color:#d3e9e8;font-size:13px;line-height:1.65;max-width:610px;margin:12px 0 0}
.vr-date{flex-shrink:0;background:#ffffff16;border:1px solid #ffffff3a;border-radius:16px;padding:16px 22px;backdrop-filter:blur(8px)}
.vr-date small{color:#d5eeec;font-size:11px}.vr-date strong{display:block;font-size:24px;letter-spacing:-.5px;margin:3px 0;color:white}
.vr-date span{font-size:10px;color:#e2f4ed}.vr-dot{display:inline-block;width:6px;height:6px;background:#9bedd0;border-radius:50%;margin-right:5px}
[data-testid="stMetric"]{background:linear-gradient(135deg,#fff,#f9fcfc);border:1px solid #e0e9e9;border-radius:18px;padding:16px 20px;box-shadow:0 5px 18px #123c4606}
[data-testid="stMetricLabel"]{font-size:12px;color:#6c848d}[data-testid="stMetricValue"]{font-size:1.9rem;color:#123b45;letter-spacing:-.8px}
.stTabs [role="tablist"]{gap:7px;background:#ffffffa8;padding:6px;border-radius:999px;border:1px solid #e3ecec;width:fit-content;margin:5px 0 12px}
.stTabs [role="tab"]{border-radius:999px;padding:10px 16px;height:auto;font-size:13px;color:#647d86;border:0!important}
.stTabs [role="tab"][aria-selected="true"]{background:#087f78!important;color:white!important}
.stTabs [data-baseweb="tab-highlight"]{background:transparent}
.st-key-price_card,.st-key-signals_card,.st-key-confirm_card,.st-key-activity_card,.st-key-distribution_card{background:#ffffffd9;border-radius:20px;box-shadow:0 7px 25px #123c4505}
h2,h3{color:#173c46;letter-spacing:-.5px}h3{font-size:1.15rem!important}
.vr-price{display:flex;align-items:baseline;gap:14px;margin:4px 0 2px}.vr-price strong{font-size:31px;font-weight:700;color:#153b44;letter-spacing:-1px}
.vr-tag{font-size:11px;border-radius:8px;padding:5px 9px;background:#e5f5f0;color:#08785f;font-weight:600}.vr-tag.down{background:#fceeee;color:#be5460}
.vr-row{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:11px 0;border-bottom:1px solid #eef2f2}
.vr-ticker{font-weight:700;color:#244650;font-size:13px}.vr-pattern{color:#7b9098;font-size:11px;line-height:1.5;max-width:185px;margin-top:2px}
.vr-empty{padding:18px 0;color:#80949a;font-size:13px}.vr-small{color:#81949b;font-size:11px;line-height:1.6}
.vr-confirm{margin:8px 0 17px}.vr-confirm-head{display:flex;justify-content:space-between;color:#536f78;font-size:12px}.vr-confirm-head b{font-size:18px;color:#087f78}
.vr-track{height:6px;background:#edf3f3;border-radius:20px;margin:8px 0}.vr-fill{height:100%;background:linear-gradient(90deg,#0b827b,#7bcbbb);border-radius:20px}
[data-testid="stDataFrame"]{border-radius:14px;overflow:hidden}
@media(max-width:800px){.vr-hero-grid{flex-direction:column;align-items:flex-start}.vr-hero{padding:24px}.vr-date{padding:10px 16px}.vr-hero h1{font-size:1.7rem!important}.stTabs [role="tablist"]{width:100%;border-radius:16px;flex-wrap:wrap}}
</style>
"""


def apply_theme():
    st.markdown(CSS, unsafe_allow_html=True)


def sidebar_brand():
    st.markdown('<div class="vr-brand"><div class="vr-logo">∿</div><div><b>VN30 Radar</b><small>CANDLESTICK RESEARCH</small></div></div>', unsafe_allow_html=True)
    st.caption("PHẠM VI PHÂN TÍCH")


def hero(asof, stored_last, count):
    st.markdown(f"""<div class="vr-hero"><div class="vr-topline">PHÂN TÍCH THỊ TRƯỜNG / VN30</div>
    <div class="vr-hero-grid"><div><h1>VN30 Candlestick Radar</h1>
    <p>Quan sát thị trường. Hiểu từng tín hiệu.<br>Quét mẫu hình nến và kiểm chứng bằng lịch sử của {count} cổ phiếu đang chọn.</p></div>
    <div class="vr-date"><small>Ngày phân tích</small><strong>{asof:%d.%m.%Y}</strong><span><i class="vr-dot"></i>SSI · Bản lưu đến {stored_last:%d/%m/%Y}</span></div></div></div>""", unsafe_allow_html=True)


def _style(fig, height):
    fig.update_layout(template="plotly_white", height=height, font={"family": "Arial, sans-serif", "size": 11, "color": "#6c848d"},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin={"l": 6, "r": 10, "t": 10, "b": 5},
        legend={"orientation": "h", "y": 1.04}, hoverlabel={"bgcolor": "white"})
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#edf2f3", zeroline=False)
    return fig


def render_overview(frames, latest, events, current, all_outcomes, selected, asof, start, market_days):
    left, right = st.columns([2.35, 1], gap="medium")
    with left:
        with st.container(border=True, key="price_card"):
            st.subheader("Diễn biến cổ phiếu")
            symbol = st.selectbox("Cổ phiếu quan sát", selected, index=selected.index("FPT") if "FPT" in selected else 0, key="overview_symbol")
            frame = frames[symbol].loc[lambda f: (f.index >= start) & (f.index <= asof)]
            if frame.empty:
                st.info("Chưa có nến của mã này trong khoảng đang xem.")
            else:
                price = f"{frame.close.iloc[-1]:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
                row = latest.set_index("symbol").loc[symbol]
                change = row.change_pct
                badge = "" if pd.isna(change) else f'<span class="vr-tag {"down" if change < 0 else ""}">{change:+.2f}% so với phiên trước</span>'
                st.markdown(f'<div class="vr-price"><strong>{price}</strong>{badge}</div><div class="vr-small">{escape(symbol)} · Giá SSI, đồng · Nến cuối {frame.index[-1]:%d/%m/%Y}</div>', unsafe_allow_html=True)
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=.035, row_heights=[.8,.2])
                fig.add_trace(go.Candlestick(x=frame.index, open=frame.open, high=frame.high, low=frame.low, close=frame.close,
                    increasing_line_color=TEAL, decreasing_line_color="#d46b74", name=symbol, showlegend=False), row=1, col=1)
                colors = ["#b6dcd6" if c >= o else "#ebc8cc" for o,c in zip(frame.open,frame.close)]
                fig.add_trace(go.Bar(x=frame.index, y=frame.volume, marker_color=colors, name="Khối lượng", showlegend=False), row=2, col=1)
                signals = events[(events.symbol == symbol) & (events.kind == "pattern")]
                if not signals.empty:
                    fig.add_trace(go.Scatter(x=signals.date, y=frame.loc[signals.date,"close"].to_numpy(), mode="markers", text=signals.name_vi,
                        marker={"color":"#d6a44b","size":6}, name="Mẫu hình", showlegend=False, hovertemplate="%{x|%d/%m/%Y}<br>%{text}<extra></extra>"),row=1,col=1)
                fig.update_layout(xaxis_rangeslider_visible=False)
                fig.update_yaxes(side="right")
                st.plotly_chart(_style(fig, 380), width="stretch", key="overview_candles")
                st.caption("Chấm vàng: mẫu hình đã nhận diện · Biểu đồ dùng chuỗi giá SSI đang lưu.")
    with right:
        with st.container(border=True, key="signals_card"):
            st.subheader("Tín hiệu mới")
            active = latest[latest.patterns.ne("") | latest.setups.ne("")]
            if active.empty:
                st.markdown('<div class="vr-empty">Chưa có tín hiệu trong ngày chọn.</div>', unsafe_allow_html=True)
            for row in active.head(5).itertuples(index=False):
                bias = set(current.loc[current.symbol == row.symbol,"bias"])
                label = "Hướng tăng" if bias == {"bullish"} else "Hướng giảm" if bias == {"bearish"} else "Trung tính" if bias == {"neutral"} else "Nhiều nhãn"
                description = row.patterns or row.setups
                st.markdown(f'<div class="vr-row"><div><div class="vr-ticker">{escape(row.symbol)}</div><div class="vr-pattern">{escape(description)}</div></div><span class="vr-tag {"down" if bias == {"bearish"} else ""}">{label}</span></div>', unsafe_allow_html=True)
            st.caption(f"{len(active)} mã có tín hiệu · Xem đầy đủ trong bảng quét bên dưới.")
        with st.container(border=True, key="confirm_card"):
            st.subheader("Xác nhận trong lịch sử")
            summary = summarize_setups(all_outcomes[all_outcomes.symbol.isin(selected)])
            for row in summary.itertuples(index=False):
                rate = "—" if pd.isna(row.probability) else f"{row.probability*100:.2f}%".replace(".",",")
                width = 0 if pd.isna(row.probability) else row.probability*100
                st.markdown(f'<div class="vr-confirm"><div class="vr-confirm-head"><span>{row.name_vi}</span><b>{rate}</b></div><div class="vr-track"><div class="vr-fill" style="width:{width:.4f}%"></div></div><div class="vr-small">{row.n_completed}/{row.n_evaluated} cảnh báo được xác nhận</div></div>', unsafe_allow_html=True)
            st.caption(f"Toàn bộ lịch sử đến {asof:%d/%m/%Y}. Tỷ lệ hoàn thành mẫu hình, chưa phải tỷ lệ sinh lời.")
    first, second = st.columns([1.35, 1], gap="medium")
    with first:
        with st.container(border=True, key="activity_card"):
            st.subheader("Nhịp xuất hiện tín hiệu")
            dates = market_days[-30:]
            activity = events[events.kind == "pattern"].groupby("date").symbol.nunique().reindex(dates,fill_value=0)
            fig = go.Figure(go.Scatter(x=activity.index,y=activity.values,mode="lines",fill="tozeroy",line={"color":TEAL,"width":2},fillcolor="rgba(8,127,120,.12)",hovertemplate="%{x|%d/%m/%Y}: %{y} mã<extra></extra>"))
            fig.update_yaxes(title="Số mã có mẫu hình",rangemode="tozero",dtick=1 if activity.max()<=5 else None)
            st.plotly_chart(_style(fig,210),width="stretch",key="overview_activity")
            st.caption("Tối đa 30 phiên đến ngày quét, trong khoảng lịch sử hiển thị.")
    with second:
        with st.container(border=True, key="distribution_card"):
            st.subheader("Phân bố nhãn mẫu hình")
            counts = events.loc[events.kind == "pattern","bias"].value_counts()
            names={"bullish":"Hướng tăng","bearish":"Hướng giảm","neutral":"Trung tính"}
            colors={"bullish":TEAL,"bearish":"#d6868e","neutral":"#c6d8dc"}
            if counts.empty:
                st.info("Chưa có mẫu hình trong khoảng đang xem.")
            else:
                fig=go.Figure(go.Pie(labels=[names[k] for k in counts.index],values=counts.values,hole=.75,marker_colors=[colors[k] for k in counts.index],textinfo="none",hovertemplate="%{label}: %{value} nhãn<extra></extra>"))
                fig.update_layout(annotations=[{"text":f"<b>{int(counts.sum()):,}</b><br>nhãn","x":.5,"y":.5,"showarrow":False,"font":{"size":19,"color":"#244650"}}])
                fig=_style(fig,210);fig.update_layout(legend={"orientation":"h","y":-.05,"x":.5,"xanchor":"center"})
                st.plotly_chart(fig,width="stretch",key="overview_distribution")
            st.caption("Phân loại theo định nghĩa mẫu hình; một phiên có thể mang nhiều nhãn.")
'''

CAPTURE_CODE = r'''"""Chụp dashboard đang chạy và lưu PNG vào report/screenshots."""
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
'''


THEME = """[theme]
primaryColor = "#087f78"
backgroundColor = "#f3f6f7"
secondaryBackgroundColor = "#ffffff"
textColor = "#173c46"
font = "sans serif"
"""


def main():
    root = Path(__file__).resolve().parent
    main_path = root / "src/app/main.py"
    if not main_path.is_file():
        raise ValueError("Đặt upgrade_dashboard.py trong thư mục gốc vn30-candlestick-radar, cùng cấp pyproject.toml.")
    source = main_path.read_text(encoding="utf-8-sig")
    updated = upgrade_source(source)
    compile(updated, "main.py", "exec")
    compile(PREMIUM_CODE, "premium.py", "exec")
    compile(CAPTURE_CODE, "capture_dashboard.py", "exec")
    config_path = root / ".streamlit/config.toml"
    config = config_path.read_text(encoding="utf-8-sig") if config_path.exists() else ""
    if re.search(r"(?m)^\[theme\]\s*$", config):
        config = re.sub(r"(?ms)^\[theme\][^\n]*\n.*?(?=^\[|\Z)", THEME + "\n", config)
    else:
        config = config.rstrip() + "\n\n" + THEME
    targets = {
        root / "src/app/premium.py": PREMIUM_CODE,
        root / "capture_dashboard.py": CAPTURE_CODE,
        config_path: config.lstrip(),
        main_path: updated,
    }
    backup = root / ("backup_dashboard_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    backup.mkdir()
    existed = {path: path.exists() for path in targets}
    for path in targets:
        if existed[path]:
            saved = backup / path.relative_to(root)
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, saved)
    written = []
    try:
        for path, content in targets.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(path.name + ".upgrade_tmp")
            temp.write_text(content, encoding="utf-8")
            temp.replace(path)
            written.append(path)
    except Exception:
        for path in reversed(written):
            if existed[path]:
                shutil.copy2(backup / path.relative_to(root), path)
            else:
                path.unlink(missing_ok=True)
        raise
    print("Nâng cấp giao diện thành công.")
    print("Bản sao giao diện cũ:", backup)
    print("Đã tạo:", root / "capture_dashboard.py")
    print("Trong .venv, chạy dashboard: python -m streamlit run src/app/main.py")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit("Không thể nâng cấp: " + str(exc))
