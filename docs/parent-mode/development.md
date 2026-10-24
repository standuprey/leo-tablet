# Development and validation

Run commands from the repository root. Runtime GTK, evdev and NetworkManager integration is still pending; the new domain package has no GI or hardware imports.

## Isolated development environment

Use the same Python interpreter as the kiosk system. Do not install development packages into system Python or run the installer for tests.

```sh
uv venv --python "$(command -v python3)" --system-site-packages .venv
uv pip install --python .venv/bin/python -e './leo-kiosk[dev]'
```

The editable project contains only application code. GTK/GIR runtime dependencies remain distribution-managed; system-site-packages allows future GTK tests to access the installed bindings. The current domain/storage suite needs no GTK display or network manager.

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

## SQLite lifecycle and migrations

- `open_database()` resolves `${XDG_DATA_HOME:-~/.local/share}/leo-kiosk/catalog.sqlite3`; relative/empty XDG overrides fall back to the home directory. The application directory is 0700, the database file 0600. Explicit path overrides must be caller-controlled; existing override-directory permissions are not changed.
- Returned connections use WAL, foreign keys, FULL synchronous writes, an explicit 3-second busy timeout and SQLite's same-thread guard. Close them explicitly (for example with `contextlib.closing`); SQLite's own connection context manager commits/rolls back but does **not** close the connection.
- Use `transaction(connection)` for one caller-owned transaction. It rejects nesting, rolls back domain errors without replacing their type, and translates SQLite failures to `StorageError`. Bind values through SQL parameters. Lower-level repository methods must not open another transaction inside a service-owned scope.
- Pass all trusted `Migration(version, statements)` values, in order starting at 1, whenever opening an application schema. Applied statement checksums and UTC timestamps are recorded in `schema_migrations`. Never edit an applied batch; append a new version instead. The default empty batch initializes infrastructure only; it does not create game/home tables yet.
- Startup refuses newer, incomplete, edited or unrecognized schema histories and corrupt files; it never silently resets existing data. Imports must not supply SQL. Migration SQL is trusted application code, not a general-purpose SQL sandbox.
- Before an initialized database is upgraded, SQLite's backup API snapshots committed data, including data still in WAL. Private `catalog.sqlite3.before-vN.<random>.bak` files remain beside the source; incomplete copies use `.partial` and are removed after failure when possible. A complete copy is flushed, renamed and its directory flushed before the schema transaction starts.
- All pending migrations share one transaction; failed SQL rolls back their schema/data/history changes and retains the pre-upgrade backup. Migration statements cannot commit, begin/savepoint transactions, attach databases or change PRAGMAs; `executescript` is never used.
- Stop the previous kiosk process before upgrading/restoring. Backups are not an online multi-version upgrade protocol or an implemented Restore UI. Keep successful backups until an administrator decides retention; if cleanup is prevented by an I/O/permission failure, `.partial` files are not valid restore artifacts.

Focused checks:

```sh
.venv/bin/python -m pytest leo-kiosk/tests/integration/test_database.py -q
.venv/bin/python -m pytest leo-kiosk/tests/integration/test_migrations.py -q
.venv/bin/python -m pytest leo-kiosk/tests/integration/test_storage_failures.py -q
```

The disk-full case uses SQLite's page limit on a temporary file, not a full host disk. Permission and backup failures are bounded fault injections; these are not claims of testing real hardware/filesystem failures.

## Current implementation

See [implementation-status.md](implementation-status.md) for completed task IDs, validation results and remaining blockers. [specs.md](../../specs.md) remains the execution plan.
