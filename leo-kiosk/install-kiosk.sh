#!/usr/bin/env bash
# Sets up Léo's kiosk on Arch: packages, files, content folders, greetd auto-login.
# Run as your ADMIN user from this folder:   sudo ./install-kiosk.sh
# It does not start anything; reboot when it finishes.
set -euo pipefail

KIOSK_USER="leo"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="/home/${KIOSK_USER}/kiosk"

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo ./install-kiosk.sh" >&2
  exit 1
fi
if ! id "$KIOSK_USER" >/dev/null 2>&1; then
  echo "User '$KIOSK_USER' does not exist. Create it first: useradd -m $KIOSK_USER" >&2
  exit 1
fi

echo "==> Installing packages"
pacman -S --needed --noconfirm \
  cage greetd greetd-agreety gtk3 python-gobject \
  gcompris-qt vlc feh firefox \
  pipewire pipewire-pulse wireplumber libpulse \
  rsync
# Optional apps: not in the official repos (cheese is archived upstream,
# tuxpaint is AUR-only). Tiles for missing apps show "Ask Papa".
for opt in tuxpaint cheese; do
  pacman -S --needed --noconfirm "$opt" 2>/dev/null \
    || echo "!! '$opt' not installed (not in official repos); its tile will show 'Ask Papa'."
done
# Minetest was renamed Luanti; install whichever this repo has.
pacman -S --needed --noconfirm luanti 2>/dev/null \
  || pacman -S --needed --noconfirm minetest 2>/dev/null \
  || echo "!! Neither luanti nor minetest installed; the Build tile will show 'Ask Papa'."

echo "==> Copying launcher to $DEST"
install -d -o "$KIOSK_USER" -g "$KIOSK_USER" "$DEST" "$DEST/voices"
install -m 755 -o "$KIOSK_USER" -g "$KIOSK_USER" "$HERE/launcher.py" "$DEST/launcher.py"
install -m 755 -o "$KIOSK_USER" -g "$KIOSK_USER" "$HERE/backwatch.py" "$DEST/backwatch.py"
install -m 755 -o "$KIOSK_USER" -g "$KIOSK_USER" "$HERE/run.sh" "$DEST/run.sh"
install -m 644 -o "$KIOSK_USER" -g "$KIOSK_USER" "$HERE/tiles.json" "$DEST/tiles.json"

echo "==> Creating content folders"
for d in carwash gabby pets family science; do
  install -d -o "$KIOSK_USER" -g "$KIOSK_USER" "/home/${KIOSK_USER}/Leo/$d"
done
SCI="/home/${KIOSK_USER}/Leo/science/index.html"
if [[ ! -e "$SCI" ]]; then
  cat > "$SCI" <<'HTML'
<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<body style="font-family:sans-serif;text-align:center;padding-top:20vh;font-size:48px">
Papa is adding experiments soon! 🔬
</body>
HTML
  chown "$KIOSK_USER:$KIOSK_USER" "$SCI"
fi

echo "==> Power button: short press = sleep, long press = power off"
install -d /etc/systemd/logind.conf.d
install -m 644 "$HERE/logind-power.conf" /etc/systemd/logind.conf.d/leotablet.conf
# Drop-ins are read on logind restart; this doesn't kill any session.
systemctl try-restart systemd-logind.service

echo "==> Letting $KIOSK_USER use audio, video and input devices"
# 'input' is for backwatch.py (volume-button hold-to-exit).
usermod -aG video,audio,input "$KIOSK_USER"

echo "==> Configuring greetd (auto-login into the kiosk)"
if [[ -f /etc/greetd/config.toml && ! -f /etc/greetd/config.toml.orig ]]; then
  cp /etc/greetd/config.toml /etc/greetd/config.toml.orig
fi
cat > /etc/greetd/config.toml <<EOF
[terminal]
vt = 1

# If the kiosk ever exits (e.g. the parent corner), you land on a text login.
[default_session]
command = "agreety --cmd /bin/bash"
user = "greeter"

# Runs once at boot, as $KIOSK_USER, with no password.
[initial_session]
command = "cage -s -- $DEST/run.sh"
user = "$KIOSK_USER"
EOF

systemctl enable greetd.service

echo
echo "Done. Reboot to start the kiosk:  sudo reboot"
echo "To go back to a text login later: sudo systemctl disable greetd && sudo systemctl enable getty@tty1"
