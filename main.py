"""PowerTree GUI launcher.

Usage:
    .venv\\Scripts\\python.exe main.py            # open with the demo project
    .venv\\Scripts\\python.exe main.py file.ptproj

For the command-line interface use powertree.bat (or `python -m powertree`).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from powertree.ui.app_entry import run_gui


if __name__ == "__main__":
    sys.exit(run_gui(sys.argv[1] if len(sys.argv) > 1 else None))
