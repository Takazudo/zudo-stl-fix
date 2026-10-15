"""Onedir helper with PyInstaller's signing-compatible macOS bundle layout."""
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
datas, binaries, hiddenimports = [], [], []
for package in ("numpy", "scipy", "shapely", "trimesh"):
    d, b, h = collect_all(
        package, include_py_files=False,
        filter_submodules=lambda name: ".tests" not in name and ".testing" not in name,
    )
    datas += d
    binaries += b
    hiddenimports += h
a = Analysis(
    [str(root / "engine" / "worker.py")], pathex=[str(root / "engine")],
    binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "pytest", "IPython"], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="stl-worker",
    console=True, debug=False, strip=False, upx=False,
    target_arch=os.environ["ZUDO_BUILD_ARCH"], codesign_identity=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="stl-worker")
app = BUNDLE(
    coll, name="STLWorker.app", bundle_identifier="com.takazudo.zudostlfix.worker",
    info_plist={"LSBackgroundOnly": True, "LSMinimumSystemVersion": "14.0"},
)
