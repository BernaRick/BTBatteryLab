# PyInstaller spec per pacchettizzare il collector Python in un
# eseguibile standalone (vedi docs/roadmap.md, "Standalone .exe
# packaging" e build_exe.bat).
#
# Uso manuale (di solito e' build_exe.bat a farlo): dalla root del
# repo, con il virtual environment attivato,
#     pyinstaller btbatterylab.spec
#
# Modalita' --onedir (non --onefile): produce dist/btbatterylab/ con
# btbatterylab.exe piu' le sue dipendenze come cartella - avvio
# immediato e piu' facile da debuggare rispetto a --onefile, che
# invece si scompatta in una cartella temporanea a ogni avvio. Il
# collector non ha dipendenze di terze parti (solo libreria standard:
# sqlite3, threading, json, pathlib, subprocess), quindi non servono
# hidden-imports.

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
