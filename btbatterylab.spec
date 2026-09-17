# PyInstaller spec for packaging the Python collector into a
# standalone executable (see docs/roadmap.md, "Standalone .exe
# packaging" and build_exe.bat).
#
# Manual use (usually build_exe.bat does this): from the repo root,
# with the virtual environment activated,
#     pyinstaller btbatterylab.spec
#
# --onedir mode (not --onefile): produces dist/btbatterylab/ with
# btbatterylab.exe plus its dependencies as a folder - immediate
# startup and easier to debug than --onefile, which instead unpacks
# itself into a temp folder on every launch. The collector has no
# third-party dependencies (only the standard library: sqlite3,
# threading, json, pathlib, subprocess), so no hidden-imports are
# needed.

block_cipher = None

a = Analysis(
    ["src/btbatterylab/main.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="btbatterylab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="btbatterylab",
)
