"""Chi tiết tín hiệu và nghiên cứu lợi suất; UI độc lập với nhận diện mẫu hình."""
import json
from html import escape
import hashlib
import os
import tempfile
import time
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from finance.context import signal_context, history_at
from analytics.event_study import event_outcomes, summarize_events
from analytics.radar import build_radar, infer_market_days
from analytics.study import q1_tables, training_fingerprint

LABELS={'bullish':'Hướng tăng','bearish':'Hướng giảm','neutral':'Trung tính'}


def save_watchlist(path,values):
    """Ghi nguyên tử; thử lại có giới hạn khi Windows tạm khóa thao tác replace."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,suffix='.tmp',delete=False) as handle:
            temp=Path(handle.name);json.dump(list(dict.fromkeys(values)),handle,ensure_ascii=False)
        # File tạm phải đóng trước replace. Windows còn có thể từ chối khi
        # một luồng/tiến trình khác đang dùng file đích mà không share-delete.
        # Giữ file cũ nguyên vẹn; không dùng unlink(path) rồi ghi lại.
        for attempt in range(10):
            try:
                os.replace(temp,path)
                break
            except PermissionError as exc:
                if getattr(exc,'winerror',None) not in (5,32,33) or attempt==9:
                    raise
                time.sleep(min(0.01 * 2**attempt,0.1))
    finally:
        if temp is not None:temp.unlink(missing_ok=True)


EXPLANATIONS={
    'doji':'Giá mở cửa và đóng cửa gần nhau. Hai bên mua bán chưa thể hiện ưu thế rõ trong phiên.',
    'dragonfly_doji':'Giá từng xuống thấp rồi quay lên gần mức mở cửa. Trong đồ án, mẫu này vẫn được xếp là chưa rõ hướng.',
    'gravestone_doji':'Giá từng lên cao rồi quay xuống gần mức mở cửa. Trong đồ án, mẫu này vẫn được xếp là chưa rõ hướng.',
    'long_legged_doji':'Giá dao động nhiều cả hai phía nhưng đóng cửa gần mức mở cửa: có giằng co, chưa rõ hướng.',
    'spinning_top':'Thân nến nhỏ và có bóng ở hai phía. Phiên này chưa cho thấy bên mua hay bên bán chiếm ưu thế rõ.',
    'marubozu_white':'Giá mở cửa gần đáy và đóng cửa gần đỉnh phiên: bên mua chiếm ưu thế trong phiên đó.',
    'marubozu_black':'Giá mở cửa gần đỉnh và đóng cửa gần đáy phiên: bên bán chiếm ưu thế trong phiên đó.',
    'hammer':'Sau xu hướng giảm, giá từng xuống thấp rồi hồi lên, để lại bóng dưới dài. Đây là dấu hiệu cần theo dõi khả năng hồi phục.',
    'inverted_hammer':'Sau xu hướng giảm, giá có lúc bật lên mạnh nhưng chưa giữ được toàn bộ mức tăng. Cần thêm bằng chứng từ phiên sau.',
    'hanging_man':'Sau xu hướng tăng, xuất hiện nến có bóng dưới dài: giá đã chịu sức ép bán trong phiên. Cần theo dõi khả năng suy yếu.',
    'shooting_star':'Sau xu hướng tăng, giá lên cao rồi lùi xuống, để lại bóng trên dài. Đây là dấu hiệu cần theo dõi khả năng suy yếu.',
    'bullish_engulfing':'Sau xu hướng giảm, thân nến tăng phủ thân nến giảm trước đó: lực mua đã mạnh lên trong cặp phiên này.',
    'bearish_engulfing':'Sau xu hướng tăng, thân nến giảm phủ thân nến tăng trước đó: lực bán đã mạnh lên trong cặp phiên này.',
    'piercing':'Sau xu hướng giảm, nến tăng đóng cửa vượt nửa thân nến giảm trước đó: giá đã hồi lại một phần mức giảm.',
    'dark_cloud_cover':'Sau xu hướng tăng, nến giảm đóng cửa dưới nửa thân nến tăng trước đó: giá đã mất một phần mức tăng.',
    'bullish_harami':'Sau xu hướng giảm, một nến tăng nhỏ nằm trong thân nến giảm trước đó. Đà giảm có thể đang chậm lại.',
    'bearish_harami':'Sau xu hướng tăng, một nến giảm nhỏ nằm trong thân nến tăng trước đó. Đà tăng có thể đang chậm lại.',
    'morning_star':'Ba nến sau xu hướng giảm cho thấy chuyển từ giảm, sang chững lại, rồi hồi phục theo định nghĩa của đồ án.',
    'evening_star':'Ba nến sau xu hướng tăng cho thấy chuyển từ tăng, sang chững lại, rồi suy yếu theo định nghĩa của đồ án.',
    'morning_star_setup':'Mới có hai nến đầu có thể dẫn đến Sao mai. Chưa đủ ba nến để gọi là mẫu hình Sao mai hoàn chỉnh.',
    'evening_star_setup':'Mới có hai nến đầu có thể dẫn đến Sao hôm. Chưa đủ ba nến để gọi là mẫu hình Sao hôm hoàn chỉnh.',
}


def number(value,digits=2):
    if value is None or pd.isna(value):return 'Chưa đủ dữ liệu'
    return f'{float(value):,.{digits}f}'.translate(str.maketrans({',':'.','.':','}))


def explain_signal(row):
    """Diễn giải quy tắc đã có; không sinh dự báo hoặc điểm tin cậy mới."""
    bias=row.get('bias','neutral');state=row.get('status','Quan sát')
    meaning=EXPLANATIONS.get(row.get('name'),'Mẫu hình được nhận diện theo ngưỡng của đồ án; cần đối chiếu diễn biến giá.')
    if row.get('kind')=='setup':
        condition=row.get('follow') or row.get('confirmation') or 'Đối chiếu điều kiện nến thứ ba của mẫu hình.'
    elif bias=='bullish':condition=f"Phiên kế tiếp đóng cửa trên {number(row.get('high'))} đồng (đỉnh nến tín hiệu)."
    elif bias=='bearish':condition=f"Phiên kế tiếp đóng cửa dưới {number(row.get('low'))} đồng (đáy nến tín hiệu)."
    else:condition=f"Quan sát giá thoát vùng {number(row.get('low'))}–{number(row.get('high'))} đồng; mẫu hình chưa ưu tiên hướng."
    if state in ('Thiếu nến xác nhận','Nến xác nhận không hợp lệ'):
        status='Chưa thể đánh giá vì dữ liệu phiên kế tiếp bị thiếu hoặc có lỗi.'
        action='Kiểm tra hoặc nạp bù dữ liệu trước khi đọc kết quả xác nhận.'
    elif state=='Đã xác nhận':
        status='Phiên kế tiếp đã đáp ứng điều kiện theo dõi. Điều này không đảm bảo giá tiếp tục đi đúng hướng hoặc có lãi.'
        action='Ghi vào danh sách theo dõi; đối chiếu thêm xu hướng, khối lượng và mức vô hiệu trước khi cân nhắc quyết định.'
    elif state in ('Phiên kế tiếp không xác nhận','Mất hiệu lực ở phiên kế tiếp'):
        status='Phiên kế tiếp không ủng hộ điều kiện theo dõi đã đặt.'
        action='Không coi tín hiệu này là đã được xác nhận; chờ một bối cảnh hoặc tín hiệu mới.'
    elif bias=='neutral':
        status='Chưa có hướng tăng hoặc giảm ưu tiên theo định nghĩa đang dùng.'
        action='Tiếp tục quan sát giá; không suy ra quyết định mua hoặc bán chỉ từ nến trung tính.'
    else:
        status='Chưa có nến phiên kế tiếp để kiểm tra điều kiện theo dõi.'
        action='Chờ phiên kế tiếp đóng cửa và đối chiếu điều kiện bên dưới; chưa xem đây là lệnh mua hoặc bán.'
    return dict(meaning=meaning,status=status,action=action,condition=condition)


def render_glossary():
    with st.expander('Giải thích từ ngữ: nến, xác nhận, EMA và khối lượng'):
        st.markdown('''
- **Một nến** tóm tắt giá của một phiên: mở cửa, cao nhất, thấp nhất và đóng cửa. Thân nến nối mở cửa–đóng cửa; bóng nến thể hiện hai cực trị.
- **Nến tăng / giảm**: đóng cửa cao hơn / thấp hơn mở cửa cùng phiên. Điều này khác với tăng / giảm so với đóng cửa phiên trước.
- **Mẫu hình** là một hình dạng giá theo quy tắc. **Cảnh báo sớm (setup)** mới có các nến đầu, chưa đủ mẫu hình hoàn chỉnh.
- **Đã xác nhận** ở thẻ này chỉ nghĩa phiên kế tiếp đáp ứng quy tắc theo dõi. Đây không phải xác nhận chắc chắn có lãi.
- **Mức vô hiệu tham khảo** là mốc giá để xem xét lại kịch bản; chưa phải điểm dừng lỗ đã tối ưu.
- **EMA20/EMA50** là đường giá trung bình có trọng số lớn hơn cho các phiên gần đây. Giá trên EMA không tự động là tín hiệu mua.
- **Khối lượng / TB20 = 1,4 lần** nghĩa khối lượng phiên tín hiệu bằng 140% mức trung bình 20 phiên liên tiếp trước đó, không phải xác suất tăng 140%. Thiếu phiên thì chưa tính đủ bối cảnh.
- **Hỗ trợ / kháng cự** trong ứng dụng là đáy / đỉnh 20 phiên liên tiếp trước đó, chỉ là mức giá tham khảo.
''')


@st.cache_data(show_spinner=False)
def enrich(frames, events, asof, market_days, issues=None):
    rows=[]
    for _,event in events.iterrows():
        row=event.to_dict()
        row.update(signal_context(frames[event.symbol],row,asof,market_days,issues))
        rows.append(row)
    return pd.DataFrame(rows)


def render_signal_workspace(frames, events, asof, selected, market_days, root, issues=None, setup_summary=None):
    with st.container():
        st.caption('Hướng tăng/giảm là cách diễn giải mẫu hình theo định nghĩa, chưa phải lệnh mua/bán.')
        render_glossary()
        scope=st.radio('Phạm vi tín hiệu',['Ngày quét','Lịch sử trong khoảng hiển thị'],horizontal=True,key='signal_scope')
        view=events[events.date==asof] if scope=='Ngày quét' else events
        if view.empty:
            st.info('Không có tín hiệu trong phạm vi này. Đây là kết quả bình thường; có thể chuyển sang lịch sử để xem ví dụ đã xuất hiện.');return
        enriched=enrich(frames,view,asof,tuple(market_days),issues)
        prefs=root/'storage/preferences/watchlist.json';saved=[]
        if prefs.exists():
            try:
                saved=json.loads(prefs.read_text(encoding='utf-8'))
                if not isinstance(saved,list):saved=[]
            except (ValueError,OSError):st.warning('Không đọc được danh sách đã lưu. Có thể chọn lại và lưu.')
        with st.expander('Bộ lọc và danh sách quan tâm (tùy chọn)'):
            if any(s not in selected for s in st.session_state.get('watch_symbols',[])):
                st.session_state.pop('watch_symbols',None)
            watch=st.multiselect('Danh sách quan tâm',selected,default=[s for s in saved if s in selected],key='watch_symbols')
            if st.button('Lưu danh sách quan tâm',key='save_watchlist'):
                try:
                    save_watchlist(prefs,watch)
                    st.success('Đã lưu danh sách quan tâm')
                except OSError as exc:st.error(f'Không lưu được danh sách: {exc}')
            only_watch=st.checkbox('Chỉ xem danh sách quan tâm',key='watch_only')
            direction=st.multiselect('Hướng lý thuyết',list(LABELS.values()),default=list(LABELS.values()),key='signal_direction')
            states=['Tất cả',*sorted(enriched.status.unique())]
            if st.session_state.get('signal_status','Tất cả') not in states:st.session_state.pop('signal_status',None)
            state=st.selectbox('Trạng thái xác nhận',states,key='signal_status')
            volume_threshold=st.number_input('Ngưỡng khối lượng tự chọn (lần TB20)',min_value=0.1,max_value=5.0,value=1.2,step=0.1,key='volume_threshold')
            volume=st.checkbox('Lọc theo ngưỡng khối lượng tự chọn',key='signal_volume')
            st.caption('Ngưỡng mặc định 1,2 lần là quy tắc theo dõi tự chọn, chưa phải ngưỡng đã chứng minh hiệu quả giao dịch.')
        if only_watch:enriched=enriched[enriched.symbol.isin(watch)]
        enriched=enriched[enriched.bias.map(LABELS).isin(direction)]
        if state!='Tất cả':enriched=enriched[enriched.status==state]
        if volume:enriched=enriched[enriched.volume_ratio>=volume_threshold]
        if enriched.empty:st.info('Không có tín hiệu đáp ứng bộ lọc. Mở phần bộ lọc để bỏ bớt điều kiện.');return
        enriched=enriched.sort_values(['date','symbol'],ascending=[False,True]).reset_index(drop=True)
        tags={'bullish':'▲ Nghiêng tăng','bearish':'▼ Nghiêng giảm','neutral':'● Trung tính'}
        table=pd.DataFrame({'Mã':enriched.symbol,'Ngày':pd.to_datetime(enriched.date).dt.strftime('%d/%m'),'Mẫu hình':enriched.name_vi,
            'Hướng':['◆ Cảnh báo sớm' if k=='setup' else tags.get(b,'') for k,b in zip(enriched['kind'],enriched.bias)],'KL (lần TB20)':enriched.volume_ratio})
        left,right=st.columns([1,1.35],gap='medium')
        with left:
            st.markdown('**Danh sách tín hiệu** · bấm một dòng để xem chi tiết')
            pick=st.dataframe(table,hide_index=True,width='stretch',height=min(560,42+35*len(table)),on_select='rerun',selection_mode='single-row',key='signal_pick',
                column_config={'KL (lần TB20)':st.column_config.NumberColumn('KL (lần TB20)',format='%.1f',help='Khối lượng phiên so với trung bình 20 phiên trước')})
            rows=list(pick.selection.rows)
            st.caption('Đang hiện dòng đầu tiên nếu chưa chọn. Nhãn hướng là cách diễn giải mẫu hình, không phải khuyến nghị.')
        index=rows[0] if rows and rows[0]<len(enriched) else 0
        r=enriched.iloc[index];explanation=explain_signal(r)
        with right, st.container(border=True,key='detail_card'):
            fr=frames[r.symbol];fr=fr.loc[fr.index<=pd.Timestamp(r.date)].close
            chg=(fr.iloc[-1]/fr.iloc[-2]-1)*100 if len(fr)>1 and pd.notna(fr.iloc[-1]) and pd.notna(fr.iloc[-2]) and fr.iloc[-2] else None
            chg_html='' if chg is None else f'<div class="vr-small" style="color:{"#0b7a5a" if chg>0 else "#c8203f" if chg<0 else "#4a4d5c"};font-weight:600">{chg:+.2f}% so với phiên trước</div>'.replace('.',',')
            st.markdown(f'<div class="vr-dhead"><div><h3>{escape(str(r.symbol))} · {escape(str(r.name_vi))}</h3><div class="vr-small">{LABELS[r.bias]} · tín hiệu ngày {r.date:%d/%m/%Y} · {escape(str(r.status))}</div></div><div class="vr-dprice"><strong>{number(r.close,0)}</strong>{chg_html}</div></div>',unsafe_allow_html=True)
            st.markdown(f'<div class="vr-steps"><div><b>1 · NẾN CHO THẤY GÌ</b>{escape(explanation["meaning"])}</div><div><b>2 · TRẠNG THÁI</b>{escape(explanation["status"])}</div><div><b>3 · CẦN THEO DÕI</b>{escape(explanation["action"])}</div></div>',unsafe_allow_html=True)
            st.write('Điều kiện theo dõi phiên kế tiếp:',explanation['condition'])
            if r['kind']=='setup' and setup_summary is not None and not setup_summary.empty:
                hit=setup_summary[setup_summary.setup==r['name']]
                if not hit.empty and hit.iloc[0].n_evaluated:
                    h=hit.iloc[0];pc=lambda v:f'{v*100:.1f}%'.replace('.',',')
                    st.markdown(f'<div class="vr-ctx"><b>{pc(h.probability)}</b>Trong lịch sử, cảnh báo này hoàn thành {int(h.n_completed)}/{int(h.n_evaluated)} lần (Wilson 95%: {pc(h.ci_low)}–{pc(h.ci_high)}). Đây là tỷ lệ đủ mẫu hình ba nến, chưa phải tỷ lệ có lãi.</div>',unsafe_allow_html=True)
            if r.bias!='neutral' and r['kind']=='pattern':
                st.write('Mức vô hiệu tham khảo:',number(r.invalidation)+' đồng')
                st.caption('Đây là mốc xem xét lại kịch bản, chưa phải điểm dừng lỗ đã được kiểm định.')
            if r['name'] in ('morning_star','evening_star'):
                st.caption('Mẫu hình này đã đủ ba nến tại ngày tín hiệu. Trạng thái ở thẻ là bước theo dõi bổ sung ở phiên kế tiếp, khác với việc đủ ba nến trong thống kê Sao mai/Sao hôm.')
            if pd.Timestamp(r.date)<pd.Timestamp(asof):
                st.caption(f'Tín hiệu lịch sử ngày {r.date:%d/%m/%Y}: trạng thái chỉ xét đúng phiên thị trường kế tiếp, không mô tả tình trạng cổ phiếu hôm nay.')
            trend='Chưa đủ dữ liệu' if pd.isna(r.trend_pct) else ('Giảm' if r.trend_pct<0 else 'Tăng' if r.trend_pct>0 else 'Đi ngang')+' '+number(abs(r.trend_pct))+'% trong 5 phiên trước mẫu hình (mô tả bổ trợ)'
            volume_text='Chưa đủ dữ liệu' if pd.isna(r.volume_ratio) else 'Bằng '+number(r.volume_ratio)+' lần trung bình 20 phiên trước'
            context=pd.DataFrame([
                ['Diễn biến trước mẫu hình',trend],
                ['Giá so với đường trung bình EMA20','Chưa đủ dữ liệu' if pd.isna(r.ema20) else 'Cao hơn EMA20' if r.close>r.ema20 else 'Bằng hoặc thấp hơn EMA20'],
                ['Mức độ giao dịch',volume_text],
                ['Đáy / đỉnh tham khảo 20 phiên trước',number(r.support)+' / '+number(r.resistance)+' đồng']],columns=['Bối cảnh','Diễn giải'])
            with st.expander('Bối cảnh bằng lời và chỉ báo chi tiết'):
                if r.get('context_gaps',0):
                    st.caption('Có phiên thiếu/lỗi trong 50 phiên gần tín hiệu. Chỉ báo chưa đủ chuỗi liên tiếp được để trống; EMA bắt đầu lại sau khoảng thiếu.')
                st.dataframe(context,hide_index=True,width='stretch')
                technical=pd.DataFrame([['Thống kê t xu hướng 10 phiên trước mẫu hình',r.trend_t],['EMA20',r.ema20],['EMA50',r.ema50]],columns=['Chỉ báo','Giá trị'])
                st.dataframe(technical,hide_index=True,width='stretch')
                st.caption('Thống kê t 10 phiên là tiêu chí xu hướng của bộ nhận diện; biến động 5 phiên chỉ bổ trợ. Các đường trung bình và cực trị chưa tự tạo ra một chiến lược giao dịch.')
            st.markdown('**Đối chiếu trên biểu đồ**')
            st.caption('Mỗi nến là một phiên. Nến xanh: đóng cửa cao hơn mở cửa; nến đỏ: đóng cửa thấp hơn mở cửa. Đường nét đứt đánh dấu đỉnh/đáy nến tín hiệu.')
            f=history_at(frames[r.symbol],asof,market_days,issues,r.symbol)
            segment=f.close.isna().cumsum()
            f['ema20']=f.close.groupby(segment).transform(lambda c:c.ewm(span=20,adjust=False,min_periods=20).mean())
            f['ema50']=f.close.groupby(segment).transform(lambda c:c.ewm(span=50,adjust=False,min_periods=50).mean())
            position=f.index.get_loc(pd.Timestamp(r.date))
            f=f.iloc[max(0,position-20):position+11]
            fig=go.Figure(go.Candlestick(x=f.index,open=f.open,high=f.high,low=f.low,close=f.close,name=r.symbol,increasing_line_color='#0b8a66',decreasing_line_color='#d9304e'))
            for name,color in [('ema20','#6d67df'),('ema50','#e6a23c')]: fig.add_scatter(x=f.index,y=f[name],name=name.upper(),mode='lines',line={'color':color,'width':1})
            fig.add_hline(y=r.high,line_dash='dash',line_color='#0b8a66',annotation_text='Đỉnh nến tín hiệu',annotation_position='top left')
            fig.add_hline(y=r.low,line_dash='dash',line_color='#ff244e',annotation_text='Đáy nến tín hiệu',annotation_position='bottom left')
            if r.bias!='neutral' and r['kind']=='pattern':
                level=r.invalidation
                fig.add_hrect(y0=level*.995,y1=level*1.005,fillcolor='#ff244e',opacity=.07,line_width=0)
            fig.add_scatter(x=[r.date],y=[r.close],mode='markers',name='Tín hiệu đang chọn',marker={'size':12,'color':'#ff244e','symbol':'diamond'})
            fig.update_layout(height=380,xaxis_rangeslider_visible=False,template='plotly_white',font={'family':'Inter','size':12,'color':'#2d2f3c'},legend={'orientation':'h'},margin={'t':25,'b':20},separators=',.')
            fig.update_yaxes(title='Giá (đồng)',tickformat=',.0f')
            st.plotly_chart(fig,width='stretch',key='scenario_chart')
            st.caption('Biểu đồ tập trung tối đa 20 phiên có dữ liệu trước và 10 phiên sau tín hiệu, chỉ đến ngày quét; giúp nhìn rõ nến đang chọn.')
            if r.bias!='neutral' and r['kind']=='pattern':
                st.caption('Dải tô là vùng ±0,5% quanh mức vô hiệu để dễ nhìn; chưa phải biên dừng lỗ tối ưu.')
            elif r['kind']=='setup':
                st.caption('Với cảnh báo sớm Sao mai/Sao hôm, dùng điều kiện nến thứ ba ghi trong thẻ; không dùng quy tắc vượt đỉnh/đáy chung.')
        st.download_button('Tải danh sách tín hiệu đã lọc',enriched.to_csv(index=False).encode('utf-8-sig'),'signal_scenarios.csv','text/csv',key='scenario_csv')
        if st.checkbox('Tính thống kê lịch sử của mẫu hình này', key='selected_research'):
            if r['kind']=='setup':
                st.info('Cảnh báo hai nến: xem tỷ lệ hoàn thành Sao mai/Sao hôm trong mục Kết quả nghiên cứu.')
            else:
                _, selected_summary=research(frames,events[events['name']==r['name']],asof,issues,20)
                if not selected_summary.empty:
                    render_research_reading(selected_summary,key_prefix='selected')
                with st.expander('Bảng thống kê chi tiết của mẫu hình đang chọn'):
                    st.dataframe(selected_summary,hide_index=True,width='stretch')
                st.caption('Phạm vi: nhóm mã và khoảng hiển thị đang chọn, đến ngày quét; phí hai chiều mặc định 20 bps. Quy tắc xác nhận chung trong thẻ chưa được kiểm định riêng.')



@st.cache_data(show_spinner=False)
def research(frames,events,asof,issues,fee):
    result=event_outcomes(frames,events,asof,issues,fee_bps=fee)
    return result,summarize_events(result,infer_market_days({s:f.loc[f.index<=asof] for s,f in frames.items()}),inference=False)


def render_research_reading(summary,key_prefix='research'):
    names=sorted(summary['Mẫu hình'].unique())
    if st.session_state.get(key_prefix+'_pattern',names[0]) not in names:st.session_state.pop(key_prefix+'_pattern',None)
    name=st.selectbox('Mẫu hình muốn tìm hiểu',names,key=key_prefix+'_pattern')
    sample=summary[summary['Mẫu hình']==name]
    horizons=sorted(int(x) for x in sample['Số phiên'].unique())
    if st.session_state.get(key_prefix+'_horizon',5) not in horizons:st.session_state.pop(key_prefix+'_horizon',None)
    h=st.selectbox('Theo dõi sau bao nhiêu phiên?',horizons,index=horizons.index(5) if 5 in horizons else 0,format_func=lambda x:f'{x} phiên giao dịch',key=key_prefix+'_horizon')
    row=sample[sample['Số phiên']==h].iloc[0]
    n=int(row['Đủ dữ liệu'])
    st.write(f"Có {n} lần xuất hiện đủ dữ liệu để đánh giá; {int(row['Chưa đủ tương lai'])} lần chưa đủ phiên tương lai; {int(row['Loại thiếu/lỗi'])} lần bị loại do thiếu hoặc lỗi nến.")
    if n:
        st.write(f"Giả sử mua tại mở cửa phiên kế tiếp và bán tại đóng cửa phiên thứ {h}, lợi suất trung bình sau phí là {number(row['Long sau phí TB (%)'])}% trên {n} quan sát.")
        st.write(f"Mức bất lợi trung bình trong thời gian theo dõi là {number(row['Bất lợi TB (%)'])}%: lấy đáy thấp nhất so với giá mua giả định của từng lần, rồi tính trung bình.")
    else:st.info('Chưa có quan sát đủ dữ liệu cho kỳ hạn này; không thể tính kết quả trung bình.')
    st.caption('Đây là mô tả quá khứ của giả định mua rồi bán (long), kể cả với mẫu hình giảm. Không phải gợi ý mua, lợi nhuận bán khống, xác suất có lãi hay mức lỗ tối đa cho lần tiếp theo. Các mẫu có thể chồng lấn.')
    return row


def render_oos_results(frames,asof,issues,folder=None):
    """Đọc bảng holdout đã chạy bằng CLI; bộ lọc UI không fit lại mô hình."""
    folder=Path(folder) if folder is not None else Path(__file__).resolve().parents[2]/'report/oos_verified'
    with st.expander('Đánh giá ngoài mẫu · train trước, test sau'):
        manifest_path=folder/'manifest.json'
        if not manifest_path.exists():
            st.info('Chưa có bộ kết quả ngoài mẫu phiên bản kiểm định hai mẫu tại report/oos_verified. Giữ bộ cũ để đối chiếu; chạy lệnh bên dưới rồi đọc lại trang.')
            st.code(r'.\.venv\Scripts\python.exe scripts/run_study.py --oos --train-end 2025-05-20 --sensitivity --out report/oos_verified',language='powershell')
            return
        try:
            manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
            if manifest.get('mode')!='oos' or manifest.get('status')!='complete':
                raise ValueError('Kết quả ngoài mẫu chưa hoàn tất')
            end=pd.Timestamp(manifest['asof']);protocol=manifest['protocol']
            if protocol.get('version',1)<2:
                st.warning('Bộ báo cáo dùng kiểm định cũ chưa lấy mẫu lại phần train. Chạy bản nghiên cứu mới vào report/oos_verified; không trộn hai phương pháp.')
                return
            if pd.Timestamp(asof)<end:
                st.info(f'Bộ kết quả ngoài mẫu được chốt đến {end:%d/%m/%Y}, sau ngày quét đang chọn. Chọn ngày quét từ ngày này trở đi để không hiển thị kết quả tương lai trong phiên lịch sử.')
                return
            if hashlib.sha256((folder/'oos_protocol.json').read_bytes()).hexdigest()!=manifest['protocol_sha256']:
                raise ValueError('Protocol không khớp manifest')
            for name in ('q2_oos_summary.csv','q3_oos_summary.csv'):
                if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=manifest['table_hashes'][name]:
                    raise ValueError('Bảng '+name+' không khớp manifest; chờ chạy xong hoặc chạy lại nghiên cứu')
            if training_fingerprint(frames,issues,end)!=manifest['input_snapshot_sha256']:
                st.warning('Bộ kết quả được tạo từ bản dữ liệu khác DB đang xem. Chạy lại nghiên cứu với snapshot phù hợp; không ghép kết quả cũ vào DB mới đã sửa lịch sử.')
                return
            summary=pd.read_csv(folder/'q2_oos_summary.csv')
            q3=pd.read_csv(folder/'q3_oos_summary.csv')
        except (OSError,ValueError,KeyError) as exc:
            st.warning('Không đọc được bộ kết quả ngoài mẫu: '+str(exc));return
        st.write(f"Ước lượng (train): {pd.Timestamp(protocol['train_start']):%d/%m/%Y} → {pd.Timestamp(protocol['train_end']):%d/%m/%Y}. Đánh giá (test): {pd.Timestamp(protocol['test_start']):%d/%m/%Y} → {end:%d/%m/%Y}.")
        st.caption('Train là phần lịch sử dùng để ước lượng. Test là các phiên mới hơn chỉ dùng để kiểm tra kết quả; không dùng test để sửa ngưỡng hoặc chọn mô hình thắng.')
        st.caption(f"Rổ {len(manifest['universe'])} mã cố định, không phụ thuộc nhóm mã đang chọn trên UI. Ngưỡng và mức nền được khóa trước phần test. Đây là phân chia theo thời gian hồi cứu vì lịch sử đã từng được khám phá, không phải một tập chưa ai từng xem.")
        if pd.Timestamp(asof)>end:
            st.caption('Đây là kết quả đến ngày chốt trên, chưa gồm các phiên mới hơn. Chạy lại cùng protocol để nối thêm phần test nếu dữ liệu train không đổi.')
        fees=sorted(int(x) for x in summary.fee_bps.unique())
        fee=st.selectbox('Phí giả định trong đánh giá ngoài mẫu',fees,format_func=lambda x:f'{x} bps hai chiều ({number(x/100)}%)',key='oos_fee')
        row=render_research_reading(summary[summary.fee_bps==fee],key_prefix='oos')
        if row.bias=='neutral':
            st.info('Mẫu hình trung tính có thống kê mô tả, không bị gán giả thuyết tăng/giảm để kiểm định.')
        else:
            q_values=[row.get('all_q_fixed'),row.get('trend_q_fixed')]
            finite=[q for q in q_values if pd.notna(q)]
            if not finite:st.info('Chưa đủ nhãn/ngày hoặc số khối dữ liệu để kiểm định hướng. Cần ≥30 nhãn, ≥20 ngày tín hiệu và ≥10 khối lịch ở cả train và test; vẫn có thể đọc thống kê mô tả.')
            elif min(finite)<.05:
                st.write('Có tương phản đạt q BY < 0,05 trong phần test. Xem đúng mức nền ở bảng chi tiết; kết quả chưa tự chứng minh một chiến lược có lãi.')
            else:st.write('Chưa có bằng chứng đủ mạnh về chênh lệch đúng hướng theo chuẩn BY 5% cho lựa chọn này; không đồng nghĩa hiệu ứng bằng 0.')
        st.markdown('**Sao mai / Sao hôm: xác suất ước lượng trước có phù hợp phần test?**')
        for r in q3[q3.setup!='all'].itertuples(index=False):
            forecast='chưa đủ dữ liệu' if pd.isna(r.forecast_probability) else number(r.forecast_probability*100)+'%'
            observed='chưa đủ dữ liệu' if pd.isna(r.test_probability) else number(r.test_probability*100)+'%'
            st.write(f'{r.name_vi}: dự báo cố định từ train {forecast}; phần test có {r.n_test_completed}/{r.n_test_evaluated} lần hoàn thành ({observed}).')
        overall=q3[q3.setup=='all']
        if not overall.empty:
            score=overall.iloc[0]
            low=score.get('brier_gain_low');high=score.get('brier_gain_high')
            if pd.notna(low) and pd.notna(high):
                st.write(f"Khoảng tin cậy khối 95% cho cải thiện Brier chung: {number(low,6)} đến {number(high,6)} (dương là giảm sai số).")
                if low<=0<=high:st.caption('Khoảng này chứa 0: chưa đủ bằng chứng rằng sai số dự báo nhỏ hơn mô hình nền.')
        st.caption('Đây là dự báo hoàn thành mẫu hình ba nến, không phải xác suất sinh lời. Brier và log loss càng thấp càng tốt; mô hình nền dùng một xác suất chung chỉ ước lượng bằng train.')
        with st.expander('Chi tiết kiểm định và điểm dự báo ngoài mẫu'):
            st.dataframe(summary,hide_index=True,width='stretch')
            st.dataframe(q3,hide_index=True,width='stretch')
            st.caption(f"Q2 dùng bootstrap-t, lấy mẫu lại cả train và test theo khối ngày chung cho các mã; mỗi mẫu tính lại nền bằng train, không fit bằng test. Độ dài khối max({manifest.get('block_size',20)},5×kỳ hạn); cần ít nhất 10 khối lịch trong mỗi tập. Họ BY Q2 gồm 280 giả thuyết. Q3 dùng bootstrap ghép cặp theo nhãn và họ BY phụ gồm 6 so sánh điểm dự báo, không gộp với họ Q2.")
            st.download_button('Tải Q2 ngoài mẫu',summary.to_csv(index=False).encode('utf-8-sig'),'q2_oos_summary.csv','text/csv',key='oos_q2_csv')
            st.download_button('Tải Q3 ngoài mẫu',q3.to_csv(index=False).encode('utf-8-sig'),'q3_oos_summary.csv','text/csv',key='oos_q3_csv')
        stress=folder/'execution_stress.csv'
        if stress.exists() and 'execution_stress.csv' in manifest['table_hashes']:
            with st.expander('Giả định khớp lệnh và trượt giá'):
                if hashlib.sha256(stress.read_bytes()).hexdigest()!=manifest['table_hashes']['execution_stress.csv']:
                    st.warning('Bảng kịch bản khớp lệnh không khớp manifest.')
                else:
                    scenarios=pd.read_csv(stress)
                    display=scenarios[(scenarios.name_vi==row['Mẫu hình'])&scenarios.horizon.eq(row['Số phiên'])&scenarios.fee_bps.eq(fee)]
                    display=display[['slippage_bps','n_price_evaluated','n_execution_eligible',
                        'n_not_assumed_fill','mean_net_pct','mean_mae_pct','net_win_rate']].copy()
                    display['net_win_rate']*=100
                    display=display.rename(columns={'slippage_bps':'Trượt giá (bps)',
                        'n_price_evaluated':'Đủ dữ liệu giá','n_execution_eligible':'Giả định khớp',
                        'n_not_assumed_fill':'Không giả định khớp','mean_net_pct':'Long ròng TB (%)',
                        'mean_mae_pct':'Bất lợi TB (%)','net_win_rate':'Long ròng dương (%)'})
                    formats={name:st.column_config.NumberColumn(format='%.2f') for name in
                        ['Long ròng TB (%)','Bất lợi TB (%)','Long ròng dương (%)']}
                    st.dataframe(display,hide_index=True,width='stretch',column_config=formats)
                    st.caption('Trượt giá 0/10/20 bps là kịch bản định trước, cộng với phí. Không giả định khớp nếu phiên vào/ra chỉ có một giá hoặc khối lượng không dương/không biết. OHLC ngày chưa chứng minh khả năng khớp tại mở/đóng cửa; đây không phải lợi nhuận thực hiện.')


def render_verdict(asof, folder=None):
    """Tóm tắt kết quả và phân biệt số kiểm định hợp lệ với họ định trước."""
    folder = (
        Path(folder)
        if folder is not None
        else Path(__file__).resolve().parents[2] / 'report/oos_verified'
    )

    try:
        manifest = json.loads(
            (folder / 'manifest.json').read_text(encoding='utf-8')
        )

        if manifest.get('mode') != 'oos':
            return
        if manifest.get('status') != 'complete':
            return
        if pd.Timestamp(asof) < pd.Timestamp(manifest['asof']):
            return

        family = int(manifest['protocol']['primary_family'])
        table = pd.read_csv(folder / 'q2_oos_summary.csv')

        columns = [
            c for c in ('all_q_fixed', 'trend_q_fixed')
            if c in table
        ]
        if not columns:
            return

        q = pd.to_numeric(
            pd.concat([table[c] for c in columns]),
            errors='coerce',
        )
        q = q[q.between(0, 1)].dropna()

        if q.empty or family < len(q):
            return

    except (OSError, ValueError, KeyError, TypeError):
        return

    hits = int(q.lt(0.05).sum())

    prefix = (
        f'Nghiên cứu đã xác định trước {family} phép kiểm định. '
        f'Có {len(q)} giả thuyết có kết quả kiểm định hợp lệ '
        'trong bộ dữ liệu này. '
    )

    if hits == 0:
        conclusion = (
            '<b>Không giả thuyết nào đạt q &lt; 0,05.</b> '
            'Chưa đủ bằng chứng rằng mẫu hình nến dự báo giá '
            'tốt hơn mức nền.'
        )
    else:
        conclusion = (
            f'<b>{hits} giả thuyết đạt q &lt; 0,05.</b> '
            'Cần đọc bảng chi tiết; kết quả này chưa chứng minh '
            'chiến lược có lãi.'
        )

    st.markdown(
        '<div class="vr-verdict"><b>Kết luận nghiên cứu.</b> '
        f'{prefix}{conclusion} '
        'Công cụ học thuật, không phải khuyến nghị đầu tư.</div>',
        unsafe_allow_html=True,
    )

def render_event_research(frames,events,asof,issues):
    render_verdict(asof)
    render_oos_results(frames,asof,issues)
    with st.expander('Khám phá trong mẫu: giá sau tín hiệu',expanded=True):
        st.info('Phần này xem kết quả trong quá khứ. Tỷ lệ hoàn thành Sao mai/Sao hôm ở phía dưới là việc đủ mẫu hình ba nến, không phải tỷ lệ đầu tư có lãi.')
        scope=st.radio('Phạm vi nghiên cứu Q1/Q2',['Toàn bộ lịch sử','Theo khoảng hiển thị'],horizontal=True,key='q2_scope')
        if scope=='Toàn bộ lịch sử':
            names=st.session_state.get('symbols',list(frames))
            events=build_radar(frames,asof,issues).events
            events=events[events.symbol.isin(names)]
        years,tickers=q1_tables(events)
        with st.expander('Q1 · Mỗi mẫu hình đã xuất hiện bao nhiêu lần?'):
            st.caption('Bảng thứ nhất theo năm, bảng thứ hai theo mã. Một phiên có thể mang nhiều tên mẫu hình nên số nhãn không phải số lần độc lập.')
            st.dataframe(years,width='stretch');st.dataframe(tickers,width='stretch')
            st.download_button('Tải Q1 theo năm',years.to_csv().encode('utf-8-sig'),'q1_year.csv','text/csv',key='q1_year_csv')
            st.download_button('Tải Q1 theo mã',tickers.to_csv().encode('utf-8-sig'),'q1_symbol.csv','text/csv',key='q1_symbol_csv')
        with st.expander('Giả định phí và cách tính lợi suất'):
            fee=st.number_input('Tổng phí hai chiều giả định (bps)',min_value=0,max_value=500,value=20,step=5,key='event_fee')
            st.caption('1 bps = 0,01%. 20 bps = 0,20% tổng hai chiều, chia đều cho mua và bán. Vào tại mở cửa phiên kế tiếp, ra tại đóng cửa t+h; h=1 nghĩa mua và bán trong cùng phiên kế tiếp. Chưa tính trượt giá hoặc khả năng khớp khi trần/sàn.')
        with st.spinner('Đang đối chiếu các lần xuất hiện trong lịch sử...'):
            result,summary=research(frames,events,asof,issues,fee)
        if summary.empty:st.info('Chưa có mẫu hình để thống kê.');return
        render_research_reading(summary)
        with st.expander('Bảng mô tả kỹ thuật và tải CSV'):
            st.dataframe(summary,hide_index=True,width='stretch')
            st.download_button('Tải nghiên cứu lợi suất CSV',summary.to_csv(index=False).encode('utf-8-sig'),'event_summary.csv','text/csv',key='event_summary_csv')
            st.download_button('Tải từng quan sát lợi suất',result.to_csv(index=False).encode('utf-8-sig'),'event_outcomes.csv','text/csv',key='event_rows_csv')
            st.markdown('**Cách đọc:** lợi suất là biến động theo giả định vào/ra trong lịch sử. Phần khám phá chỉ xuất thống kê mô tả; xem CI/p/q trong đánh giá ngoài mẫu phía trên. p/q nhỏ không phải xác suất có lãi cao.')
            st.caption('Long/MAE/tỷ lệ đúng hướng tính theo nhãn; tương phản với mức nền lấy trọng số đều theo ngày tín hiệu. all_mean/trend_mean đổi dấu theo hướng lý thuyết. Không dùng bộ lọc giao diện để chọn họ kiểm định có kết quả thuận lợi.')
        st.caption('Phần khám phá này dùng toàn bộ phạm vi đang chọn để tính mức nền. Đánh giá ngoài mẫu ở mục riêng phía trên đọc bảng do scripts/run_study.py --oos tạo; UI không tự fit lại hoặc thay mốc chia. Kết quả nghiên cứu chưa tự chứng minh hiệu quả giao dịch.')
