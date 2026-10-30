# PyInstaller build configuration for ImageShelf (Task 14).
# Build with:   pyinstaller imageshelf.spec
# Result:       dist/ImageShelf/ImageShelf.exe (Windows) or dist/ImageShelf/ImageShelf (macOS/Linux)
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("assets", "assets")],          # the completion sound, found via app.utils.resource_path
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ImageShelf",
    console=False,                         # no black console window behind the GUI
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="ImageShelf",
)
