"""I/O dùng riêng cho phân tích bổ sung; không thay protocol hoặc module đã khóa."""
from pathlib import Path
import hashlib
import json
from contextlib import closing
from datetime import datetime
import platform
import sys

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT/'src') not in sys.path:sys.path.insert(0,str(ROOT/'src'))
import numpy as np
import pandas as pd
import scipy
from data import db
from analytics.study import training_fingerprint


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parent_report(folder):
    folder=Path(folder);folder=folder if folder.is_absolute() else ROOT/folder
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('status')!='complete' or manifest.get('mode')!='oos':raise ValueError('Cần báo cáo ngoài mẫu hoàn tất')
    if digest(folder/'oos_protocol.json')!=manifest['protocol_sha256']:raise ValueError('Protocol không khớp manifest')
    for name,value in manifest['table_hashes'].items():
        if digest(folder/name)!=value:raise ValueError('Bảng nguồn thay đổi: '+name)
    return folder,manifest


def snapshot(path,manifest):
    path=Path(path);path=path if path.is_absolute() else ROOT/path
    with closing(db.connect_readonly(path)) as conn:
        conn.execute('BEGIN')
        frames={s:db.load_ohlc(conn,s) for s in manifest['universe']}
        issues=pd.read_sql_query('SELECT symbol,trading_date,check_name AS "check",severity,detail FROM quality_issues',conn)
    asof=pd.Timestamp(manifest['asof'])
    frames={s:f.loc[f.index<=asof].copy() for s,f in frames.items()}
    issues=issues[pd.to_datetime(issues.trading_date)<=asof].copy()
    if training_fingerprint(frames,issues,asof)!=manifest['input_snapshot_sha256']:
        raise ValueError('DB không khớp ảnh dữ liệu của báo cáo nguồn; không ghép snapshot khác')
    return frames,issues


def output_folder(path,parent=None):
    path=Path(path);path=path if path.is_absolute() else ROOT/path
    if parent is not None and path.resolve()==Path(parent).resolve():raise ValueError('Không ghi vào kết quả chính')
    if path.exists() and any(path.iterdir()):raise ValueError('Thư mục đầu ra đã có dữ liệu; chọn tên mới')
    path.mkdir(parents=True,exist_ok=True);return path


def csv(path,name,frame):frame.to_csv(path/name,index=False,encoding='utf-8-sig',lineterminator='\n')


def finish(out,kind,source,settings,script):
    record=dict(status='complete',analysis=kind,generated_at=datetime.now(db.VN).isoformat(),
        parent_manifest_sha256=digest(source/'manifest.json') if source else None,
        parent_report=str(source) if source else None,settings=settings,python=platform.python_version(),
        numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__,script_sha256=digest(script),
        support_sha256=digest(__file__),tables={p.name:digest(p) for p in out.glob('*.csv')})
    paths=[p for d in ['analytics','finance','data'] for p in (ROOT/'src'/d).glob('*.py')]
    record['dependency_hashes']={p.relative_to(ROOT).as_posix():digest(p) for p in paths}
    if source:
        parent=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
        locked=parent.get('protocol',{}).get('numerical_code_hashes',{})
        record['preexisting_parent_code_differences']=[k for k,v in locked.items() if digest(ROOT/k)!=v]
    (out/'manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')


def utf8():
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='backslashreplace')
