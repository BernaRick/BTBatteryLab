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
# itself into a temp folder on every launch. The collector's own code
# has no third-party dependencies beyond nicegui (only the standard
# library otherwise: sqlite3, threading, json, pathlib, subprocess),
# so no hidden-imports are needed.
#
# `datas` bundles src/btbatterylab/ui/assets/ (Patrick's logo, see
# app.py's _LOGO_DIR) into the frozen build under btbatterylab/ui/
# assets/ - PyInstaller only auto-bundles Python modules it detects via
# import analysis, never arbitrary static files sitting next to them,
# so this static asset needs listing explicitly or it's silently
# missing from the build (caught 2026-09-28: the logo was committed and
# worked when run from source, but not after a rebuild).

block_cipher = None

a = Analysis(
    ["src/btbatterylab/main.py"],
    pathex=["src"],
    binaries=[],
    datas=[
        ("src/btbatterylab/ui/assets", "btbatterylab/ui/assets"),
    ],
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
