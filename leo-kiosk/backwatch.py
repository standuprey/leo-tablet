#!/usr/bin/env python3
"""Kiosk back button: tap volume-down then volume-up within 1 second to
close the current app. (The Surface volume rocker emits instantaneous
press+release pairs — holding it produces no "held" state, so taps,
not a hold.)

Runs as the kiosk user (needs the 'input' group to read /dev/input).
The launcher writes the running app's PID to STATE_FILE and removes it
when home is shown again. Killing the app's process group makes the
launcher's watch loop bring the tiles back.
"""
import os
import signal
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, ".app-pid")
WINDOW = 1.0    # seconds allowed between the volume-down and volume-up taps
# linux-input event codes
EV_KEY = 1
KEY_VOLUMEUP = 115
KEY_VOLUMEDOWN = 114
# input_event: struct timeval (2 x i64), u16 type, u16 code, i32 value
FORMAT = "qqhhi"
SIZE = struct.calcsize(FORMAT)


def current_app_pid():
    try:
        with open(STATE_FILE) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def kill_app():
    pid = current_app_pid()
    if pid is None:
        return False
    try:
        os.killpg(pid, signal.SIGTERM)
        log("SIGTERM sent to process group %d" % pid)
    except (ProcessLookupError, PermissionError) as e:
        log("killpg %d failed: %s" % (pid, e))
        try:
            os.kill(pid, signal.SIGTERM)
            log("SIGTERM sent to pid %d" % pid)
        except (ProcessLookupError, PermissionError) as e2:
            log("kill %d failed: %s" % (pid, e2))
    return True


def log(msg):
    print("backwatch: %s" % msg, file=sys.stderr, flush=True)


def main():
    devices = sorted(
        os.path.join("/dev/input", d)
        for d in os.listdir("/dev/input")
        if d.startswith("event")
    )
    if not devices:
        log("no input devices found")
        return 1

    global t_start, last_down
    t_start = time.monotonic()
    last_down = [None]  # time of last volume-down press (list: mutable in closure)
    import select
    raw = {}  # fd -> device path
    for d in devices:
        try:
            raw[os.open(d, os.O_RDONLY | os.O_NONBLOCK)] = d
        except OSError as e:
            log("cannot open %s: %s" % (d, e))
    log("watching %d/%d devices: %s" % (len(raw), len(devices),
                                        ", ".join(raw.values())))

    def handle_event(dev, data):
        if len(data) != SIZE:
            log("short read on %s: %d bytes" % (dev, len(data)))
            return
        _, _, etype, ecode, evalue = struct.unpack(FORMAT, data)
        if etype != EV_KEY:
            return
        log("%+.2fs %s KEY code=%d value=%d" %
            (time.monotonic() - t_start, dev, ecode, evalue))
        if ecode not in (KEY_VOLUMEDOWN, KEY_VOLUMEUP) or evalue != 1:
            return
        now = time.monotonic()
        if ecode == KEY_VOLUMEDOWN:
            last_down[0] = now
        elif last_down[0] is not None and now - last_down[0] <= WINDOW:
            last_down[0] = None
            if not kill_app():
                log("no app pid in %s" % STATE_FILE)

    while True:
        readable, _, _ = select.select(list(raw), [], [], 0.1)
        for fd in readable:
            try:
                data = os.read(fd, SIZE)
                while data:
                    handle_event(raw[fd], data)
                    try:
                        data = os.read(fd, SIZE)
                    except OSError:
                        break
            except OSError:
                pass
        time.sleep(0.05)


if __name__ == "__main__":
    sys.exit(main())
