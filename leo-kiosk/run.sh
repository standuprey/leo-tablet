#!/bin/sh
# cage session: back-button watcher in background, launcher in foreground.
# Both log to /tmp so crashes are diagnosable over SSH.
python3 /home/leo/kiosk/backwatch.py >/home/leo/kiosk/.backwatch.log 2>&1 &
exec python3 /home/leo/kiosk/launcher.py >/tmp/leo-launcher.log 2>&1
