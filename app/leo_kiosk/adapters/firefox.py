"""Firefox launch adapter: argv building only; lifetime is the session's job."""

from pathlib import Path

from leo_kiosk.domain.errors import ValidationError


def build_firefox_command(
    firefox_binary: str, profile: Path, url: str, extra_args: tuple[str, ...] = ()
) -> tuple[str, ...]:
    if not url.lower().startswith(("http://", "https://")):
        raise ValidationError("Only HTTP(S) URLs may be opened in the game browser")
    if not url or any(c.isspace() or c == "\x00" for c in url):
        raise ValidationError("Game URL contains whitespace or control characters")
    return (
        firefox_binary,
        "--no-remote",
        "--new-instance",
        "--profile",
        str(profile),
        "--kiosk",
        url,
        *extra_args,
    )
