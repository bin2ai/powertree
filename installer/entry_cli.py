"""PyInstaller CLI entry point (powertree-cli.exe)."""
import sys

from powertree.cli import main

if __name__ == "__main__":
    sys.exit(main())
