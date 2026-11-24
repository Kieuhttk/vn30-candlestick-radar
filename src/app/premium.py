"""Giao diện VN30 Radar: menu dọc, font Inter cục bộ và màu nhấn đỏ neon."""
from functools import lru_cache
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from analytics.setup_probability import summarize_setups

ACCENT, TEAL = "#ff244e", "#0b8a66"
PAGES = ["Radar", "Biểu đồ", "Kết quả nghiên cứu", "Chất lượng", "Phương pháp"]
NAV_KEYS = ["nav_radar", "nav_chart", "nav_statistics", "nav_quality", "nav_method"]
ICONS = ["radar", "candlestick_chart", "query_stats", "verified", "menu_book"]
CSS = """
<style>
:root{--vr-red:#ff244e;--vr-ink:#20212b;--vr-muted:#4a4d5c;--vr-line:#e8e8ee}
html,body,.stApp,button,input,textarea,select{font-family:'Inter','Segoe UI',sans-serif}
.stApp :is(h1,h2,h3,h4,p,label,button,input,textarea,select,th,td,small,strong,em){font-family:'Inter','Segoe UI',sans-serif!important}
.stApp [data-testid="stMarkdownContainer"],.stApp [data-testid="stCaptionContainer"]{font-family:'Inter','Segoe UI',sans-serif!important}
.stApp{background:#f6f6f9;color:var(--vr-ink)}
.block-container{max-width:1740px;padding:2.7rem 3rem 3rem}
[data-testid="stHeader"]{background:#f6f6f9e8}
[data-testid="stSidebar"]{background:#fff;border-right:1px solid var(--vr-line)}
[data-testid="stSidebarUserContent"]{padding-top:.6rem}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{gap:.65rem}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label{font-size:13px}
.vr-brand{display:flex;align-items:center;gap:11px;margin:0 0 24px}
.vr-logo{width:40px;height:40px;display:grid;place-items:center;border-radius:12px;background:linear-gradient(145deg,#ff5274,#ff1649);box-shadow:0 7px 18px #ff244e26;color:white}
.vr-brand b{font-size:20px;letter-spacing:-.8px;color:#20212b;font-weight:750}
.vr-brand small{display:block;font-size:9px;letter-spacing:1.65px;color:#646879;margin-top:4px}
.vr-nav-label{font-size:10px;letter-spacing:1.7px;color:#646879;margin:0 0 9px;font-weight:600}
.vr-filter-label{border-top:1px solid #eeeef3;padding-top:23px;margin:19px 0 13px;font-size:10px;letter-spacing:1.7px;color:#646879;font-weight:600}
[class*="st-key-nav_"] button{width:100%;justify-content:flex-start!important;border:0!important;border-radius:11px!important;min-height:43px!important;padding:9px 13px!important;box-shadow:none!important}
[class*="st-key-nav_"] button p{font-size:13px!important;font-weight:500!important;letter-spacing:-.1px}
[class*="st-key-nav_"] button>div{justify-content:flex-start!important;width:100%}
[class*="st-key-nav_"] button [data-has-shortcut]{justify-content:flex-start!important;gap:11px}
[class*="st-key-nav_"] button[kind="tertiary"]{color:#777985!important;background:transparent!important}
[class*="st-key-nav_"] button[kind="tertiary"]:hover{background:#f7f7fa!important;color:#30313c!important}
[class*="st-key-nav_"] button[kind="primary"]{color:#e7133f!important;background:#fff0f3!important;box-shadow:inset 3px 0 #ff244e!important}
[class*="st-key-nav_"] button[kind="primary"] p{font-weight:650!important}
.vr-topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;margin:0 0 22px;padding-bottom:16px;border-bottom:1px solid #e5e5ec}
.vr-crumb{color:#9a9aa6;font-size:12px}.vr-crumb b{color:#393a46;font-weight:550}
.vr-source{background:#fff;border:1px solid #e6e6ed;border-radius:99px;color:#777985;padding:7px 12px;font-size:10px;letter-spacing:.25px}
.vr-source i{display:inline-block;width:6px;height:6px;border-radius:50%;background:#a4a5b0;margin-right:6px}
.vr-hero{position:relative;overflow:hidden;padding:26px 30px;border-radius:18px;border:1px solid #f1dfe5;background:radial-gradient(ellipse at 82% 100%,#ffc2d350 0,transparent 58%),linear-gradient(105deg,#fff,#fff1f4 70%,#ffe5ed);margin:0 0 3px}
.vr-hero-grid{display:flex;align-items:center;justify-content:space-between;gap:28px;position:relative;z-index:1}
.vr-topline{font-size:9px;letter-spacing:1.9px;font-weight:600;color:#ad6576;margin-bottom:10px}
.vr-hero h1{font-size:34px!important;line-height:1.15!important;letter-spacing:-1.6px!important;font-weight:750!important;color:#262532!important;margin:0!important;padding:0!important}
.vr-hero h1 em{font-style:normal;color:#ff244e;margin-left:.18em}
.vr-hero p{font-size:13px;line-height:1.8;color:#786571;max-width:580px;margin:10px 0 0}
.vr-hero-art{width:145px;flex-shrink:0;opacity:.85;margin-left:auto;margin-right:12px}
.vr-date{background:#ffffffb8;border:1px solid #ffffffed;border-radius:14px;padding:16px 19px;flex-shrink:0;box-shadow:0 5px 20px #8f29400a}
.vr-date small{font-size:10px;color:#a3838c}.vr-date strong{display:block;font-size:24px;letter-spacing:-.7px;color:#452e39;margin:6px 0;font-weight:650}
.vr-date span{font-size:9px;color:#ab7786}.vr-dot{display:inline-block;width:5px;height:5px;background:#ff244e;border-radius:50%;margin-right:5px;box-shadow:0 0 7px #ff244e55}
[data-testid="stMetric"]{background:#fff;border:1px solid var(--vr-line);border-radius:15px;padding:18px 20px;box-shadow:0 3px 16px #29273803;position:relative;min-height:102px}
[data-testid="stMetricLabel"] p{font-size:13.5px!important;color:#3a3d4c!important;font-weight:500}
[data-testid="stMetricValue"]{font-family:'Inter',sans-serif!important;font-size:30px!important;font-weight:650;letter-spacing:-1px;color:#2e2e3b}
.st-key-price_card,.st-key-signals_card,.st-key-confirm_card,.st-key-activity_card,.st-key-distribution_card{background:#fff;border:1px solid #e7e7ee!important;border-radius:17px;box-shadow:0 4px 20px #25223603}
.st-key-price_card{margin-top:8px}.st-key-signals_card{margin-top:8px}
.st-key-price_card>div,.st-key-signals_card>div,.st-key-confirm_card>div,.st-key-activity_card>div,.st-key-distribution_card>div{padding-top:2px}
h2,h3{color:#2b2c38;letter-spacing:-.5px;font-family:'Inter',sans-serif!important}
h3{font-size:16px!important;font-weight:650!important;line-height:1.5!important}
[data-testid="stCaptionContainer"]{color:#4a4d5c;font-size:13px;line-height:1.7}
[data-testid="stCaptionContainer"] p{font-size:13px!important;line-height:1.7!important;color:#4a4d5c!important}
[data-testid="stWidgetLabel"] p{font-size:13px;color:#4a4d5c}
[data-testid="stMain"] button{border-radius:9px;font-size:12px}
[data-testid="stDataFrame"]{border-radius:12px;overflow:hidden}
.vr-price{display:flex;align-items:baseline;gap:12px;margin:3px 0 0}.vr-price strong{font-size:33px;font-weight:650;color:#292b38;letter-spacing:-1.25px;font-variant-numeric:tabular-nums}
.vr-tag{font-size:10px;border-radius:7px;padding:5px 8px;background:#e8f7f0;color:#11765d;font-weight:550;white-space:nowrap}.vr-tag.down{background:#fff0f2;color:#ba2d4d}.vr-tag.neutral{background:#f2f2f7;color:#676a78}
.vr-row{display:flex;align-items:center;justify-content:space-between;gap:9px;padding:10px 0;border-bottom:1px solid #f0f0f5}
.vr-ticker{font-size:12px;font-weight:650;color:#4b4b59}.vr-pattern{font-size:13px;color:#4a4d5c;max-width:240px;margin-top:4px;line-height:1.5}
.vr-empty{font-size:12px;color:#747681;padding:18px 0}.vr-small{font-size:13px;color:#4a4d5c;line-height:1.7}
.vr-confirm{margin:6px 0 15px}.vr-confirm-head{display:flex;justify-content:space-between;align-items:center;font-size:11px;color:#838392}.vr-confirm-head b{font-size:17px;font-weight:650;color:#1b1c26}
.vr-track{height:5px;border-radius:20px;background:#f5f0f2;margin:9px 0}.vr-fill{height:100%;border-radius:20px;background:#272833}
.st-key-confirm_card [data-testid="stVerticalBlock"],.st-key-signals_card [data-testid="stVerticalBlock"]{gap:.65rem}
.vr-head{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;flex-wrap:wrap;margin:0 0 18px}
.vr-head h1{font-size:28px!important;line-height:1.2!important;letter-spacing:-.9px!important;font-weight:750!important;color:#1b1c26!important;margin:0!important;padding:0!important}
.vr-head h1 em{font-style:normal;color:#ff244e}.vr-head p{font-size:14px;color:#4a4d5c;margin:6px 0 0}
.vr-chips{display:flex;gap:8px;flex-wrap:wrap}.vr-chip{background:#fff;border:1px solid #d9dbe5;border-radius:10px;padding:8px 12px;font-size:13px;font-weight:550;color:#1b1c26}.vr-chip small{color:#646879;font-weight:400;margin-right:6px;font-size:12.5px}
.vr-dot.ok{background:#0b8a66;box-shadow:none}
.st-key-kpi_hi [data-testid="stMetric"]{background:#ff244e;border-color:#ff244e}
.st-key-kpi_hi [data-testid="stMetricLabel"] p,.st-key-kpi_hi [data-testid="stMetricValue"]{color:#fff!important}
.vr-kpi-note{font-size:12.5px;color:#4a4d5c;margin:-2px 0 0 4px}
.st-key-detail_card{background:#fff;border:1px solid #e4e5ec!important;border-radius:16px}
.vr-dhead{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}.vr-dhead h3{margin:0!important;font-size:18px!important}
.vr-dprice{text-align:right}.vr-dprice strong{font-size:28px;font-weight:700;letter-spacing:-1px;font-variant-numeric:tabular-nums}
.vr-steps{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:12px 0}
.vr-steps div{background:#f7f7fa;border-radius:12px;padding:12px;font-size:13.5px;line-height:1.55;color:#2d2f3c}
.vr-steps b{display:block;font-size:11.5px;letter-spacing:.8px;color:#c4062e;margin-bottom:4px}
.vr-ctx{background:#fff7e6;border-radius:12px;padding:12px 14px;font-size:13.5px;line-height:1.55;color:#4d3a00;margin:8px 0}.vr-ctx b{font-size:20px;color:#1b1c26;margin-right:6px}
.vr-verdict{background:#1b1c26;color:#fff;border-radius:16px;padding:18px 22px;line-height:1.65;font-size:14px;margin:0 0 14px}.vr-verdict b{color:#ff8fa5}
@media(max-width:900px){.vr-steps{grid-template-columns:1fr}}
@media(min-width:1100px){[data-testid="stSidebar"][data-collapsed="false"]{width:266px!important;min-width:266px!important;max-width:266px!important}}
@media(max-width:1100px){.vr-hero-art{display:none}.block-container{padding-left:1.6rem;padding-right:1.6rem}.vr-hero h1{font-size:28px!important}}
@media(max-width:750px){.vr-hero-grid{flex-wrap:wrap}.vr-hero{padding:22px}.vr-date{padding:11px 15px}.vr-topbar{margin-bottom:16px}.vr-source{display:none}.block-container{padding:2rem 1rem}.vr-price{flex-wrap:wrap}.vr-hero h1{font-size:26px!important}}
</style>
"""


@lru_cache(maxsize=1)
def _font_css():
    path = Path(__file__).resolve().parents[2] / "assets/fonts/inter.css"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def apply_theme():
    st.markdown("<style>" + _font_css() + "</style>" + CSS, unsafe_allow_html=True)


def sidebar_brand():
    st.markdown("""<div class="vr-brand"><div class="vr-logo"><svg width="25" height="25" viewBox="0 0 26 26" fill="none"><path d="M4 17l5-8 5 11 7-14" stroke="white" stroke-width="2.7" stroke-linecap="round" stroke-linejoin="round"/></svg></div><div><b>VN30 Radar<span style="color:#ff244e">.</span></b><small>CANDLESTICK RESEARCH</small></div></div>""", unsafe_allow_html=True)


def _navigate(page):
    st.session_state["nav_page"] = page


def sidebar_menu():
    # Giữ lựa chọn của từng trang khi widget tạm thời không được render.
    selected = st.session_state.get("symbols")
    for key in ("overview_symbol", "chart_symbol", "signals_only", "stats_scope", "setup_filter", "outcome_filter", "severity"):
        if key in st.session_state:
            if key in ("overview_symbol", "chart_symbol") and selected is not None and st.session_state[key] not in selected:
                del st.session_state[key]
            else:
                st.session_state[key] = st.session_state[key]
    page = st.session_state.get("nav_page", "Radar")
    if page not in PAGES:
        page = "Radar"
    st.markdown('<div class="vr-nav-label">KHÔNG GIAN PHÂN TÍCH</div>', unsafe_allow_html=True)
    for name, key, icon in zip(PAGES, NAV_KEYS, ICONS):
        st.button(name, key=key, icon=f":material/{icon}:", type="primary" if page == name else "tertiary",
                  width="stretch", on_click=_navigate, args=(name,))
    st.markdown('<div class="vr-filter-label">BỘ LỌC PHIÊN QUÉT</div>', unsafe_allow_html=True)
    return page


def hero(asof, stored_last, count, page="Radar"):
    titles = {"Radar": "Hiểu <em>tín hiệu giá</em>", "Biểu đồ": "Đọc <em>diễn biến giá</em>",
              "Kết quả nghiên cứu": "Đọc <em>kết quả nghiên cứu</em>", "Chất lượng": "Kiểm tra <em>dữ liệu</em>", "Phương pháp": "Hiểu <em>phương pháp</em>"}
    subs = {"Radar": "Chọn một dòng để đọc ý nghĩa của mẫu hình và điều kiện cần theo dõi.",
            "Biểu đồ": "Giá, khối lượng và vị trí xuất hiện mẫu hình của từng mã.",
            "Kết quả nghiên cứu": "Mẫu hình đã đủ ba nến chưa, và giá sau đó diễn biến ra sao so với mức nền.",
            "Chất lượng": "Phiên thiếu, cảnh báo dữ liệu và nhật ký nạp.",
            "Phương pháp": "Định nghĩa, giả định và giới hạn của nghiên cứu."}
    st.markdown(f'''<div class="vr-hero"><div class="vr-hero-grid">
    <div><div class="vr-topline">VN30 CANDLESTICK RADAR</div>
    <h1>{titles.get(page, titles["Radar"])}</h1>
    <p>{escape(subs.get(page, ""))}<br>Phạm vi theo dõi: {count} cổ phiếu.</p></div>
    <div class="vr-hero-art" aria-hidden="true"><svg width="145" height="112" viewBox="0 0 145 112" fill="none">
    <circle cx="75" cy="56" r="48" stroke="#ff244e" stroke-opacity=".10"/>
    <circle cx="75" cy="56" r="34" stroke="#ff244e" stroke-opacity=".10"/>
    <path d="M20 90L47 68L74 75L109 32L132 20" stroke="#ff244e" stroke-opacity=".2" stroke-width="2" stroke-dasharray="4 5"/>
    <path d="M37 49v36M67 36v42M97 20v48" stroke="#ff244e" stroke-width="2"/>
    <rect x="29" y="60" width="16" height="16" rx="3" fill="#ff9ab1"/>
    <rect x="59" y="46" width="16" height="23" rx="3" fill="#ff688d"/>
    <rect x="89" y="29" width="16" height="27" rx="3" fill="#ff244e"/>
    <circle cx="121" cy="24" r="4" fill="#ff244e"/></svg></div>
    <div class="vr-date"><small>Ngày phân tích</small><strong>{asof:%d.%m.%Y}</strong>
    <span><i class="vr-dot"></i>Bản lưu đến {stored_last:%d/%m/%Y}</span></div>
    </div></div>''', unsafe_allow_html=True)


def _style(fig, height):
    fig.update_layout(template="plotly_white", height=height, font={"family":"Inter, sans-serif","size":12,"color":"#4a4d5c"},
        paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",margin={"l":6,"r":10,"t":10,"b":5},
        legend={"orientation":"h","y":1.04},hoverlabel={"bgcolor":"white","font":{"color":"#30303b"}})
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#f0f0f5",zeroline=False)
    return fig


def render_overview(frames, latest, events, current, all_outcomes, selected, asof, start, market_days):
    left, right = st.columns([1.35, 1], gap="medium")
    with left:
        with st.container(border=True, key="signals_card"):
            st.subheader("Tín hiệu cần tìm hiểu")
            active = latest[latest.patterns.ne("") | latest.setups.ne("")]
            if active.empty:
                st.markdown('<div class="vr-empty">Chưa có tín hiệu trong ngày chọn.</div>', unsafe_allow_html=True)
            for row in active.head(5).itertuples(index=False):
                bias = set(current.loc[current.symbol == row.symbol,"bias"])
                label = "Gợi ý tăng" if bias == {"bullish"} else "Gợi ý giảm" if bias == {"bearish"} else "Chưa rõ hướng" if bias == {"neutral"} else "Đọc từng nhãn"
                description = row.patterns or row.setups
                st.markdown(f'<div class="vr-row"><div><div class="vr-ticker">{escape(row.symbol)}</div><div class="vr-pattern">{escape(description)}</div></div><span class="vr-tag {"down" if bias == {"bearish"} else "neutral" if bias == {"neutral"} else ""}">{label}</span></div>', unsafe_allow_html=True)
            st.caption(f"{len(active)} mã có tín hiệu. Gợi ý tăng/giảm là hướng theo lý thuyết; xem thẻ giải thích để biết trạng thái, chưa phải lệnh mua/bán.")
    with right:
        with st.container(border=True, key="confirm_card"):
            st.subheader("Cảnh báo sớm hoàn thành bao nhiêu lần?")
            summary = summarize_setups(all_outcomes[all_outcomes.symbol.isin(selected)])
            for row in summary.itertuples(index=False):
                rate = "—" if pd.isna(row.probability) else f"{row.probability*100:.2f}%".replace(".",",")
                width = 0 if pd.isna(row.probability) else row.probability*100
                st.markdown(f'<div class="vr-confirm"><div class="vr-confirm-head"><span>{row.name_vi}</span><b>{rate}</b></div><div class="vr-track"><div class="vr-fill" style="width:{width:.4f}%"></div></div><div class="vr-small">{row.n_completed}/{row.n_evaluated} lần đủ mẫu hình ba nến</div></div>', unsafe_allow_html=True)
            st.caption(f"Toàn bộ lịch sử đến {asof:%d/%m/%Y}. Tỷ lệ hoàn thành mẫu hình, chưa phải tỷ lệ sinh lời.")
    first, second = st.columns([1.35, 1], gap="medium")
    with first:
        with st.container(border=True, key="activity_card"):
            st.subheader("Nhịp xuất hiện tín hiệu")
            dates = market_days[-30:]
            activity = events[events.kind == "pattern"].groupby("date").symbol.nunique().reindex(dates,fill_value=0)
            fig = go.Figure(go.Scatter(x=activity.index,y=activity.values,mode="lines",fill="tozeroy",line={"color":"#4a4d5c","width":2},fillcolor="rgba(74,77,92,.08)",hovertemplate="%{x|%d/%m/%Y}: %{y} mã<extra></extra>"))
            fig.update_yaxes(title="Số mã có mẫu hình",rangemode="tozero",dtick=1 if activity.max()<=5 else None)
            st.plotly_chart(_style(fig,210),width="stretch",key="overview_activity")
            st.caption("Tối đa 30 phiên đến ngày quét, trong khoảng lịch sử hiển thị.")
    with second:
        with st.container(border=True, key="distribution_card"):
            st.subheader("Phân bố nhãn mẫu hình")
            counts = events.loc[events.kind == "pattern","bias"].value_counts()
            names={"bullish":"Hướng tăng","bearish":"Hướng giảm","neutral":"Trung tính"}
            colors={"bullish":"#0b8a66","bearish":"#d9304e","neutral":"#dfdfe9"}
            if counts.empty:
                st.info("Chưa có mẫu hình trong khoảng đang xem.")
            else:
                fig=go.Figure(go.Pie(labels=[names[k] for k in counts.index],values=counts.values,hole=.75,marker_colors=[colors[k] for k in counts.index],textinfo="none",hovertemplate="%{label}: %{value} nhãn<extra></extra>"))
                fig.update_layout(annotations=[{"text":f"<b>{int(counts.sum()):,}</b><br>nhãn","x":.5,"y":.5,"showarrow":False,"font":{"size":19,"color":"#41404f"}}])
                fig=_style(fig,210);fig.update_layout(legend={"orientation":"h","y":-.05,"x":.5,"xanchor":"center"})
                st.plotly_chart(fig,width="stretch",key="overview_distribution")
            st.caption("Phân loại theo định nghĩa mẫu hình; một phiên có thể mang nhiều nhãn.")
