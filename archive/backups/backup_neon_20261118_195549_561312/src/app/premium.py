"""Giao diện VN30 Radar: menu dọc, font Inter cục bộ và màu nhấn đỏ neon."""
from functools import lru_cache
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from analytics.setup_probability import summarize_setups

ACCENT, TEAL = "#ff244e", "#159b7e"
PAGES = ["Radar", "Biểu đồ", "Thống kê cảnh báo", "Chất lượng", "Phương pháp"]
NAV_KEYS = ["nav_radar", "nav_chart", "nav_statistics", "nav_quality", "nav_method"]
ICONS = ["radar", "candlestick_chart", "query_stats", "verified", "menu_book"]
CSS = """
<style>
:root{--vr-red:#ff244e;--vr-ink:#20212b;--vr-muted:#777985;--vr-line:#e8e8ee}
html,body,.stApp,button,input,textarea,select{font-family:'Inter','Segoe UI',sans-serif}
.stApp :is(h1,h2,h3,h4,p,label,button,input,textarea,select,th,td,small,strong,em){font-family:'Inter','Segoe UI',sans-serif!important}
.stApp [data-testid="stMarkdownContainer"],.stApp [data-testid="stCaptionContainer"]{font-family:'Inter','Segoe UI',sans-serif!important}
.stApp{background:#f6f6f9;color:var(--vr-ink)}
.block-container{max-width:1740px;padding:2.7rem 3rem 3rem}
[data-testid="stHeader"]{background:#f6f6f9e8}
[data-testid="stSidebar"]{background:#fff;border-right:1px solid var(--vr-line)}
[data-testid="stSidebarUserContent"]{padding-top:.6rem}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{gap:.65rem}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label{font-size:12px}
.vr-brand{display:flex;align-items:center;gap:11px;margin:0 0 24px}
.vr-logo{width:40px;height:40px;display:grid;place-items:center;border-radius:12px;background:linear-gradient(145deg,#ff5274,#ff1649);box-shadow:0 7px 18px #ff244e26;color:white}
.vr-brand b{font-size:20px;letter-spacing:-.8px;color:#20212b;font-weight:750}
.vr-brand small{display:block;font-size:9px;letter-spacing:1.65px;color:#93939f;margin-top:4px}
.vr-nav-label{font-size:10px;letter-spacing:1.7px;color:#9899a4;margin:0 0 9px;font-weight:600}
.vr-filter-label{border-top:1px solid #eeeef3;padding-top:23px;margin:19px 0 13px;font-size:10px;letter-spacing:1.7px;color:#9899a4;font-weight:600}
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
[data-testid="stMetric"]:after{content:'';position:absolute;top:22px;right:19px;width:7px;height:7px;background:#ff244e;border-radius:50%;box-shadow:0 0 0 5px #fff0f3}
[data-testid="stMetricLabel"] p{font-size:11px!important;color:#8a8b98!important;font-weight:500}
[data-testid="stMetricValue"]{font-family:'Inter',sans-serif!important;font-size:30px!important;font-weight:650;letter-spacing:-1px;color:#2e2e3b}
.st-key-price_card,.st-key-signals_card,.st-key-confirm_card,.st-key-activity_card,.st-key-distribution_card{background:#fff;border:1px solid #e7e7ee!important;border-radius:17px;box-shadow:0 4px 20px #25223603}
.st-key-price_card{margin-top:8px}.st-key-signals_card{margin-top:8px}
.st-key-price_card>div,.st-key-signals_card>div,.st-key-confirm_card>div,.st-key-activity_card>div,.st-key-distribution_card>div{padding-top:2px}
h2,h3{color:#2b2c38;letter-spacing:-.5px;font-family:'Inter',sans-serif!important}
h3{font-size:16px!important;font-weight:650!important;line-height:1.5!important}
[data-testid="stCaptionContainer"]{color:#747681;font-size:11px;line-height:1.7}
[data-testid="stCaptionContainer"] p{font-size:11px!important;line-height:1.7!important}
[data-testid="stWidgetLabel"] p{font-size:12px;color:#777985}
[data-testid="stMain"] button{border-radius:9px;font-size:12px}
[data-testid="stDataFrame"]{border-radius:12px;overflow:hidden}
.vr-price{display:flex;align-items:baseline;gap:12px;margin:3px 0 0}.vr-price strong{font-size:33px;font-weight:650;color:#292b38;letter-spacing:-1.25px;font-variant-numeric:tabular-nums}
.vr-tag{font-size:10px;border-radius:7px;padding:5px 8px;background:#e8f7f0;color:#11765d;font-weight:550;white-space:nowrap}.vr-tag.down{background:#fff0f2;color:#ba2d4d}.vr-tag.neutral{background:#f2f2f7;color:#676a78}
.vr-row{display:flex;align-items:center;justify-content:space-between;gap:9px;padding:10px 0;border-bottom:1px solid #f0f0f5}
.vr-ticker{font-size:12px;font-weight:650;color:#4b4b59}.vr-pattern{font-size:11px;color:#747681;max-width:180px;margin-top:4px;line-height:1.5}
.vr-empty{font-size:12px;color:#747681;padding:18px 0}.vr-small{font-size:11px;color:#747681;line-height:1.7}
.vr-confirm{margin:6px 0 15px}.vr-confirm-head{display:flex;justify-content:space-between;align-items:center;font-size:11px;color:#838392}.vr-confirm-head b{font-size:17px;font-weight:650;color:#f0254e}
.vr-track{height:5px;border-radius:20px;background:#f5f0f2;margin:9px 0}.vr-fill{height:100%;border-radius:20px;background:linear-gradient(90deg,#ff244e,#ff94ac)}
.st-key-confirm_card [data-testid="stVerticalBlock"],.st-key-signals_card [data-testid="stVerticalBlock"]{gap:.65rem}
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
    titles = {"Radar": "Radar <em>thị trường</em>", "Biểu đồ": "Đọc <em>diễn biến giá</em>",
              "Thống kê cảnh báo": "Tín hiệu &amp; <em>xác nhận</em>", "Chất lượng": "Kiểm tra <em>dữ liệu</em>", "Phương pháp": "Hiểu <em>phương pháp</em>"}
    descriptions = {"Radar": f"Một góc nhìn rõ ràng về mẫu hình nến của {count} cổ phiếu đang chọn.<br>Theo dõi tín hiệu mới và đối chiếu kết quả trong lịch sử.",
                    "Biểu đồ": "Quan sát giá, khối lượng và vị trí xuất hiện mẫu hình.<br>Chọn mã để đọc chi tiết từng phiên giao dịch.",
                    "Thống kê cảnh báo": "Từ cảnh báo hai nến đến mẫu hình được xác nhận.<br>Đối chiếu số quan sát, tỷ lệ hoàn thành và khoảng tin cậy.",
                    "Chất lượng": "Theo dõi các phiên thiếu, cảnh báo và nhật ký nạp.<br>Đọc số liệu cùng với chất lượng của nguồn dữ liệu.",
                    "Phương pháp": "Các định nghĩa và giới hạn của nghiên cứu.<br>Hiểu cách tín hiệu được nhận diện trước khi diễn giải kết quả."}
    st.markdown(f'<div class="vr-topbar"><div class="vr-crumb">Không gian nghiên cứu <span style="margin:0 8px;color:#d1d1d9">/</span> <b>{escape(page)}</b></div><div class="vr-source"><i></i>SSI &nbsp;·&nbsp; SQLite / Chỉ đọc</div></div>', unsafe_allow_html=True)
    st.markdown(f"""<div class="vr-hero"><div class="vr-hero-grid"><div><div class="vr-topline">VN30 CANDLESTICK RADAR</div><h1>{titles.get(page,titles["Radar"])}</h1><p>{descriptions.get(page,descriptions["Radar"])}</p></div>
    <div class="vr-hero-art" aria-hidden="true"><svg width="145" height="112" viewBox="0 0 145 112" fill="none"><circle cx="75" cy="56" r="48" stroke="#ff244e" stroke-opacity=".10"/><circle cx="75" cy="56" r="34" stroke="#ff244e" stroke-opacity=".10"/><path d="M20 90L47 68L74 75L109 32L132 20" stroke="#ff244e" stroke-opacity=".2" stroke-width="2" stroke-dasharray="4 5"/><path d="M37 49v36M67 36v42M97 20v48" stroke="#ff244e" stroke-width="2"/><rect x="29" y="60" width="16" height="16" rx="3" fill="#ff9ab1"/><rect x="59" y="46" width="16" height="23" rx="3" fill="#ff688d"/><rect x="89" y="29" width="16" height="27" rx="3" fill="#ff244e"/><circle cx="121" cy="24" r="4" fill="#ff244e"/></svg></div>
    <div class="vr-date"><small>Ngày phân tích</small><strong>{asof:%d.%m.%Y}</strong><span><i class="vr-dot"></i>Bản lưu đến {stored_last:%d/%m/%Y}</span></div></div></div>""", unsafe_allow_html=True)


def _style(fig, height):
    fig.update_layout(template="plotly_white", height=height, font={"family":"Inter, sans-serif","size":11,"color":"#90909f"},
        paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",margin={"l":6,"r":10,"t":10,"b":5},
        legend={"orientation":"h","y":1.04},hoverlabel={"bgcolor":"white","font":{"color":"#30303b"}})
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#f0f0f5",zeroline=False)
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
                st.markdown(f'<div class="vr-row"><div><div class="vr-ticker">{escape(row.symbol)}</div><div class="vr-pattern">{escape(description)}</div></div><span class="vr-tag {"down" if bias == {"bearish"} else "neutral" if bias == {"neutral"} else ""}">{label}</span></div>', unsafe_allow_html=True)
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
            fig = go.Figure(go.Scatter(x=activity.index,y=activity.values,mode="lines",fill="tozeroy",line={"color":ACCENT,"width":2},fillcolor="rgba(255,36,78,.09)",hovertemplate="%{x|%d/%m/%Y}: %{y} mã<extra></extra>"))
            fig.update_yaxes(title="Số mã có mẫu hình",rangemode="tozero",dtick=1 if activity.max()<=5 else None)
            st.plotly_chart(_style(fig,210),width="stretch",key="overview_activity")
            st.caption("Tối đa 30 phiên đến ngày quét, trong khoảng lịch sử hiển thị.")
    with second:
        with st.container(border=True, key="distribution_card"):
            st.subheader("Phân bố nhãn mẫu hình")
            counts = events.loc[events.kind == "pattern","bias"].value_counts()
            names={"bullish":"Hướng tăng","bearish":"Hướng giảm","neutral":"Trung tính"}
            colors={"bullish":"#159b7e","bearish":"#ed6b85","neutral":"#dfdfe9"}
            if counts.empty:
                st.info("Chưa có mẫu hình trong khoảng đang xem.")
            else:
                fig=go.Figure(go.Pie(labels=[names[k] for k in counts.index],values=counts.values,hole=.75,marker_colors=[colors[k] for k in counts.index],textinfo="none",hovertemplate="%{label}: %{value} nhãn<extra></extra>"))
                fig.update_layout(annotations=[{"text":f"<b>{int(counts.sum()):,}</b><br>nhãn","x":.5,"y":.5,"showarrow":False,"font":{"size":19,"color":"#41404f"}}])
                fig=_style(fig,210);fig.update_layout(legend={"orientation":"h","y":-.05,"x":.5,"xanchor":"center"})
                st.plotly_chart(fig,width="stretch",key="overview_distribution")
            st.caption("Phân loại theo định nghĩa mẫu hình; một phiên có thể mang nhiều nhãn.")
