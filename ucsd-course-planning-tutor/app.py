"""Compatibility shim.

The project used to live in this subdirectory, with an older copy of the same
app at the repository root. It now lives at the root only. Any Streamlit Cloud
deployment still pointing at this path keeps working through here rather than
silently serving the stale copy, which is what happened for a month.
"""

import pathlib
import runpy
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
