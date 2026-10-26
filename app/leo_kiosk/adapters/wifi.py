"""NetworkManager control via nmcli: scan, connect, forget, portal detect.

nmcli is the interface (no extra D-Bus dependency); polkit grants active
seat sessions network control, which covers the kiosk user. Captive portals
cannot be "logged into" from here — that is browser work; this module only
detects the portal state (connectivity == portal) so the UI can offer the
sign-in window.
"""

import subprocess

NMCLI = "nmcli"
CONNECTIVITY_CHECK_URL = "http://detectportal.firefox.com/success.txt"


class WifiError(RuntimeError):
    """nmcli failed or produced unusable output."""


def _run(args: list[str], timeout: int = 20) -> str:
    try:
        result = subprocess.run(
            [NMCLI, *args], capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WifiError(f"nmcli {args[0]} failed: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise WifiError(detail[-1] if detail else f"nmcli {args[0]} failed")
    return result.stdout


def _split_terse(line: str) -> list[str]:
    """Split an nmcli -t line on unescaped colons (SSID may contain colons)."""
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    fields.append("".join(current))
    return fields


def parse_wifi_list(output: str) -> list[dict[str, str]]:
    """Parse `nmcli -t -f IN-USE,SSID,SIGNAL,SECURITY device wifi list`."""
    networks = []
    for line in output.splitlines():
        if not line.strip():
            continue
        fields = _split_terse(line)
        while len(fields) < 4:
            fields.append("")
        in_use, ssid, signal, security = fields[:4]
        if not ssid:
            continue  # hidden networks cannot be joined by tapping a tile
        networks.append(
            {
                "in_use": in_use == "*",
                "ssid": ssid,
                "signal": signal,
                "security": security or "open",
            }
        )
    networks.sort(key=lambda n: (not n["in_use"], -int(n["signal"] or 0)))
    return networks


def list_networks() -> list[dict[str, str]]:
    _run(["device", "wifi", "rescan"])
    return parse_wifi_list(_run(["-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list"]))


def parse_device_status(output: str) -> str | None:
    """Connected Wi-Fi network name from `nmcli -t device status`, or None."""
    for line in output.splitlines():
        fields = _split_terse(line)
        if len(fields) >= 4 and fields[1] == "wifi" and fields[3]:
            return fields[3]
    return None


def current_network() -> str | None:
    return parse_device_status(_run(["-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"]))


def connectivity() -> str:
    """Global connectivity: none, portal, limited, full, or unknown."""
    return _run(["networking", "connectivity"]).strip() or "unknown"


def saved_networks() -> list[str]:
    output = _run(["-t", "-f", "NAME,TYPE,DEVICE", "connection", "show"])
    names = []
    for line in output.splitlines():
        fields = _split_terse(line)
        if len(fields) >= 2 and fields[1] == "802-11-wireless" and fields[0]:
            names.append(fields[0])
    return sorted(names)


def connect(ssid: str, password: str | None) -> tuple[bool, str]:
    """Join a network; returns (success, message). Hidden SSIDs unsupported."""
    args = ["device", "wifi", "connect", ssid]
    if password:
        args += ["password", password]
    try:
        _run(args, timeout=45)
        return True, f"Connected to {ssid}."
    except WifiError as exc:
        return False, str(exc)


def forget(name: str) -> tuple[bool, str]:
    try:
        _run(["connection", "delete", name])
        return True, f"Forgot {name}."
    except WifiError as exc:
        return False, str(exc)