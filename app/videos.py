#!/usr/bin/env python3
"""Video playback wrapper: `videos.py <url>` plays one video fullscreen with mpv.

Spawned by the launcher's launch engine (POST /videos/play -> controller) so
leopowerd's kill guard and backwatch still see the allowlisted argv[0]. mpv
runs in this script's process group (no new session), so the power button and
the Down/Up hold tear down playback together with this wrapper; when mpv
exits, the launcher's watch restores the Videos page. mpv 0.41 dropped
--play-and-exit; --keep-open=no is the same behavior, and --no-terminal is
omitted so errors reach the log.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    # mpv's own output must be visible for on-device diagnosis.
    _log = open("/tmp/leo-videos.log", "a", buffering=1)
    os.dup2(_log.fileno(), 1)
    os.dup2(_log.fileno(), 2)
except OSError:
    _log = None

from leo_kiosk.adapters.video_player import build_video_command  # noqa: E402

MPV = "mpv"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: videos.py <video-url>")
    build_video_command(MPV, sys.argv[1])  # validates; raises before mpv runs
    args = [
        "--fullscreen",
        "--keep-open=no",
        "--hwdec=auto",
        "--ytdl-format=best[height<=?1080]",
        "--script-opts=ytdl_hook-ytdl_path=yt-dlp",
        sys.argv[1],
    ]
    raise SystemExit(subprocess.call([MPV, *args], cwd=HERE))


if __name__ == "__main__":
    main()
