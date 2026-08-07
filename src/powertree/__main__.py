"""`python -m powertree` — dispatches to the CLI (use `powertree gui` for
the desktop app)."""

import sys

from .cli import main

sys.exit(main())
