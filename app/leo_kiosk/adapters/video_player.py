"""mpv video-playback adapter: argv building and validation only.

The playback process is spawned through the deployed ``videos.py`` entry
script so leopowerd's kill guard sees the allowlisted ``videos.py`` argv[0]
exactly as before the web port; lifetime is the caller's (launcher engine's)
job.
"""

from leo_kiosk.domain.errors import ValidationError


def build_video_command(script_path: str, url: str) -> tuple[str, ...]:
    if not url.lower().startswith(("http://", "https://")):
        raise ValidationError("Only HTTP(S) URLs may be played")
    if any(c.isspace() or c == "\x00" for c in url):
        raise ValidationError("Video URL contains whitespace or control characters")
    return (script_path, url)
