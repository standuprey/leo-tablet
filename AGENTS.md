# AGENTS.md — Léo's tablet (Surface Go kiosk)

Agent-facing rules for working in this repository. Human-facing overview: [README.md](README.md).

## What this is

A fullscreen picture-tile kiosk for a 5-year-old on a Surface Go running Arch Linux with the `cage` compositor and `greetd` auto-login. Python/GTK3 app; SQLite catalog/review store under a "parent mode" rework (see `docs/parent-mode/`).

## Layout

| Path | Contents |
|---|---|
| `app/` | Python code: `pyproject.toml`, `leo_kiosk/` package (`domain/`, `services/`, `storage/`, `adapters/`, `ui/`), `tests/` (`unit/`, `integration/`, `ui/`), plus legacy runtime scripts `launcher.py`, `backwatch.py`, `run.sh` (deployed byte-identical to the tablet; do not reformat — see `pyproject.toml` ruff excludes) |
| `config/` | Files installed onto the tablet by `install-kiosk.sh`: `tiles.json`, `logind-power.conf`, `sleep-power.conf`, `90-leotablet-typecover.rules` |
| `docs/` | `parent-mode/` architecture/backlog/status, `specs.md` |
| `install-kiosk.sh` | Root-level deploy entry point (sudo) |
| `catalog/`, `tools/`, `web-games.json` | Game-catalog discovery data and import tool |
| `catalog.sqlite3` mentions in docs | Device runtime DB at `${XDG_DATA_HOME:-~/.local/share}/leo-kiosk/` — a device path, not a repo file |

## The device

- Surface Go, Arch + linux-surface kernel, hostname `leo-tablet`, LAN address `192.168.1.186`.
- SSH as `standup@192.168.1.186` with `~/.ssh/id_ed25519` (key auth, no password). Not on Tailscale.
- Kiosk user `leo`: no SSH, no sudo. Runtime files live in `/home/leo/kiosk/`, content in `/home/leo/Leo/`.
- **Sudo on the tablet requires a password and only the user can type it.** Never run sudo remotely; prepare the commands and hand them over, or wait for the user to run them.
- The tablet sleeps/suspends; SSH times out when it is asleep. Wake it (power button) and retry.
- The device is for a child: changes to power behavior, gestures, or time limits are safety-relevant. Test on-device before declaring done.

## Working rules

1. **Anything that exists on the device must exist in this repo first.** Author files here, then deploy. No one-off edits on the tablet.
2. **Deploy** = rsync this repo to the tablet's canonical checkout `~/leo-kiosk` (on the device), then `sudo ./install-kiosk.sh` from that checkout. The installer verifies byte-identity against `app/` + `config/` and writes a `deploy-manifest` to `/home/leo/kiosk/` for identifying the deployed version.
3. **Power button** (`app/powerd.py` → `leopowerd.service`): press = screen off, press again = screen on, 60 s screen-off = suspend, resume restores the screen. The EC reports the button as an atomic press+release (no hold info reaches the OS — see `config/logind-power.conf`), so logind must keep `HandlePowerKey=ignore` and power-off lives in the parent-mode "Power off" tile. The Type Cover udev rule (`config/90-leotablet-typecover.rules`) and single `SuspendState=mem` (`config/sleep-power.conf`) exist because the Type Cover otherwise aborts every suspend with a spurious wake. Don't "simplify" these away without reading `docs/` and the device journal.
4. **Tests**: run from `app/` with the repo-root venv: `../.venv/bin/python -m pytest -q`. UI tests need a display and `--run-display`; hardware tests need `--run-hardware`. `ruff` and `mypy` (strict, configured in `app/pyproject.toml`) are part of the checks.
5. Task/backlog state lives in `docs/parent-mode/backlog.md` and `tasks.json`; keep them consistent when completing work.
