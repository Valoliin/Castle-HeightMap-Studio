"""
PyInstaller hook for CasADi.

CadQuery imports CasADi through its assembly/constraint stack. On Windows,
CasADi is not just Python code: casadi._casadi.pyd depends on native DLLs and
CasADi ships many plugin DLLs in the casadi package directory.

collect_all() explicitly collects:
- submodules
- package data
- dynamic libraries
"""
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("casadi")

# SWIG first tries casadi._casadi, then falls back to _casadi.
for module_name in ("casadi._casadi", "_casadi"):
    if module_name not in hiddenimports:
        hiddenimports.append(module_name)
