# Léo's tablet: Surface Go kiosk kit

A fullscreen picture-tile home screen for a 5-year-old, running on Arch Linux with the `cage` kiosk compositor.

## What's in this folder
| File | What it is |
|---|---|
| `launcher.py` | Fullscreen GTK3 home screen with big picture tiles |
| `tiles.json` | The tiles: emoji, label, color, command, time limit (minutes) |
| `install-kiosk.sh` | Installs packages, copies the files, makes content folders, sets up greetd auto-login |
| `voices/` | Optional: record Papa saying each word as `<tile id>.wav` (e.g. `draw.wav`); played on tap |

## How it behaves
- Tap a tile: the app opens fullscreen. When Léo quits it, **tap volume-down then volume-up within 1 second**, or the tile's time limit runs out, he's back on the home screen.
- Power button: **short press puts the tablet to sleep** (suspend), **holding it ~5 seconds powers it off** (logind long-press; config in `logind-power.conf`).
- Parent escape: tap the invisible top-left corner **5 times within 4 seconds**. The kiosk exits and you get a text login.
- If an app isn't installed, the tile says "Ask Papa to fix this one!" instead of crashing.

## SSH access
From any machine on the same network:
```
ssh standup@192.168.1.186
```
The admin user's key (`id_ed25519`) is authorized on the tablet, so no password is needed. The kiosk user (`leo`) has no SSH access and no sudo.

## How this device was set up
For reference if you ever need to rebuild it from scratch — this is what was actually done, in order.

1. **Base install.** Arch Linux installed by hand with GRUB; admin user `standup` created, kiosk user `leo` created with a locked password (no sudo).
2. **Network + SSH.** Wifi via `nmtui`, then `sudo systemctl enable --now sshd`.
3. **linux-surface kernel** (from the [wiki](https://github.com/linux-surface/linux-surface/wiki/Installation-and-Setup)) — needed for the touchscreen, which talks through Intel MEI rather than plain HID:
   ```
   curl -s https://raw.githubusercontent.com/linux-surface/linux-surface/master/pkg/keys/surface.asc | sudo pacman-key --add -
   sudo pacman-key --finger 56C464BAAC421453
   sudo pacman-key --lsign-key 56C464BAAC421453
   ```
   Append to `/etc/pacman.conf`:
   ```
   [linux-surface]
   Server = https://pkg.surfacelinux.com/arch/
   ```
   Then:
   ```
   sudo pacman -Syu
   sudo pacman -S linux-surface linux-surface-headers
   sudo grub-mkconfig -o /boot/grub/grub.cfg
   sudo reboot
   ```
   Check `uname -r` contains "surface". Test wifi and touch (`libinput list-devices`).
4. **Touchscreen daemon.** `sudo pacman -S iptsd && sudo systemctl enable --now iptsd` — without this, the touchscreen never appears as an input device.
5. **Time sync.** `sudo systemctl enable --now systemd-timesyncd` (clock was drifting unsynchronized before this).
6. **Install the kiosk**: copy this folder to the tablet, then `sudo ./install-kiosk.sh`.
7. **Reboot.** It should boot straight into the launcher. If it drops to a text login, the auto-login failed: check `sudo chage -l leo`, and read `journalctl -b -u greetd`.
   - Already installed and just want the power-button change? Copy `logind-power.conf` to `/etc/systemd/logind.conf.d/leotablet.conf` and `sudo systemctl try-restart systemd-logind.service`.

## Architecture
How the pieces fit together on a running tablet:

```
greetd ──auto-login──▶ leo
                         │
                         ├─ cage (Wayland kiosk compositor, fullscreen)
                         │    └─ launcher.py (GTK3 tile grid)
                         │         └─ spawns app processes (own process group)
                         │
                         └─ backwatch.py (reads /dev/input/event*, unprivileged)
```

- **Session**: `greetd` logs `leo` in automatically on tty1 and starts `cage`, which runs exactly one client fullscreen — the launcher. There is no window manager, no taskbar, no way out except the defined gestures.
- **Launcher**: `launcher.py` draws the tile grid. Tapping a tile spawns the tile's command with `start_new_session` (its own process group) and records the PID in `/home/leo/kiosk/.app-pid`; the file is removed when the home screen is shown again.
- **Back gesture**: `backwatch.py` runs as `leo` (in the `input` group) reading raw `/dev/input/event*`. It counts volume-key taps — down then up within 1 second — and on a match kills the recorded process group. The launcher's watch loop notices the app exited and redraws the tiles. Note: the Surface volume rocker emits instantaneous press+release pairs, so holds cannot be used as a gesture.
- **Power**: logind handles the physical power button (`logind-power.conf`: short press = suspend, ~5 s hold = power off) — no desktop session involved.
- **Content lives outside the kiosk**: `/home/leo/Leo/` folders (videos, photos, a local HTML page) are referenced by `tiles.json`, so content can be swapped or synced without touching the code.

## Test without the full kiosk
On any machine with GTK3 and PyGObject: `python3 launcher.py`. Tiles for missing apps show the "Ask Papa" message.

## Safety and upkeep
- Keep your admin user separate from `leo` (no sudo for `leo`), with SSH on your admin account to fix things remotely.
- Arch is rolling: update deliberately (say monthly, with the tablet in reach), not on autopilot. Keep the install USB around.
- Time limits live in `tiles.json` (`minutes` per tile). In-app exit gesture: `WINDOW` in `backwatch.py`.
- To undo auto-login: `sudo systemctl disable greetd && sudo systemctl enable getty@tty1`.

## Parent-mode implementation plan

The parent area, game review workflow, home-slot selection, and iwd-backed Wi-Fi/captive-portal support are **specified; domain foundations are implemented but not integrated into the launcher**:

- [Architecture and product behavior](docs/parent-mode/architecture.md)
- [Detailed implementation backlog](docs/parent-mode/backlog.md) — 68 dependency-linked tasks with Fibonacci sizes, domains, acceptance criteria, and tests
- [Machine-readable tasks](docs/parent-mode/tasks.json)
- [Saved discovery catalog](web-games.json) — source data, not a list of verified playable games
- [Implementation status](docs/parent-mode/implementation-status.md) — completed task IDs and remaining integration gates
- [Development and test commands](docs/parent-mode/development.md)

The planned gestures (Up/Down/Down for parent mode; Down/Down/Up to return) replace the current shortcut only when the implementation is deployed. The current behavior described above is unchanged.

## Status
- Tiles exist but still need to be designed and content is TBD, just some examples for now
