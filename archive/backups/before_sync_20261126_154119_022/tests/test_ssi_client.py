"""Hợp đồng SSI với Session giả; không dùng khóa thật hoặc mạng."""
import numpy as np
import pandas as pd
import pytest
import requests

from ssi_api import client as api


class Response:
    def __init__(self,status=200,data=None,headers=None):
        self.status_code=status;self.data=data;self.headers=headers or {}
        self.text='fake response';self.url=api.BASE+'/data/ohlc'
    def json(self):
        assert self.status_code!=204,'204 must not require a JSON body'
        return self.data
    def raise_for_status(self):
        if self.status_code>=400:raise requests.HTTPError('fake HTTP failure')


class Session:
    def __init__(self):
        self.headers={};self.posts=[];self.gets=[];self.responses=[]
    def post(self,url,**kwargs):
        self.posts.append((url,kwargs))
        return Response(data={'accessToken':'fake-token','expiresAt':10000})
    def get(self,url,**kwargs):
        self.gets.append((url,kwargs))
        assert self.responses,'Unexpected network request in offline test'
        return self.responses.pop(0)


@pytest.fixture
def client(monkeypatch):
    session=Session();waits=[]
    monkeypatch.setattr(api.requests,'Session',lambda:session)
    monkeypatch.setattr(api.time,'time',lambda:1000.)
    monkeypatch.setattr(api.time,'sleep',waits.append)
    result=api.SSIClient('fake-key','fake-secret')
    return result,session,waits


def test_login_sets_read_token_and_refreshes_before_expiry(client):
    c,s,_=client
    assert s.posts[0][0]==api.BASE+'/auth/token'
    assert s.posts[0][1]['json']=={'apiKey':'fake-key','apiSecret':'fake-secret'}
    assert s.headers['Authorization']=='Bearer fake-token'
    c.exp=1059;s.responses=[Response(data={'data':[]})]
    c.get('/data/ohlc',{'symbol':'FPT'})
    assert len(s.posts)==2 and len(s.gets)==1


def test_rate_limit_retries_are_bounded_and_do_not_sleep_in_real_time(client):
    c,s,waits=client;s.responses=[Response(429),Response(429),Response(data={'data':[]})]
    c.get('/data/ohlc',{})
    assert waits==[2.,4.,.2] and len(s.gets)==3
    s.responses=[Response(429)]*5;waits.clear()
    with pytest.raises(RuntimeError,match='tần suất'):c.get('/data/ohlc',{})
    assert waits==[2.,4.,8.,16.,32.]


def test_http_error_is_not_silently_returned_as_empty_data(client):
    c,s,_=client;s.responses=[Response(503)]
    with pytest.raises(api.SSIError) as error:c.get('/data/ohlc',{})
    assert error.value.status==503 and len(s.gets)==1


def test_pagination_accepts_short_pages_but_requires_empty_termination(client):
    c,s,_=client
    s.responses=[Response(data={'data':[{'symbol':'A'}]}),
        Response(data={'data':[{'symbol':'B'}]}),Response(204)]
    out=c._paged('/data/ohlc',{},100,5)
    assert out.symbol.tolist()==['A','B']
    assert [kwargs['params']['pageIndex'] for _,kwargs in s.gets]==[1,2,3]


@pytest.mark.parametrize('case',['repeat','max_pages'])
def test_incomplete_pagination_raises_instead_of_returning_partial_history(client,case):
    c,s,_=client
    values=['A','A'] if case=='repeat' else ['A','B']
    s.responses=[Response(data={'data':[{'symbol':value}]}) for value in values]
    with pytest.raises(RuntimeError):c._paged('/data/ohlc',{},1,2)


def test_page_size_fallback_does_not_swallow_date_format_errors(client,monkeypatch):
    c,_,_=client;attempts=[]
    def paged(path,params,size,max_pages):
        attempts.append(size)
        if size>100:raise api.SSIError(400,'unsupported page size','fake')
        return pd.DataFrame({'close':['100']})
    monkeypatch.setattr(c,'_paged',paged)
    assert c.paged('/data/ohlc',{},page_size=1000).close.tolist()==['100']
    assert attempts==[1000,500,100]
    def invalid_date(*args):raise api.SSIError(400,'400213 invalid date','fake')
    monkeypatch.setattr(c,'_paged',invalid_date)
    with pytest.raises(api.SSIError,match='400213'):c.paged('/data/ohlc',{},1000)


def test_date_format_negotiation_is_cached_per_endpoint(client,monkeypatch):
    c,_,_=client;seen=[]
    def paged(path,params,page_size):
        seen.append((path,params))
        if len(params['from'])==10:raise api.SSIError(400,'400213','fake')
        return pd.DataFrame({'close':['100']})
    monkeypatch.setattr(c,'paged',paged)
    start=pd.Timestamp('2026-01-05');end=pd.Timestamp('2026-01-06')
    first=c.ohlc('FPT',start,end)
    assert seen[-1][1]['from']=='2026/01/05 00:00:00'
    assert seen[-1][1]['to']=='2026/01/06 23:59:59'
    before=len(seen);c.ohlc('FPT',start,end)
    assert len(seen)==before+1 and first.close.iloc[0]==100
    assert '/data/securitiesSummary' not in c.fmt


def test_numeric_and_mixed_date_conversion_preserve_identifiers():
    frame=pd.DataFrame({'symbol':['001','ABC'],'tradingDate':['2026/01/05','2026-01-06'],
        'close':['100.5','bad'],'volume':['1000','0']})
    result=api.to_num(frame)
    assert result.symbol.tolist()==['001','ABC'] and result.tradingDate.tolist()==['2026/01/05','2026-01-06']
    assert result.close.iloc[0]==100.5 and np.isnan(result.close.iloc[1])
    dates=api.to_date(pd.Series(['2026/01/05','2026-01-06','07/01/2026','invalid']))
    assert dates.iloc[:3].tolist()==list(pd.date_range('2026-01-05',periods=3)) and pd.isna(dates.iloc[3])


@pytest.mark.parametrize('headers,expected',[({},2.),({'X-RATELIMIT-RESET':'bad'},2.),
    ({'X-RATELIMIT-RESET':'0'},1.),({'X-RATELIMIT-RESET':'120'},60.)])
def test_rate_limit_delay_is_clamped(headers,expected):
    assert api.wait_seconds(headers,default=2.)==expected
