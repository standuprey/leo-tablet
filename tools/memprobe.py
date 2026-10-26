#!/usr/bin/env python3
"""One-shot memory probe for the leo-tablet (diagnostic, not deployed runtime).

Prints per-process PSS/RSS (PSS requires root or same-uid), grouped totals
per user, and meminfo summary. Intended to run as:
    sudo python3 /tmp/memprobe.py            # on the tablet, for PSS
    python3 -                                # piped over ssh, RSS-only view
"""

import glob

UID_NAMES = {0: "root", 82: "http", 102: "polkitd", 988: "systemd-network"}


def probe(pid: int) -> tuple[int, int, int] | None:
    """Return (uid, pss_kB, rss_kB) or None if unreadable."""
    try:
        uid = int(
            open(f"/proc/{pid}/status").read().split("Uid:")[1].split()[0]
        )
        rss = 0
        pss = None
        for line in open(f"/proc/{pid}/smaps_rollup"):
            if line.startswith("Pss:"):
                pss = int(line.split()[1])
            elif line.startswith("Rss:"):
                rss = int(line.split()[1])
        return uid, pss if pss is not None else -1, rss
    except (OSError, ValueError, IndexError):
        return None


def name(pid: int) -> str:
    try:
        return (
            open(f"/proc/{pid}/cmdline", "rb")
            .read()
            .decode(errors="replace")
            .replace(chr(0), " ")
            .strip()[:80]
        )
    except OSError:
        return ""


rows = []
for p in glob.glob("/proc/[0-9]*"):
    pid = int(p.split("/")[2])
    info = probe(pid)
    if info is None:
        continue
    uid, pss, rss = info
    n = name(pid) or f"[{pid}]"
    rows.append((rss, pss, uid, pid, n))

rows.sort(reverse=True)
have_pss = any(p >= 0 for _, p, _, _, _ in rows)
print("PSS_kB    RSS_kB   USER  PID  CMD")
for rss, pss, uid, pid, n in rows[:25]:
    pss_s = f"{pss:8}" if pss >= 0 else "     n/a"
    print(f"{pss_s}  {rss:7}  {UID_NAMES.get(uid, str(uid)):<7} {pid:<5}  {n}")

sum_pss = sum(p for _, p, _, _, _ in rows if p >= 0)
sum_rss = sum(r for r, _, _, _, _ in rows)
print("SUM_RSS_kB:", sum_rss)
if have_pss:
    print("SUM_PSS_kB:", sum_pss)
    by_uid: dict[int, int] = {}
    for _, p, uid, _, _ in rows:
        if p >= 0:
            by_uid[uid] = by_uid.get(uid, 0) + p
    for uid in sorted(by_uid, key=lambda u: -by_uid[u]):
        print(f"SUM_PSS_uid{uid}({UID_NAMES.get(uid, uid)}):", by_uid[uid])

mi = {}
for l in open("/proc/meminfo"):
    parts = l.split()
    if len(parts) > 1:
        mi[parts[0][:-1]] = int(parts[1])
for k in ("MemTotal", "MemAvailable", "MemFree", "Slab", "Shmem", "SReclaimable"):
    print(k + "_kB:", mi.get(k))
