"""Di chuyển có manifest; mặc định xem trước, --apply thực hiện, --undo hoàn tác."""
import argparse
import json
from pathlib import Path
import shutil
from datetime import datetime
import ast
import re

ROOT=Path(__file__).resolve().parents[2]


def plan(root):
    moves=[]
    # Các trình cài bản vá chỉ dùng một lần, không thuộc mã chạy của ứng dụng.
    for name in ('upgrade_project.py', 'upgrade_research.py', 'repair_auto_update.py'):
        source=root/'scripts/maintenance'/name
        if source.is_file():
            moves.append((source.relative_to(root).as_posix(),'archive/installers/'+name,'archive'))
    runtime={'update_data.py':'scripts/data/update_data.py','install_update_task.py':'scripts/system/install_update_task.py',
             'capture_dashboard.py':'scripts/app/capture_dashboard.py','check_data.py':'scripts/data/check_data.py',
             'remove_eco.py':'scripts/data/remove_eco.py','run_setup_probability.py':'scripts/analytics/run_setup_probability.py'}
    for name,dest in runtime.items():
        if (root/name).is_file(): moves.append((name,dest,'utility'))
    for p in root.iterdir():
        if p.name.startswith(('backup_dashboard_','backup_neon_')) or p.name=='src_backup_before_radar':
            moves.append((p.name,'archive/backups/'+p.name,'archive'))
        elif p.is_file() and p.name.startswith('upgrade_') and p.suffix=='.py':
            moves.append((p.name,'archive/installers/'+p.name,'archive'))
        elif p.name=='pyproject_before_radar.toml': moves.append((p.name,'archive/config/'+p.name,'archive'))
        elif p.is_file() and p.suffix=='.md' and p.name.startswith(('HUONG_DAN_','SUA_LOI_')):
            moves.append((p.name,'docs/legacy/'+p.name,'archive'))
        elif p.name in ('refresh_radar.patch','TEP_VA_SHA256.json'):
            moves.append((p.name,'archive/installers/'+p.name,'archive'))
    for folder in ('src','tests'):
        for p in (root/folder).rglob('*.bak'):
            rel=p.relative_to(root).as_posix();moves.append((rel,'archive/backups/'+rel,'archive'))
    for p in (root/'storage').glob('radar_before_*.db'):
        moves.append((p.relative_to(root).as_posix(),'storage/backups/'+p.name,'archive'))
    return moves


def adapt(text, destination):
    # Các script gốc dùng __file__ để tìm project; thay biểu thức này trước khi di chuyển.
    text=re.sub(r'Path\(__file__\)(?:\.resolve\(\))?\.parent(?!s)', 'Path(__file__).resolve().parents[2]',text)
    if destination.endswith('install_update_task.py'):
        text=text.replace('"update_data.py"','"scripts\\data\\update_data.py"')
    tree=ast.parse(text)
    line=0
    for node in tree.body:
        if isinstance(node,ast.Expr) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str): line=node.end_lineno
        elif isinstance(node,ast.ImportFrom) and node.module=='__future__': line=node.end_lineno
        else: break
    lines=text.splitlines(keepends=True)
    bootstrap='\nimport os as _radar_os, sys as _radar_sys\nfrom pathlib import Path as _RadarPath\n_radar_root = _RadarPath(__file__).resolve().parents[2]\n_radar_sys.path.insert(0, str(_radar_root / "src"))\n_radar_os.chdir(_radar_root)\n'
    text=''.join(lines[:line])+bootstrap+''.join(lines[line:])
    compile(text,destination,'exec')
    return text


def apply(root):
    moves=plan(root)
    if not moves:
        print('Không còn file thuộc danh sách cần di chuyển.');return None
    for source,dest,kind in moves:
        if (root/dest).exists(): raise FileExistsError(f'Đích đã có, dừng để tránh ghi đè: {dest}')
        if kind=='utility': adapt((root/source).read_text(encoding='utf-8-sig'),dest)
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    folder=root/'archive/migrations'/stamp;folder.mkdir(parents=True)
    manifest=folder/'moves.json';entries=[]
    manifest.write_text('[]',encoding='utf-8')
    for source,dest,kind in moves:
        original=root/source;target=root/dest;target.parent.mkdir(parents=True,exist_ok=True)
        entry={'source':source,'target':dest,'original_copy':None}
        if kind=='utility':
            copy=folder/source;copy.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,copy)
            entry['original_copy']=copy.relative_to(root).as_posix()
            target.write_text(adapt(original.read_text(encoding='utf-8-sig'),dest),encoding='utf-8')
            original.unlink()
        else: shutil.move(str(original),str(target))
        entries.append(entry);manifest.write_text(json.dumps(entries,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Đã sắp xếp. Manifest hoàn tác:',manifest)
    print('Nếu đã cài lịch Windows, đăng ký lại: .\\.venv\\Scripts\\python.exe scripts/system/install_update_task.py')
    return manifest


def undo(root,manifest):
    entries=json.loads(Path(manifest).read_text(encoding='utf-8'))
    for e in entries:
        if (root/e['source']).exists(): raise FileExistsError('Đã có file tại vị trí cũ: '+e['source'])
    for e in reversed(entries):
        source=root/e['source'];target=root/e['target'];source.parent.mkdir(parents=True,exist_ok=True)
        if e['original_copy']:
            shutil.copy2(root/e['original_copy'],source);target.unlink()
        else: shutil.move(str(target),str(source))
    print('Đã hoàn tác. Đăng ký lại lịch Windows nếu bạn đã đổi lịch theo đường dẫn mới.')


if __name__=='__main__':
    # CLI tiếng Việt dùng UTF-8 cả khi stdout/stderr bị chuyển vào pipe trên Windows.
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true');parser.add_argument('--undo')
    args=parser.parse_args()
    if args.undo: undo(ROOT,args.undo)
    elif args.apply: apply(ROOT)
    else:
        for source,dest,_ in plan(ROOT): print(source,'->',dest)
        print('Chỉ xem trước. Thêm --apply để thực hiện.')
