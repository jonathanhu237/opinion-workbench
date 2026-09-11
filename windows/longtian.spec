from pathlib import Path

from PyInstaller.building.build_main import Analysis, COLLECT, EXE, PYZ
from PyInstaller.utils.hooks import collect_all, collect_submodules

repo_root = Path(SPECPATH).resolve().parent
backend_src = repo_root / "backend" / "src"
frontend_dist = repo_root / "frontend" / "dist"
entrypoint = Path(SPECPATH).resolve() / "launcher_entry.py"

if not (frontend_dist / "index.html").is_file():
    raise RuntimeError("Build frontend/dist before running PyInstaller")

playwright_datas, playwright_binaries, playwright_hiddenimports = collect_all(
    "playwright"
)
hiddenimports = collect_submodules("longtian_api") + playwright_hiddenimports
datas = [
    (str(frontend_dist), "resources/static"),
    *playwright_datas,
]

a = Analysis(
    [str(entrypoint)],
    pathex=[str(backend_src)],
    binaries=playwright_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Longtian",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
worker_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LongtianGalleryWorker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    worker_exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Longtian",
)
