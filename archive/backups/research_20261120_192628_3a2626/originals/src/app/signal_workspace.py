"""Chi tiết tín hiệu và nghiên cứu lợi suất; UI độc lập với nhận diện mẫu hình."""
import json
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from finance.context import signal_context
from analytics.event_study import event_outcomes, summarize_events

LABELS={'bullish':'Hướng tăng','bearish':'Hướng giảm','neutral':'Trung tính'}


@st.cache_data(show_spinner=False)
def enrich(frames, events, asof, market_days):
    rows=[]
    for _,event in events.iterrows():
        row=event.to_dict()
        row.update(signal_context(frames[event.symbol],row,asof,market_days))
        rows.append(row)
    return pd.DataFrame(rows)


def render_signal_workspace(frames, events, asof, selected, market_days, root, issues=None):
    with st.expander('Kịch bản xử lý & bối cảnh tín hiệu',expanded=True):
        st.caption('Quy tắc theo dõi học thuật, cần xác nhận bằng giá. Các mức dưới đây chưa được kiểm định như một chiến lược giao dịch.')
        prefs=root/'storage/preferences/watchlist.json'
        saved=[]
        if prefs.exists():
            try: saved=json.loads(prefs.read_text(encoding='utf-8'))
            except (ValueError,OSError): st.warning('Không đọc được danh sách đã lưu. Có thể chọn lại và lưu.')
        watch=st.multiselect('Danh sách quan tâm',selected,default=[s for s in saved if s in selected],key='watch_symbols')
        if st.button('Lưu danh sách quan tâm',key='save_watchlist'):
            try:
                prefs.parent.mkdir(parents=True,exist_ok=True)
                temp=prefs.with_suffix('.tmp');temp.write_text(json.dumps(watch,ensure_ascii=False),encoding='utf-8');temp.replace(prefs)
                st.success('Đã lưu danh sách vào storage/preferences/watchlist.json')
            except OSError as exc: st.error(f'Không lưu được danh sách: {exc}')
        only_watch=st.checkbox('Chỉ xem danh sách quan tâm',key='watch_only')
        scope=st.radio('Phạm vi tín hiệu',['Ngày quét','Lịch sử trong khoảng hiển thị'],horizontal=True,key='signal_scope')
        view=events[events.date==asof] if scope=='Ngày quét' else events
        if only_watch: view=view[view.symbol.isin(watch)]
        if view.empty:
            st.info('Không có tín hiệu phù hợp. Chọn lịch sử hoặc điều chỉnh danh sách quan tâm.');return
        enriched=enrich(frames,view,asof,tuple(market_days))
        direction=st.multiselect('Hướng lý thuyết',list(LABELS.values()),default=list(LABELS.values()),key='signal_direction')
        state=st.selectbox('Trạng thái xác nhận',['Tất cả',*sorted(enriched.status.unique())],key='signal_status')
        volume=st.checkbox('Khối lượng ≥ 1,2 lần trung bình 20 phiên trước',key='signal_volume')
        enriched=enriched[enriched.bias.map(LABELS).isin(direction)]
        if state!='Tất cả': enriched=enriched[enriched.status==state]
        if volume: enriched=enriched[enriched.volume_ratio>=1.2]
        if enriched.empty: st.info('Không có tín hiệu đáp ứng bộ lọc.');return
        enriched=enriched.sort_values(['date','symbol'],ascending=[False,True]).reset_index(drop=True)
        st.download_button('Tải danh sách tín hiệu đã lọc',enriched.to_csv(index=False).encode('utf-8-sig'),'signal_scenarios.csv','text/csv',key='scenario_csv')
        index=st.selectbox('Chọn tín hiệu',range(len(enriched)),format_func=lambda i:f"{enriched.iloc[i].symbol} · {enriched.iloc[i].date:%d/%m/%Y} · {enriched.iloc[i].name_vi}",key='scenario_index')
        r=enriched.iloc[index]
        number=lambda x:'Chưa đủ dữ liệu' if pd.isna(x) else f'{x:,.2f}'
        st.markdown(f'**{r.symbol} · {r.name_vi} · {LABELS[r.bias]}**')
        st.write('Trạng thái:',r.status)
        st.write('Theo dõi:',r.follow)
        st.write('Mức vô hiệu tham khảo:',number(r.invalidation) if r.bias!='neutral' else 'Chưa có hướng; theo dõi cả đỉnh và đáy.')
        context=pd.DataFrame([
            ['Xu hướng 5 phiên trước mẫu hình',number(r.trend_pct)+' %'],
            ['EMA20 tại ngày tín hiệu',number(r.ema20)],['EMA50 tại ngày tín hiệu',number(r.ema50)],
            ['Giá so với EMA20', 'Chưa đủ dữ liệu' if pd.isna(r.ema20) else 'Trên EMA20' if r.close>r.ema20 else 'Không vượt EMA20'],
            ['Khối lượng / TB20 phiên trước',number(r.volume_ratio)+' lần'],
            ['Hỗ trợ: đáy 20 phiên trước',number(r.support)],['Kháng cự: đỉnh 20 phiên trước',number(r.resistance)]],columns=['Bối cảnh','Giá trị'])
        st.dataframe(context,hide_index=True,width='stretch')
        st.caption('Hỗ trợ/kháng cự là cực trị 20 phiên trước, chưa phải vùng giá đã xác nhận. Bối cảnh được tính tại ngày tín hiệu; trạng thái chỉ đối chiếu đúng phiên thị trường kế tiếp đã biết đến ngày quét.')
        f=frames[r.symbol].loc[lambda x:x.index<=asof].copy()
        f['ema20']=f.close.ewm(span=20,adjust=False,min_periods=20).mean()
        f['ema50']=f.close.ewm(span=50,adjust=False,min_periods=50).mean()
        f=f.loc[f.index>=pd.Timestamp(r.date)-pd.Timedelta(days=90)]
        fig=go.Figure(go.Candlestick(x=f.index,open=f.open,high=f.high,low=f.low,close=f.close,name=r.symbol,increasing_line_color='#159b7e',decreasing_line_color='#f05270'))
        for name,color in [('ema20','#6d67df'),('ema50','#e6a23c')]: fig.add_scatter(x=f.index,y=f[name],name=name.upper(),mode='lines',line={'color':color,'width':1})
        fig.add_hline(y=r.high,line_dash='dash',line_color='#159b7e',annotation_text='Đỉnh nến tín hiệu')
        fig.add_hline(y=r.low,line_dash='dash',line_color='#ff244e',annotation_text='Đáy nến tín hiệu')
        if r.bias!='neutral':
            level=r.invalidation
            fig.add_hrect(y0=level*.995,y1=level*1.005,fillcolor='#ff244e',opacity=.07,line_width=0)
        fig.add_scatter(x=[r.date],y=[r.close],mode='markers',name='Tín hiệu đang chọn',marker={'size':12,'color':'#ff244e','symbol':'diamond'})
        fig.update_layout(height=420,xaxis_rangeslider_visible=False,template='plotly_white',font={'family':'Inter'},legend={'orientation':'h'},margin={'t':25,'b':20})
        st.plotly_chart(fig,width='stretch',key='scenario_chart')
        st.caption('Dải tô là vùng ±0,5% quanh mức vô hiệu để dễ nhìn; chưa phải biên dừng lỗ tối ưu. Với setup Sao mai/Sao hôm, dùng điều kiện xác nhận ghi trong thẻ, không dùng quy tắc vượt đỉnh/đáy chung.')
        if st.checkbox('Tính thống kê lịch sử của mẫu hình này', key='selected_research'):
            if r['kind']=='setup':
                st.info('Cảnh báo hai nến: xem tỷ lệ hoàn thành Sao mai/Sao hôm trong mục Thống kê cảnh báo.')
            else:
                _, selected_summary=research(frames,events[events['name']==r['name']],asof,issues,20)
                st.dataframe(selected_summary,hide_index=True,width='stretch')
                st.caption('Phạm vi: nhóm mã và khoảng hiển thị đang chọn, đến ngày quét; phí hai chiều mặc định 20 bps. Quy tắc xác nhận chung trong thẻ chưa được kiểm định riêng.')



@st.cache_data(show_spinner=False)
def research(frames,events,asof,issues,fee):
    result=event_outcomes(frames,events,asof,issues,fee_bps=fee)
    return result,summarize_events(result)


def render_event_research(frames,events,asof,issues):
    with st.expander('Hiệu quả sau tín hiệu · 5 / 10 / 20 phiên',expanded=True):
        fee=st.number_input('Tổng phí hai chiều giả định (bps)',min_value=0,max_value=500,value=20,step=5,key='event_fee')
        st.caption('20 bps = 0,20% hai chiều. Vào tại mở cửa phiên kế tiếp, thoát tại đóng cửa phiên thứ 5/10/20 kể từ lúc vào; phí chia đều cho hai chiều. Chỉ dùng dữ liệu đến ngày quét và các tín hiệu trong khoảng hiển thị.')
        with st.spinner('Đang tính lợi suất sau tín hiệu...'):
            result,summary=research(frames,events,asof,issues,fee)
        if summary.empty: st.info('Chưa có mẫu hình để thống kê.');return
        st.dataframe(summary,hide_index=True,width='stretch')
        st.download_button('Tải nghiên cứu lợi suất CSV',summary.to_csv(index=False).encode('utf-8-sig'),'event_summary.csv','text/csv',key='event_summary_csv')
        st.download_button('Tải từng quan sát lợi suất',result.to_csv(index=False).encode('utf-8-sig'),'event_outcomes.csv','text/csv',key='event_rows_csv')
        st.info('Lợi suất long sau phí là giả định cho mọi nhãn, không phải gợi ý mua khi có mẫu hình giảm. Bất lợi đo đáy thấp nhất so với giá vào, không phải drawdown danh mục. Chưa mô phỏng trượt giá, thanh khoản hoặc khớp lệnh khi khóa trần/sàn; chưa đánh giá ngoài mẫu.')
        st.caption('Kiểm định thăm dò: trừ lợi suất nền long cùng mã/kỳ hạn từ toàn bộ cửa sổ hợp lệ đến ngày quét; lấy trung bình theo ngày tín hiệu. Bootstrap vòng tròn theo khối 20 ngày có tín hiệu, 1.000 lần; p dùng phân phối bootstrap đã trừ trung bình, q hiệu chỉnh Benjamini–Yekutieli trên các mẫu hình × kỳ hạn đang hiển thị. Chỉ tính CI/p khi có ≥30 nhãn và ≥20 ngày. Lựa chọn khối và tính dừng ảnh hưởng kết quả; chưa đủ để kết luận hiệu quả giao dịch.')
