"""Dashboard VN30: chỉ đọc SQLite, thống kê theo ngày quét và nhóm mã đang chọn."""
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
import os
import json

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from dotenv import load_dotenv

from data import db
from data.quality import last_closed_day
from analytics.radar import build_radar
from analytics.setup_probability import build_setup_outcomes, summarize_setups
from app.premium import apply_theme, sidebar_brand, hero, render_overview, sidebar_menu

from app.signal_workspace import render_signal_workspace, render_event_research

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
ACCENT, NAVY, GRAY, AMBER = '#ff244e', '#272833', '#9899a6', '#d4a145'
STATUS = {"completed": "Hoàn thành", "not_completed": "Không hoàn thành", "pending": "Chờ phiên kế tiếp",
          "missing_next_bar": "Thiếu nến kế tiếp", "invalid_next_bar": "Nến kế tiếp không hợp lệ"}
SOURCE_FILES = {"live": "storage/radar.db", "demo": "data_sample/radar_demo.db"}
SOURCE_LABELS = {"live": "Hằng ngày (Live)", "demo": "Demo báo cáo"}


def source_path(value):
    path = Path(value).expanduser()
    return (path if path.is_absolute() else ROOT / path).resolve()


def initial_source_mode():
    configured = st.session_state.get("db_path", os.getenv("RADAR_DB_PATH", "")).strip()
    if configured:
        for mode, relative in SOURCE_FILES.items():
            if source_path(configured) == source_path(relative):
                return mode
    return "live" if source_path(SOURCE_FILES["live"]).is_file() else "demo" if source_path(SOURCE_FILES["demo"]).is_file() else "live"


def change_source():
    mode = st.session_state["data_source_mode"]
    st.session_state["db_path"] = SOURCE_FILES[mode]
    st.session_state["_source_changed"] = True
    read_data.clear()
    analyze.clear()


def pct(value):
    return "—" if pd.isna(value) else f"{100 * value:.2f}%".replace(".", ",")


def chart_style(fig, height=360):
    fig.update_layout(template="plotly_white", height=height, font={"family": 'Inter, sans-serif', "color": NAVY},
        margin={"l": 15, "r": 20, "t": 25, "b": 25}, paper_bgcolor="rgba(0,0,0,0)",
        legend={"orientation": "h", "y": 1.15}, hoverlabel={"bgcolor": "white"})
    return fig


def dates_table(frame, columns):
    result = frame.copy()
    for column in columns:
        result[column] = pd.to_datetime(result[column]).dt.strftime("%d/%m/%Y").fillna("—")
    return result


def download(label, frame, filename, key):
    st.download_button(label, frame.to_csv(index=False).encode("utf-8-sig"), filename, "text/csv", key=key)


@st.cache_data(ttl=60, show_spinner=False)
def read_data(path, symbols, signature):
    with closing(db.connect_readonly(path)) as conn:
        conn.execute("BEGIN")
        frames = {symbol: db.load_ohlc(conn, symbol) for symbol in symbols}
        issues = pd.read_sql_query('SELECT symbol, trading_date, check_name AS "check", severity, detail FROM quality_issues', conn)
        logs = pd.read_sql_query("SELECT * FROM ingest_log WHERE id IN (SELECT MAX(id) FROM ingest_log GROUP BY symbol)", conn)
    return frames, issues, logs


@st.cache_data(show_spinner=False)
def analyze(frames, issues, asof):
    return build_radar(frames, asof, issues), build_setup_outcomes(frames, asof, issues)


def file_signature(path):
    try:
        stat=Path(path).stat();return stat.st_mtime_ns,stat.st_size
    except FileNotFoundError:return None


def sqlite_signature(path):
    return tuple(file_signature(item) for item in (Path(path),Path(str(path)+'-wal')))


@st.fragment(run_every=60)
def monitor_sqlite(path,signature,status_signature,track_status=True):
    if sqlite_signature(path)!=signature or (track_status and file_signature(ROOT/'report/update_logs/latest_status.json')!=status_signature):
        read_data.clear();analyze.clear();st.rerun(scope='app')


def main():
    st.set_page_config(page_title="VN30 Candlestick Radar", page_icon="📈", layout="wide")
    apply_theme()




    with st.sidebar:
        sidebar_brand()
        page = sidebar_menu()
        initial = initial_source_mode()
        if "data_source_mode" in st.session_state and st.session_state["data_source_mode"] not in SOURCE_FILES:
            st.session_state["data_source_mode"] = initial
        mode = st.radio("Chế độ dữ liệu", tuple(SOURCE_LABELS), index=tuple(SOURCE_LABELS).index(initial),
                        format_func=SOURCE_LABELS.__getitem__, key="data_source_mode", on_change=change_source)
        st.session_state["db_path"] = SOURCE_FILES[mode]
        with st.expander("Nguồn dữ liệu", expanded=False):
            entered = st.text_input("File SQLite", key="db_path", disabled=True)
            if mode == "demo":
                st.caption("Bản dữ liệu cố định để xem demo và đối chiếu báo cáo.")
            else:
                st.caption("Phiên đã đóng gần nhất đã lưu. Giá được nạp theo lịch cập nhật SSI.")
        path = source_path(entered)
        is_demo = path == source_path(SOURCE_FILES["demo"])
        if st.button('Đọc lại SQLite', width='stretch', key='reload_sqlite', icon=':material/refresh:'):
            read_data.clear()
            analyze.clear()
    try:
        text = (ROOT / "src/data/universe_vn30.txt").read_text(encoding="utf-8-sig")
        universe = list(dict.fromkeys(line.split("#", 1)[0].strip().upper() for line in text.splitlines()))
        universe = [symbol for symbol in universe if symbol]
        if not universe or any(not symbol.isalnum() for symbol in universe):
            raise ValueError("Danh sách mã trống hoặc không hợp lệ")
        signature = sqlite_signature(path)
        with st.spinner("Đang đọc dữ liệu lưu..."):
            frames, issues, logs = read_data(str(path.resolve()), tuple(universe), signature)
    except Exception as exc:
        st.error(f"Không đọc được dữ liệu: {exc}")
        if mode == "live":
            st.info("Chưa đọc được DB hằng ngày. Có thể chọn Demo báo cáo nếu đã có dữ liệu mẫu; hoặc nạp SSI vào storage/radar.db.")
        else:
            st.info("Chưa đọc được DB demo. Kiểm tra data_sample/radar_demo.db hoặc chọn Hằng ngày (Live).")
        return
    available = [frame for frame in frames.values() if not frame.empty]
    if not available:
        st.warning("SQLite chưa có nến cho các mã trong danh sách nghiên cứu.")
        return
    now = datetime.now(db.VN)
    closed = last_closed_day(now)
    closed_frames=[frame.loc[frame.index<=closed] for frame in available]
    closed_frames=[frame for frame in closed_frames if not frame.empty]
    if not closed_frames:
        st.warning("Chưa có nến đã đóng để phân tích.")
        return
    first=min(frame.index.min() for frame in closed_frames)
    stored_last=max(frame.index.max() for frame in closed_frames);last=stored_last
    previous=st.session_state.get('_scan_source',{})
    current=st.session_state.get('asof')
    identity=str(path.resolve())
    changed_db=previous.get('db') not in (None,identity)
    invalid=current is not None and not first<=pd.Timestamp(current)<=last
    followed_latest=(current is not None and previous.get('last') is not None
                     and pd.Timestamp(current)==pd.Timestamp(previous['last'])
                     and last>pd.Timestamp(previous['last']))
    source_changed=st.session_state.pop('_source_changed',False)
    if source_changed or changed_db or invalid or followed_latest:st.session_state['asof']=last.date()
    st.session_state['_scan_source']={'db':identity,'last':last.date()}
    with st.sidebar:
        st.caption(f"{'Demo báo cáo' if is_demo else SOURCE_LABELS[mode]} · Dữ liệu đến {stored_last:%d/%m/%Y}")
        monitor_sqlite(str(path),signature,file_signature(ROOT/'report/update_logs/latest_status.json'),track_status=not is_demo)
        status_file=ROOT/'report/update_logs/latest_status.json'
        if status_file.exists():
            try:
                status=json.loads(status_file.read_text(encoding='utf-8'))
                same_db=os.path.normcase(str(Path(status.get('db_path','')).resolve()))==os.path.normcase(identity)
                if same_db and status.get('state')=='failed':
                    st.warning('Lần cập nhật gần nhất thất bại. Xem log trong report/update_logs; dữ liệu đang hiển thị có thể là bản cũ.')
                elif same_db and status.get('state')=='running':
                    st.caption('Trạng thái ghi nhận gần nhất: bắt đầu nạp '+status.get('started_at','')+'; chưa ghi nhận hoàn tất.')
                elif same_db and status.get('freshness')=='unconfirmed':
                    st.caption('Lần nạp đã kết thúc nhưng chưa xác nhận đủ mốc ngày thường đã đóng. Kiểm tra từng mã và lịch nghỉ.')
            except (OSError,ValueError,TypeError):
                st.caption('Không đọc được trạng thái cập nhật; có thể đối chiếu log trong report/update_logs.')
        if st.button('Về phiên gần nhất',key='latest_session',width='stretch'):
            st.session_state['asof']=last.date()
        asof = pd.Timestamp(st.date_input("Ngày quét", last.date(), min_value=first.date(), max_value=last.date(), key="asof"))
        with st.expander("Nhóm cổ phiếu", expanded=False):
            selected = st.multiselect("Cổ phiếu", universe, default=universe, key="symbols")
        st.caption(f"{len(selected)}/{len(universe)} mã được chọn")
        days = st.selectbox("Biểu đồ & lịch sử", [90, 180, 365, 730], index=1,
                            format_func=lambda value: f"{value} ngày lịch", key="chart_days")
        st.caption("Nến hôm nay chỉ xem được sau 15:00 giờ Việt Nam.")
    if not selected:
        st.info("Chọn ít nhất một cổ phiếu để xem dashboard.")
        return
    with st.spinner("Đang tính tín hiệu và thống kê theo ngày quét..."):
        radar, all_outcomes = analyze(frames, issues, asof)
    start = asof - pd.Timedelta(days=days)
    latest = radar.latest[radar.latest.symbol.isin(selected)].copy()
    events = radar.events[radar.events.symbol.isin(selected) & (radar.events.date >= start)].copy()
    current = events[events.date == asof]
    selected_logs = logs[logs.symbol.isin(selected)]
    q = issues[issues.symbol.isin(selected)].copy()
    missing = radar.missing_sessions[radar.missing_sessions.symbol.isin(selected)].copy()
    inferred = missing.rename(columns={"date": "trading_date"}).assign(check="missing_session", severity="warning")
    q = pd.concat([q, inferred], ignore_index=True)
    q["trading_date"] = pd.to_datetime(q.trading_date)
    q = q[q.trading_date <= asof].drop_duplicates(["symbol", "trading_date", "check"])
    hero(asof, stored_last, len(selected), page=page)
    meta = f"DB lưu đến {stored_last:%d/%m/%Y} · Cách hôm nay {max(0, (pd.Timestamp(now.date()) - stored_last).days)} ngày lịch"
    if not selected_logs.empty:
        meta += f" · Lần nạp gần nhất của nhóm: {selected_logs.run_at.max()} (UTC+7)"
    st.caption(f"{'Demo báo cáo' if is_demo else SOURCE_LABELS[mode]} · {meta}")
    if is_demo:
        st.info(f"Đang xem demo cố định đến {stored_last:%d/%m/%Y}. Chọn Hằng ngày (Live) để theo dõi phiên mới nhất đã lưu; demo giữ nguyên dữ liệu của báo cáo.")
    elif stored_last<closed:
        st.info(f'DB đang có nến đến {stored_last:%d/%m/%Y}; mốc ngày thường đã đóng là {closed:%d/%m/%Y} (chưa trừ nghỉ lễ). Kiểm tra lịch nghỉ và log cập nhật nếu dữ liệu vẫn cũ. “Đọc lại SQLite” chỉ đọc dữ liệu đã lưu.')
    with st.expander('Ngày dữ liệu cuối của từng mã'):
        rows=[]
        for symbol,frame in frames.items():
            known=frame.index[frame.index<=closed]
            day=known.max() if len(known) else pd.NaT
            label='Chưa có nến đã đóng' if pd.isna(day) else 'Chậm hơn mã mới nhất' if day<stored_last else 'Có bản ghi ngày mới nhất'
            rows.append((symbol,day,label))
        st.dataframe(dates_table(pd.DataFrame(rows,columns=['Mã','Ngày cuối đã đóng','Trạng thái lưu']),['Ngày cuối đã đóng']),hide_index=True,width='stretch')
        st.caption('Ngày lưu không thay thế kiểm tra chất lượng giá/khối lượng. Bảng này không bị ẩn bởi bộ lọc chỉ xem tín hiệu.')
    future=[(symbol,day) for symbol,frame in frames.items() for day in frame.index[frame.index>closed]]
    if future:
        st.warning(f'Đang ẩn {len(future)} nến chưa đóng hoặc tương lai sau mốc {closed:%d/%m/%Y}. Các nến này không được phân tích.')
        with st.expander('Xem nến sau mốc đóng cửa đang bị ẩn'):
            st.dataframe(dates_table(pd.DataFrame(future,columns=['Mã','Ngày']),['Ngày']),hide_index=True,width='stretch')
    if page == 'Radar':
        n_pat = current.loc[current.kind == "pattern", "symbol"].nunique()
        n_set = current.loc[current.kind == "setup", "symbol"].nunique()
        n_warn = int(q.severity.isin(["error", "warning"]).sum())
        metrics = st.columns([1.3, 1, 1, 1])
        with metrics[0], st.container(key="kpi_hi"):
            st.metric("Mã có tín hiệu hôm nay", f"{current.symbol.nunique()}/{len(selected)}")
        metrics[0].markdown(f'<div class="vr-kpi-note">{n_pat} mã có mẫu hình · {n_set} mã có cảnh báo sớm</div>', unsafe_allow_html=True)
        metrics[1].metric("Cảnh báo sớm", n_set, help="Mã đã có hai nến đầu của Sao mai/Sao hôm, chờ nến thứ ba.")
        metrics[2].metric("Mã đủ dữ liệu", f"{latest.status.eq('Đã quét').sum()}/{len(selected)}")
        metrics[3].metric("Lưu ý dữ liệu lịch sử", n_warn, help="Số cảnh báo chất lượng dữ liệu trong lịch sử, không phải điểm rủi ro cổ phiếu. Xem chi tiết ở trang Chất lượng.")
    if latest.status.ne("Đã quét").any():
        st.warning("Có mã thiếu nến ngày chọn hoặc chưa đủ cửa sổ liên tiếp. Xem cột Trạng thái trong radar.")
    if not selected_logs.empty and selected_logs.status.eq("failed").any():
        st.warning("Có mã nạp thất bại ở lần gần nhất; số liệu đang xem có thể là bản lưu trước đó.")

    pass
    if page == 'Radar':  # Giữ chú thích của trang Radar
        render_signal_workspace(frames, events, asof, selected, radar.market_days, ROOT, issues,
                                setup_summary=summarize_setups(all_outcomes[all_outcomes.symbol.isin(selected)]))
        render_overview(frames, latest, events, current, all_outcomes, selected, asof, start, radar.market_days)
        st.subheader("Bảng quét toàn bộ nhóm mã")
        signals_only = st.checkbox("Chỉ hiện mã có mẫu hình hoặc cảnh báo", value=True, key="signals_only")
        table = latest.copy()
        if signals_only:
            table = table[table.patterns.ne("") | table.setups.ne("")]
        display = dates_table(table, ["data_date"]).rename(columns={"symbol": "Mã", "status": "Trạng thái", "patterns": "Mẫu hình",
            "setups": "Chờ xác nhận", "data_date": "Ngày nến cuối", "close": "Đóng cửa", "change_pct": "Thay đổi (%)", "volume": "Khối lượng"})
        display = display[["Mã", "Mẫu hình", "Chờ xác nhận", "Ngày nến cuối", "Đóng cửa", "Thay đổi (%)", "Khối lượng"]]
        st.caption(f"Đang hiện {len(display)}/{len(selected)} mã. Ngày không có tín hiệu là một kết quả hợp lệ.")
        st.dataframe(display, hide_index=True, width="stretch", column_config={
            "Đóng cửa": st.column_config.NumberColumn(format="localized"), "Thay đổi (%)": st.column_config.NumberColumn(format="%+.2f"),
            "Khối lượng": st.column_config.NumberColumn(format="localized")})
        download("Tải bảng đang xem", display, f"radar_{asof:%Y%m%d}.csv", "radar_csv")
        st.subheader("Mẫu hình xuất hiện trong lịch sử")
        counts = events.loc[events.kind == "pattern"].groupby("name_vi").size().sort_values()
        if counts.empty:
            st.info("Chưa có mẫu hình phù hợp trong khoảng đang xem.")
        else:
            figure = go.Figure(go.Bar(x=counts.values, y=counts.index, orientation="h", marker_color=ACCENT))
            figure.update_xaxes(title="Số nhãn mẫu hình")
            st.plotly_chart(chart_style(figure, max(340, len(counts) * 26)), width="stretch")
        st.caption("Một phiên có thể mang nhiều nhãn, ví dụ Doji và Doji bia mộ. Số nhãn không phải số sự kiện độc lập.")

    if page == 'Biểu đồ':
        symbol = st.selectbox("Mã xem biểu đồ", selected, key="chart_symbol")
        frame = frames[symbol].loc[lambda f: (f.index >= start) & (f.index <= asof)]
        history = events[events.symbol == symbol]
        if frame.empty:
            st.info("Mã này chưa có nến trong khoảng đang xem.")
        else:
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.76, 0.24])
            fig.add_trace(go.Candlestick(x=frame.index, open=frame.open, high=frame.high, low=frame.low, close=frame.close,
                name=symbol, increasing_line_color='#0b8a66', decreasing_line_color="#d9304e"), row=1, col=1)
            fig.add_trace(go.Bar(x=frame.index, y=frame.volume, name="Khối lượng", marker_color=GRAY), row=2, col=1)
            for kind, group in history.groupby("kind"):
                fig.add_trace(go.Scatter(x=group.date, y=frame.loc[group.date, "close"].to_numpy(), mode="markers", text=group.name_vi,
                    name="Chờ xác nhận" if kind == "setup" else "Mẫu hình", marker={"size": 8, "symbol": "diamond-open" if kind == "setup" else "circle", "color": AMBER if kind == "setup" else "#4263eb"},
                    hovertemplate="%{x|%d/%m/%Y}<br>%{text}<extra></extra>"), row=1, col=1)
            fig.update_layout(xaxis_rangeslider_visible=False)
            fig.update_yaxes(title_text="Giá SSI (đồng)", row=1, col=1)
            fig.update_yaxes(title_text="Cổ phiếu", row=2, col=1)
            st.plotly_chart(chart_style(fig, 610), width="stretch")
        detail = dates_table(history.sort_values("date", ascending=False), ["date"])
        detail["kind"] = detail.kind.map({"pattern": "Mẫu hình", "setup": "Chờ xác nhận"})
        detail["bias"] = detail.bias.map({"bullish": "Hướng tăng", "bearish": "Hướng giảm", "neutral": "Trung tính"})
        detail = detail[["date", "name_vi", "bias", "kind", "confirmation"]].rename(columns={"date": "Ngày", "name_vi": "Mẫu hình", "bias": "Hướng lý thuyết", "kind": "Loại", "confirmation": "Điều kiện xác nhận"})
        st.dataframe(detail, hide_index=True, width="stretch")
        download("Tải lịch sử mã", detail, f"signals_{symbol}_{asof:%Y%m%d}.csv", "symbol_csv")

    if page == 'Kết quả nghiên cứu':
        render_event_research(frames, events, asof, issues)
        st.subheader("Xác suất hoàn thành trong lịch sử")
        scope = st.radio("Phạm vi thống kê", ["Toàn bộ lịch sử", "Theo khoảng hiển thị"], horizontal=True, key="stats_scope")
        outcomes = all_outcomes[all_outcomes.symbol.isin(selected)].copy()
        if scope == "Theo khoảng hiển thị":
            outcomes = outcomes[pd.to_datetime(outcomes.setup_date) >= start]
        summary = summarize_setups(outcomes)
        st.caption(f"Nhóm {len(selected)} mã · Chỉ dùng dữ liệu đến {asof:%d/%m/%Y} · Thống kê theo ngày xuất hiện cảnh báo.")
        for column, row in zip(st.columns(2), summary.itertuples(index=False)):
            with column:
                st.metric(f"{row.name_vi} · tỷ lệ hoàn thành", pct(row.probability))
                st.caption(f"{row.n_completed}/{row.n_evaluated} cảnh báo được xác nhận · Wilson 95%: {pct(row.ci_low)} – {pct(row.ci_high)}")
        st.caption(f"Tổng {int(summary.n_total.sum())} cảnh báo · Đã đánh giá {int(summary.n_evaluated.sum())} · Chờ phiên kế tiếp {int(summary.n_pending.sum())} · Loại do thiếu/lỗi nến kế tiếp {int(summary.n_excluded.sum())}.")
        if outcomes.empty:
            st.info("Chưa có cảnh báo phù hợp. Tỷ lệ được để trống vì chưa có quan sát để đánh giá.")
        left, right = st.columns(2)
        with left:
            st.markdown("**Số lần hoàn thành và không hoàn thành**")
            fig = go.Figure()
            fig.add_bar(y=summary.name_vi, x=summary.n_completed, orientation="h", name="Hoàn thành", marker_color=ACCENT)
            fig.add_bar(y=summary.name_vi, x=summary.n_evaluated - summary.n_completed, orientation="h", name="Không hoàn thành", marker_color="#cbd5e1")
            fig.update_layout(barmode="stack")
            fig.update_xaxes(title="Số cảnh báo đã có đủ dữ liệu đánh giá")
            st.plotly_chart(chart_style(fig, 270), width="stretch")
        with right:
            st.markdown("**Tỷ lệ và khoảng tin cậy Wilson 95%**")
            valid = summary[summary.probability.notna()]
            fig = go.Figure(go.Scatter(x=valid.probability * 100, y=valid.name_vi, mode="markers", marker={"size": 11, "color": ACCENT},
                error_x={"type": "data", "symmetric": False, "array": (valid.ci_high - valid.probability) * 100,
                         "arrayminus": (valid.probability - valid.ci_low) * 100, "color": ACCENT},
                hovertemplate="%{y}: %{x:.2f}%<extra></extra>"))
            upper = max(20, min(100, float(valid.ci_high.max()) * 110)) if not valid.empty else 20
            fig.update_xaxes(range=[0, upper], title="Tỷ lệ hoàn thành (%)")
            st.plotly_chart(chart_style(fig, 270), width="stretch")
        st.info("Hoàn thành nghĩa là mẫu hình ba nến xuất hiện ở đúng phiên thị trường kế tiếp. Đây chưa phải xác suất có lãi. Wilson là khoảng mô tả ban đầu; các quan sát có thể phụ thuộc nhau.")
        with st.expander("Bảng tổng hợp và tải CSV"):
            view = summary.copy()
            for name in ("probability", "ci_low", "ci_high"):
                view[name] = view[name].map(pct)
            view = view.drop(columns="setup").rename(columns={"name_vi": "Cảnh báo", "n_total": "Tổng", "n_evaluated": "Đủ dữ liệu", "n_completed": "Hoàn thành",
                "n_pending": "Chờ", "n_excluded": "Loại", "probability": "Tỷ lệ", "ci_low": "CI dưới", "ci_high": "CI trên"})
            st.dataframe(view, hide_index=True, width="stretch")
            download("Tải thống kê CSV", summary, f"setup_probability_{asof:%Y%m%d}.csv", "probability_csv")
            download("Tải toàn bộ cảnh báo trong phạm vi", outcomes, f"setup_outcomes_{asof:%Y%m%d}.csv", "outcomes_csv")
        st.markdown("**Tra cứu từng lần cảnh báo**")
        setup_filter = st.selectbox("Loại cảnh báo", ["Tất cả", "Sao mai", "Sao hôm"], key="setup_filter")
        status_filter = st.selectbox("Kết quả xác nhận", ["Tất cả", *STATUS.values()], key="outcome_filter")
        history = outcomes.copy()
        history["Loại"] = history.setup.map({"morning_star_setup": "Sao mai", "evening_star_setup": "Sao hôm"})
        history["Kết quả"] = history.status.map(STATUS)
        if setup_filter != "Tất cả": history = history[history["Loại"] == setup_filter]
        if status_filter != "Tất cả": history = history[history["Kết quả"] == status_filter]
        history = dates_table(history.sort_values("setup_date", ascending=False), ["setup_date", "next_date"])
        history = history.rename(columns={"symbol": "Mã", "setup_date": "Ngày cảnh báo", "next_date": "Phiên kế tiếp"})
        st.dataframe(history[["Mã", "Loại", "Ngày cảnh báo", "Phiên kế tiếp", "Kết quả"]], hide_index=True, width="stretch", height=300)
        st.caption("Bộ lọc tra cứu chỉ thay đổi bảng chi tiết. Hai tỷ lệ phía trên dùng toàn bộ phạm vi thống kê đã chọn.")

    if page == 'Chất lượng':
        st.subheader("Chất lượng dữ liệu")
        st.caption("Các mục dưới đây thuộc lịch sử đến ngày phân tích; số cảnh báo không phải điểm rủi ro hay số lỗi độc lập.")
        severity = st.selectbox("Mức độ", ["Tất cả", "error", "warning", "info"], key="severity")
        visible = q if severity == "Tất cả" else q[q.severity == severity]
        st.markdown("**Tóm tắt theo mã và loại kiểm tra**")
        quality_summary = (visible.groupby(["symbol", "check", "severity"]).size().reset_index(name="Số lần")
                           .rename(columns={"symbol": "Mã", "check": "Loại kiểm tra", "severity": "Mức độ"}).sort_values("Số lần", ascending=False))
        st.dataframe(quality_summary, hide_index=True, width="stretch")
        with st.expander("Chi tiết từng dòng"):
            st.dataframe(dates_table(visible.sort_values(["symbol", "trading_date"]), ["trading_date"]), hide_index=True, width="stretch")
        download("Tải bảng đối chiếu", visible, f"quality_{asof:%Y%m%d}.csv", "quality_csv")
        with st.expander("Cách đọc các cảnh báo đang có"):
            st.write("Khoảng trống BSR tháng 01/2025 và MCH tháng 12/2025 liên quan chuyển sàn. Radar loại cửa sổ nhận diện đi qua khoảng thiếu; không tạo nến để lấp khoảng trống.")
            st.write("Một số summary VPL ngoài phạm vi OHLC có giá và khối lượng bằng 0. MCH ngày 05/10/2022 cần được đối chiếu thêm.")
            st.write("Kiểm tra biên độ mặc định 7% chưa mô tả đầy đủ lịch sử UPCoM, các phiên giao dịch đầu tiên và giá tham chiếu. Cần phân loại theo thời kỳ khi nghiên cứu sâu hơn.")
        st.markdown("**Nhật ký lần nạp gần nhất của từng mã**")
        st.caption("Đây là metadata hiện tại của DB, kể cả khi đang xem một ngày lịch sử.")
        if selected_logs.empty:
            if is_demo:
                st.info("DB demo đã loại nhật ký vận hành khi đóng gói. Xem nguồn và thời gian chuẩn bị trong data_sample/metadata.json.")
            else:
                st.info("DB này chưa có nhật ký nạp của các mã đang chọn. Kiểm tra đúng nguồn dữ liệu hoặc chạy ingest cho DB làm việc.")
        else:
            st.dataframe(selected_logs, hide_index=True, width="stretch")

    if page == 'Phương pháp':
        st.subheader("Phương pháp và giới hạn")
        st.markdown("""
- Nhận diện 19 mẫu hình và hai cảnh báo Sao mai/Sao hôm theo ngưỡng đã định nghĩa trong lớp tài chính.
- Ngưỡng thân/biên độ dùng các nến trước; xu hướng được đo trước khi mẫu hình bắt đầu.
- Nhận diện trên toàn bộ lịch sử đến ngày quét rồi mới cắt khoảng hiển thị. Thống kê được tính lại theo ngày quét, không đọc một CSV tổng hợp cố định.
- Không phát tín hiệu khi cửa sổ cần dùng thiếu phiên theo lịch ước lượng hoặc chứa nến lỗi đã biết. Lịch ước lượng có thể bỏ sót ngày thiếu ở toàn bộ nhóm mã.
- Cảnh báo chưa có phiên tiếp theo và cảnh báo thiếu/lỗi nến xác nhận được tách khỏi mẫu số đánh giá.
- Giá là chuỗi SSI đang lưu, có thể đã điều chỉnh lịch sử. Rổ nghiên cứu chưa tái dựng thành phần VN30 theo từng ngày quá khứ.
- Lợi suất 1/3/5/10/20 phiên có kiểm định bootstrap/BY; đánh giá ngoài mẫu theo thời gian chạy bằng scripts/run_study.py --oos, mức nền chỉ fit trên train. Tỷ lệ hoàn thành mẫu hình chưa chứng minh hiệu quả giao dịch.

**Công cụ phân tích học thuật, không phải khuyến nghị đầu tư. Không có chức năng đặt lệnh.**
""")


if __name__ == "__main__":
    main()
