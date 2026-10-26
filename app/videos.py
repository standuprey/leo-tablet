#!/usr/bin/env python3
"""Videos kiosk screen entry point; the package lives beside this file."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# The launcher spawns this screen with stdio DEVNULL; without this redirect
# an import-time crash would be invisible over SSH. One log, always fresh.
try:
    _log = open("/tmp/leo-videos.log", "a", buffering=1)
    os.dup2(_log.fileno(), 1)
    os.dup2(_log.fileno(), 2)
except OSError:
    pass

from leo_kiosk.ui.videos_window import main  # noqa: E402

if __name__ == "__main__":
    main()