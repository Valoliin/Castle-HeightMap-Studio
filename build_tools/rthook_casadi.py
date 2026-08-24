"""
Runtime hook for CasADi native libraries.

On Windows, DLL dependency lookup for casadi/_casadi.pyd must include the
bundled casadi directory. PyInstaller extracts onefile applications under
sys._MEIPASS.
"""
import builtins
import os
import sys

_dll_handles = []

if sys.platform.startswith("win"):
    base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    candidates = [
        os.path.join(base, "casadi"),
        base,
    ]

    for directory in candidates:
        if not os.path.isdir(directory):
            continue

        # PATH also helps CasADi's own plugin loader.
        current_path = os.environ.get("PATH", "")
        if directory not in current_path.split(os.pathsep):
            os.environ["PATH"] = directory + os.pathsep + current_path

        # Python 3.8+ safe DLL search mechanism.
        try:
            handle = os.add_dll_directory(directory)
            _dll_handles.append(handle)
        except (AttributeError, OSError):
            pass

# Keep handles alive for the whole process lifetime.
builtins._CHMS_CASADI_DLL_HANDLES = _dll_handles
