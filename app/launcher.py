#!/usr/bin/env python3
"""Léo's kiosk launcher entry point.

The application lives in the leo_kiosk package (ui/window.py renders the
tiles, application.py composes services and parent mode). This file only
bootstraps the import path so the deployed single-file layout works.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from leo_kiosk.application import main  # noqa: E402

if __name__ == "__main__":
    main()
