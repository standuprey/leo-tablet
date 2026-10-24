"""Private Firefox profiles: per-trial ephemeral, persistent child profile."""

import os
import shutil
from pathlib import Path

from leo_kiosk.domain.errors import ValidationError

# Minimal, non-sandbox-weakening kiosk prefs: no first-run noise, no session
# restore, no download prompts blocking a fullscreen game. TLS and the
# sandbox stay untouched; content-filter policy is a separate task.
_TRIAL_PREFS = {
    "browser.shell.checkDefaultBrowser": False,
    "browser.startup.homepage_override.mstone": "ignore",
    "browser.sessionstore.resume_from_crash": False,
    "browser.download.panel.shown": False,
    "browser.aboutConfig.showWarning": False,
    "datareporting.policy.dataSubmissionEnabled": False,
    "toolkit.telemetry.enabled": False,
}


class BrowserProfiles:
    def __init__(self, data_dir: Path, cache_dir: Path | None = None) -> None:
        self._data = Path(data_dir) / "firefox-profiles"
        self._cache = Path(cache_dir) if cache_dir else None

    @property
    def child_profile(self) -> Path:
        profile = self._data / "child"
        profile.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._write_prefs(profile, _TRIAL_PREFS)
        return profile

    def new_trial_profile(self) -> Path:
        import tempfile

        self._data.mkdir(parents=True, exist_ok=True, mode=0o700)
        profile = Path(tempfile.mkdtemp(prefix="trial-", dir=self._data))
        os.chmod(profile, 0o700)
        self._write_prefs(profile, _TRIAL_PREFS)
        return profile

    def cleanup_profile(self, profile: Path) -> None:
        if profile == self.child_profile:
            return  # the child profile persists across sessions
        shutil.rmtree(profile, ignore_errors=True)

    @staticmethod
    def _write_prefs(profile: Path, prefs: dict[str, object]) -> None:
        profile.mkdir(parents=True, exist_ok=True)
        lines = [f'user_pref("{key}", {value!r});' for key, value in prefs.items()]
        (profile / "user.js").write_text("\n".join(lines) + "\n")
        os.chmod(profile / "user.js", 0o600)

    @staticmethod
    def validate_profile_path(profile: Path, expected_parent: Path) -> None:
        resolved = profile.resolve()
        if not resolved.is_relative_to(Path(expected_parent).resolve()):
            raise ValidationError("Profile path escaped the private profiles directory")
