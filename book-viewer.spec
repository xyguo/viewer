# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path(SPECPATH)
datas = [
    (str(project_root / "index.html"), "."),
    (str(project_root / "app.js"), "."),
    (str(project_root / "bootstrap.js"), "."),
    (str(project_root / "styles.css"), "."),
]
mathjax_root = project_root / "vendor" / "mathjax"
if (mathjax_root / "es5" / "tex-chtml.js").is_file():
    datas.append((str(mathjax_root), "vendor/mathjax"))

a = Analysis(
    [str(project_root / "src" / "book_viewer" / "__main__.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="book-viewer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
