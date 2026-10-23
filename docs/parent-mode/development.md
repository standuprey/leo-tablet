# Development and validation

Run commands from the repository root. Runtime GTK, evdev and NetworkManager integration is still pending; the new domain package has no GI or hardware imports.

## Isolated development environment

Use the same Python interpreter as the kiosk system. Do not install development packages into system Python or run the installer for tests.

```sh
uv venv --python "$(command -v python3)" --system-site-packages .venv
uv pip install --python .venv/bin/python -e './leo-kiosk[dev]'
```

The editable project contains only application code. GTK/GIR runtime dependencies remain distribution-managed; system-site-packages allows future GTK tests to access the installed bindings. The current domain-only suite needs no GTK display or network manager.

## Checks

```sh
.venv/bin/python -m pytest leo-kiosk/tests -q
.venv/bin/python -m ruff check leo-kiosk
.venv/bin/python -m ruff format --check leo-kiosk/leo_kiosk leo-kiosk/tests
.venv/bin/python -m mypy --config-file leo-kiosk/pyproject.toml leo-kiosk/leo_kiosk
```

Only the legacy launcher's/watcher's existing percent-formatting is exempted from Ruff's UP031 rule; their runtime behavior has not been modified.

## Test boundaries

- Each test receives private temporary HOME/XDG directories and non-host D-Bus addresses.
- The default Python-socket guard rejects external networking, DNS, UDP sends and direct connections to the standard host system-bus socket. This is a test guard, not an OS security sandbox: native/C libraries and external subprocesses require their own injected fixture addresses and ownership checks.
- Mark controlled loopback fixture tests with `@pytest.mark.local_network`. This permits loopback only, never external addresses. Tests must not use real credentials or connect to a personal network.
- `fake_clock` and `fake_process` fixtures are inert: advancing time and recording signals never starts or signals a real process.
- `display`, `wayland` and `hardware` tests are skipped unless their corresponding `--run-display`, `--run-wayland` or `--run-hardware` flag is supplied. Flags do not create a display or authorize privileged/network changes.
- A future private D-Bus fixture must replace the nonexistent default address with its own isolated test bus, not the host bus.
- Passing domain tests does not satisfy the Surface Go button, browser-focus, networking or touch-only portal gates.

## Current implementation

See [implementation-status.md](implementation-status.md) for completed task IDs, validation results and remaining blockers. [specs.md](../../specs.md) remains the execution plan.
