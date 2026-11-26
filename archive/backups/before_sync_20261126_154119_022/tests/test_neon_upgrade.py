"""Kiểm tra lỗi nâng cấp khi câu lệnh được trình bày trên nhiều dòng."""
import ast
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
UPGRADER = ROOT / "archive/installers/upgrade_neon_dashboard_v2.py"
SPEC = importlib.util.spec_from_file_location("neon_upgrade", UPGRADER)
upgrade = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(upgrade)
ORIGINAL = (ROOT / "tests/fixtures/main_before_neon.py.txt").read_text(encoding="utf-8")
BUTTON = 'if st.button("Đọc lại SQLite", width="stretch"):'


def formatted_source(case):
    source = ORIGINAL
    if case in ("button_split", "combined"):
        source = source.replace(BUTTON, 'if st.button("Đọc lại SQLite",\n                     width="stretch"\n        ):')
    if case == "button_all_newlines":
        source = source.replace(BUTTON, 'if st.button(\n            "Đọc lại SQLite",\n            width="stretch",\n        ):')
    if case == "button_unicode":
        source = source.replace(BUTTON, 'if st.button("Đọc lại SQLite", help="🧪 Kiểm tra dữ liệu", width="stretch"):')
    if case == "button_existing_key":
        source = source.replace(BUTTON, 'if st.button(\n            "Đọc lại SQLite",\n            key="my_reload",\n            width="stretch",\n        ):')
    if case in ("tabs_split", "combined"):
        source = source.replace('tab1, tab2, tab3, tab4, tab5 = st.tabs(["Radar", "Biểu đồ", "Thống kê cảnh báo", "Chất lượng", "Phương pháp"])',
            '(\n        tab1, tab2, tab3, tab4, tab5\n    ) = st.tabs(\n        ["Radar", "Biểu đồ", "Thống kê cảnh báo",\n         "Chất lượng", "Phương pháp"],\n    )')
    if case in ("hero_split", "combined"):
        source = source.replace('hero(asof, stored_last, len(selected))', 'hero(\n        asof,\n        stored_last,\n        len(selected),\n    )')
    if case in ("import_split", "combined"):
        source = source.replace('from app.premium import apply_theme, sidebar_brand, hero, render_overview',
            'from app.premium import (\n    apply_theme,\n    sidebar_brand, hero,\n    render_overview,\n)')
    if case in ("with_split", "combined"):
        source = source.replace('with tab1:', 'with (\n        tab1,\n    ):  # Giữ chú thích của trang Radar')
    if case == "comments":
        source = source.replace('sidebar_brand()', 'sidebar_brand()  # Thương hiệu của đồ án')
    if case == "reformatted":
        source = ast.unparse(ast.parse(source)) + "\n"
    if case == "crlf":
        source = source.replace("\n", "\r\n")
    if case == "no_final_newline":
        source = source.rstrip("\n")
    return source


@pytest.mark.parametrize("case", ["original", "button_split", "button_all_newlines", "button_unicode", "button_existing_key",
                                 "tabs_split", "hero_split", "import_split", "with_split", "comments",
                                 "reformatted", "crlf", "no_final_newline", "combined"])
def test_upgrade_handles_formatting_and_preserves_data_functions(case):
    source = formatted_source(case)
    original_tree = ast.parse(source)
    result = upgrade.upgrade_source(source)
    compile(result, "main.py", "exec")
    tree = ast.parse(result)
    assert upgrade.upgrade_source(result) == result
    assert not any(upgrade._is_st_call(n, "tabs") for n in ast.walk(tree))
    reload_calls = [n for n in ast.walk(tree) if upgrade._is_st_call(n, "button") and n.args
                    and isinstance(n.args[0], ast.Constant) and n.args[0].value == "Đọc lại SQLite"]
    assert len(reload_calls) == 1
    assert next(k.value.value for k in reload_calls[0].keywords if k.arg == "key") == ("my_reload" if case == "button_existing_key" else "reload_sqlite")
    for name in ("read_data", "analyze", "download", "dates_table"):
        before = next(n for n in original_tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        after = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assert ast.dump(before) == ast.dump(after)
    palette = next(n for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Tuple)
                   and any(isinstance(t, ast.Name) and t.id == "ACCENT" for t in n.targets[0].elts))
    assert palette.value.elts[0].value == "#ff244e"


@pytest.mark.parametrize('stdio_encoding',['utf-8','cp1252:strict'])
def test_cli_upgrade_unicode_path_bom_backup_and_rerun(tmp_path,stdio_encoding):
    root = tmp_path / "Đồ án KIEU"
    main = root / "src/app/main.py"
    main.parent.mkdir(parents=True)
    original = formatted_source("combined").replace("\n", "\r\n").encode("utf-8-sig")
    main.write_bytes(original)
    db = root / "storage/radar.db"
    db.parent.mkdir()
    db.write_bytes(b"existing-database-marker")
    env = root / ".env"
    env.write_bytes(b"existing-env-marker")
    target = root / UPGRADER.name
    shutil.copy2(UPGRADER, target)
    child_env={**os.environ,'PYTHONIOENCODING':stdio_encoding,'PYTHONUTF8':'0'}
    for iteration in range(2):
        result = subprocess.run([sys.executable, str(target)], capture_output=True, encoding='utf-8',env=child_env)
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'Đã áp dụng menu dọc' in result.stdout
        compile(main.read_text(encoding="utf-8"), "main.py", "exec")
        assert db.read_bytes() == b"existing-database-marker"
        assert env.read_bytes() == b"existing-env-marker"
    backups = sorted(root.glob("backup_neon_*"))
    assert len(backups) == 2
    assert (backups[0] / "src/app/main.py").read_bytes() == original
    assert (root / "assets/fonts/inter.css").is_file()


@pytest.mark.parametrize('stdio_encoding',['utf-8','cp1252:strict'])
def test_invalid_input_is_identified_and_not_modified(tmp_path,stdio_encoding):
    main = tmp_path / "src/app/main.py"
    main.parent.mkdir(parents=True)
    source = b'print("invalid"))\n'
    main.write_bytes(source)
    target = tmp_path / UPGRADER.name
    shutil.copy2(UPGRADER, target)
    child_env={**os.environ,'PYTHONIOENCODING':stdio_encoding,'PYTHONUTF8':'0'}
    result = subprocess.run([sys.executable, str(target)], capture_output=True, encoding='utf-8',env=child_env)
    assert result.returncode != 0
    assert "hiện tại" in result.stderr
    assert main.read_bytes() == source
    assert not (tmp_path / "src/app/premium.py").exists()
    assert not list(tmp_path.glob("backup_neon_*"))
