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
  cage greetd greetd-agreety gtk3 python-gobject python-cairo python-evdev \
  mpv yt-dlp \
  webkit2gtk-4.1 \
  gst-libav gst-plugins-good gst-plugins-bad gst-plugins-ugly \
  pipewire pipewire-pulse wireplumber libpulse \
  rsync
# mpv/yt-dlp back the (currently disabled) Videos screen; no game binaries
# are installed while the home screen is TBD placeholders.

echo "==> Copying launcher to $DEST (source: $HERE)"
install -d -o "$KIOSK_USER" -g "$KIOSK_USER" "$DEST" "$DEST/voices"
install -m 755 -o "$KIOSK_USER" -g "$KIOSK_USER" "$HERE/app/launcher.py" "$DEST/launcher.py"
install -m 755 -o "$KIOSK_USER" -g "$KIOSK_USER" "$HERE/app/videos.py" "$DEST/videos.py"
install -m 755 -o "$KIOSK_USER" -g "$KIOSK_USER" "$HERE/app/backwatch.py" "$DEST/backwatch.py"
install -m 755 -o "$KIOSK_USER" -g "$KIOSK_USER" "$HERE/app/run.sh" "$DEST/run.sh"
install -m 644 -o "$KIOSK_USER" -g "$KIOSK_USER" "$HERE/config/tiles.json" "$DEST/tiles.json"
# One-time maintenance tools the kiosk user must be able to run as leo.
install -m 755 -o "$KIOSK_USER" -g "$KIOSK_USER" "$HERE/tools/catalog_trim.py" "$DEST/catalog_trim.py"
install -m 755 -o "$KIOSK_USER" -g "$KIOSK_USER" "$HERE/app/powerd.py" "$DEST/powerd.py"
# Trusted video catalog for the Videos screen (9 random YouTube embeds).
install -m 644 -o "$KIOSK_USER" -g "$KIOSK_USER" \
  "$HERE/config/kiosk_videos.json" "$DEST/kiosk_videos.json"

echo "==> Copying the application package and catalog bootstrap"
# The entry point imports the leo_kiosk package from its own directory; without
# this the tablet keeps running the old single-file launcher.
rsync -a --delete --exclude __pycache__ "$HERE/app/leo_kiosk/" "$DEST/leo_kiosk/"
chown -R "$KIOSK_USER:$KIOSK_USER" "$DEST/leo_kiosk"
find "$DEST/leo_kiosk" -type d -exec chmod 755 {} +
find "$DEST/leo_kiosk" -type f -exec chmod 644 {} +
install -d -o "$KIOSK_USER" -g "$KIOSK_USER" "$DEST/catalog"
install -m 644 -o "$KIOSK_USER" -g "$KIOSK_USER" \
  "$HERE/catalog/bootstrap.json" "$DEST/catalog/bootstrap.json"

echo "==> Installing the invisible cursor (no pointer on the kiosk screen)"
# An empty cursor theme named 'default' in leo's ~/.icons: both cage (wlroots)
# and Firefox/GTK clients resolve it, hiding the pointer everywhere. The
# compositor reads the theme at its own startup, so a reboot is required.
CURSOR_DIR="$(mktemp -d)"
python3 "$HERE/tools/make_invisible_cursor.py" --output "$CURSOR_DIR/default" >/dev/null
install -d -o "$KIOSK_USER" -g "$KIOSK_USER" "/home/$KIOSK_USER/.icons"
rm -rf "/home/$KIOSK_USER/.icons/default"
cp -r "$CURSOR_DIR/default" "/home/$KIOSK_USER/.icons/default"
chown -R "$KIOSK_USER:$KIOSK_USER" "/home/$KIOSK_USER/.icons"
rm -rf "$CURSOR_DIR"

echo "==> Verifying deployed files match this source tree"
# Catches partial/failed copies (disk full, interrupted install).
mismatch=0
for f in app/launcher.py app/videos.py app/backwatch.py app/run.sh app/powerd.py config/tiles.json config/kiosk_videos.json; do
  dest=${f#*/}
  if ! cmp -s "$HERE/$f" "$DEST/$dest"; then
    echo "MISMATCH: $DEST/$dest does not match $HERE/$f" >&2
    mismatch=1
  fi
done
if ! diff -rq --exclude __pycache__ "$HERE/app/leo_kiosk" "$DEST/leo_kiosk" >/dev/null; then
  echo "MISMATCH: $DEST/leo_kiosk differs from $HERE/app/leo_kiosk" >&2
  mismatch=1
fi
if ! cmp -s "$HERE/catalog/bootstrap.json" "$DEST/catalog/bootstrap.json"; then
  echo "MISMATCH: $DEST/catalog/bootstrap.json does not match the source tree" >&2
  mismatch=1
fi
if [[ $mismatch -ne 0 ]]; then
  echo "Deployed files differ from this source tree; fix the source checkout and re-run." >&2
  exit 1
fi
# Checksum manifest: the tablet may hold several checkouts (this bit us once).
# To confirm WHICH tree is deployed, compare this manifest against any checkout:
#   sha256sum -c <(sed 's/  /  /' "$DEST/deploy-manifest")   # run inside a checkout
sha256sum "$HERE/app/launcher.py" "$HERE/app/videos.py" "$HERE/app/backwatch.py" "$HERE/app/run.sh" "$HERE/app/powerd.py" "$HERE/config/tiles.json" "$HERE/config/kiosk_videos.json" \
  | sed -e "s|$HERE/app/||" -e "s|$HERE/config/||" > "$DEST/deploy-manifest"
(find -L "$HERE/app/leo_kiosk" -name '*.py' -type f -print0 | xargs -0 sha256sum \
  | sed -e "s|$HERE/app/leo_kiosk/|leo_kiosk/|" -e "s|$HERE/app/||") >> "$DEST/deploy-manifest"
chown "$KIOSK_USER:$KIOSK_USER" "$DEST/deploy-manifest"
chmod 644 "$DEST/deploy-manifest"
echo "Deployed files verified. Manifest: $DEST/deploy-manifest"
sha256sum "$DEST/deploy-manifest" >/dev/null
cat "$DEST/deploy-manifest"

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

echo "==> Power button: owned by leopowerd; logind ignores the key"
install -d /etc/systemd/logind.conf.d
install -m 644 "$HERE/config/logind-power.conf" /etc/systemd/logind.conf.d/leotablet.conf
# Do NOT restart logind here: restarting it under a live compositor revokes
# the seat's devices and leaves the running cage frozen (libinput spams
# "failed to close device: Invalid argument"). The drop-in applies at next
# reboot - which leo_deploy does by default.

# One suspend state only, so a wake press during suspend entry isn't silently
# swallowed by systemd's multi-state fallback (see sleep-power.conf header).
install -d /etc/systemd/sleep.conf.d
install -m 644 "$HERE/config/sleep-power.conf" /etc/systemd/sleep.conf.d/leotablet.conf

# The Type Cover fires a wakeup event mid-suspend and aborts every attempt.
install -d /etc/udev/rules.d
install -m 644 "$HERE/config/90-leotablet-typecover.rules" /etc/udev/rules.d/90-leotablet-typecover.rules
udevadm control --reload
udevadm trigger --subsystem-match=usb --attr-match=idVendor=045e --attr-match=idProduct=096f

echo "==> Wi-Fi: default network profiles"
# Keyfile profiles are picked up by NetworkManager on reload; autoconnect
# joins the strongest available. The psk is plaintext by design so the
# profile provisions unattended (owner-provided credential).
install -d -m 700 /etc/NetworkManager/system-connections
install -m 600 "$HERE/config/wifi/standup-phone.nmconnection" \
  /etc/NetworkManager/system-connections/standup-phone.nmconnection
nmcli connection reload

# leopowerd owns the power button (screen off, 60 s screen-off -> sleep).
# See config/logind-power.conf for why logind ignores the key instead.
install -m 644 "$HERE/config/leopowerd.service" /etc/systemd/system/leopowerd.service
systemctl daemon-reload
systemctl enable --now leopowerd.service

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

echo "==> Hiding the GRUB boot menu (kiosk boots straight through)"
# Hidden menu with a 1 s timeout: nothing visible during normal boot, but
# holding ESC (or an arrow key) within the first second still opens the menu
# for recovery (bad kernel, fsck, ...). Fully removing the window
# (GRUB_TIMEOUT=0) makes a bad boot recoverable only from a live USB.
GRUB_DEFAULT="/etc/default/grub"
if [[ -f "$GRUB_DEFAULT" ]]; then
  if [[ ! -f "$GRUB_DEFAULT.orig" ]]; then
    cp "$GRUB_DEFAULT" "$GRUB_DEFAULT.orig"
  fi
  if grep -q '^GRUB_TIMEOUT=' "$GRUB_DEFAULT"; then
    sed -i 's/^GRUB_TIMEOUT=.*/GRUB_TIMEOUT=1/' "$GRUB_DEFAULT"
  else
    echo 'GRUB_TIMEOUT=1' >> "$GRUB_DEFAULT"
  fi
  if grep -q '^GRUB_TIMEOUT_STYLE=' "$GRUB_DEFAULT"; then
    sed -i 's/^GRUB_TIMEOUT_STYLE=.*/GRUB_TIMEOUT_STYLE=hidden/' "$GRUB_DEFAULT"
  else
    echo 'GRUB_TIMEOUT_STYLE=hidden' >> "$GRUB_DEFAULT"
  fi
  grub-mkconfig -o /boot/grub/grub.cfg
else
  echo "!! /etc/default/grub not found; not GRUB? Skipping boot menu change."
fi

echo
echo "Done. Reboot to start the kiosk:  sudo reboot"
echo "To go back to a text login later: sudo systemctl disable greetd && sudo systemctl enable getty@tty1"
echo "To restore the boot menu: sudo cp /etc/default/grub.orig /etc/default/grub && sudo grub-mkconfig -o /boot/grub/grub.cfg"
