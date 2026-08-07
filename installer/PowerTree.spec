# PyInstaller spec: builds dist/PowerTree with PowerTree.exe (GUI) and
# powertree-cli.exe (console) sharing one runtime folder.
# Build:  .venv\Scripts\pyinstaller.exe installer\PowerTree.spec --noconfirm

import os

# SPECPATH is the directory containing this spec file (installer/)
ROOT = os.path.dirname(os.path.abspath(SPECPATH))   # repo root
SRC = os.path.join(ROOT, "src")

a_gui = Analysis(
    [os.path.join(ROOT, "installer", "entry_gui.py")],
    pathex=[SRC],
    datas=[(os.path.join(ROOT, "examples", "DemoBoard.ptproj"), "examples")],
    hiddenimports=["powertree.mcp_server"],
    excludes=["tkinter", "matplotlib", "numpy", "PIL.ImageQt"],
    noarchive=False,
)
pyz_gui = PYZ(a_gui.pure)
exe_gui = EXE(
    pyz_gui, a_gui.scripts, [],
    exclude_binaries=True,
    name="PowerTree",
    console=False,
    icon=None,
)

a_cli = Analysis(
    [os.path.join(ROOT, "installer", "entry_cli.py")],
    pathex=[SRC],
    hiddenimports=["powertree.mcp_server"],
    excludes=["tkinter", "matplotlib", "numpy"],
    noarchive=False,
)
pyz_cli = PYZ(a_cli.pure)
exe_cli = EXE(
    pyz_cli, a_cli.scripts, [],
    exclude_binaries=True,
    name="powertree-cli",
    console=True,
    icon=None,
)

coll = COLLECT(
    exe_gui, a_gui.binaries, a_gui.datas,
    exe_cli, a_cli.binaries, a_cli.datas,
    name="PowerTree",
)
